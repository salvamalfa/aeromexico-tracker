from __future__ import annotations

import asyncio
import json
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient
from starlette.requests import Request

from scripts.start_chat_runtime import (
    LOCAL_FINALIZATION_SECONDS,
    PROVIDER_EXECUTION_MAX_SECONDS,
    RAILWAY_DRAIN_SECONDS,
    RAILWAY_SHUTDOWN_MARGIN_SECONDS,
    USAGE_RECONCILIATION_SECONDS,
    UVICORN_CONNECTION_DRAIN_SECONDS,
    WORKER_DRAIN_SECONDS,
    create_shutdown_aware_server,
    required_railway_drain_seconds,
    runtime_config,
    worker_drain_seconds,
)
from src.conversational_analytics.api import create_app
from src.conversational_analytics.auth import hash_password
from src.conversational_analytics.config import ChatConfig
from src.conversational_analytics.providers.base import ProviderResult
from src.conversational_analytics.storage import ChatStore


class Snapshot:
    version = "snapshot-v1"
    semantic_version = "semantic-v1"

    def catalog(self):
        return {"metrics": {"metrics": []}}


class EmptyRegistry:
    def tool_specs(self):
        return []


def test_uvicorn_shutdown_fences_claims_before_waiting_for_connections():
    observed = []

    class FakeConfig:
        def __init__(self, app, **kwargs):
            self.app = app
            self.options = kwargs

    class FakeServer:
        def __init__(self, config):
            self.config = config

        async def shutdown(self, sockets=None):
            observed.append(("base-shutdown", sockets))

    state = SimpleNamespace(begin_shutdown=lambda: observed.append(("fence-claims", None)))
    app = SimpleNamespace(state=state)
    uvicorn = SimpleNamespace(Config=FakeConfig, Server=FakeServer)
    server = create_shutdown_aware_server(uvicorn, app, host="127.0.0.1", port=8080)

    asyncio.run(server.shutdown())

    assert observed == [("fence-claims", None), ("base-shutdown", None)]
    assert server.config.options["timeout_graceful_shutdown"] == 5
    max_turn_config = ChatConfig(max_turn_seconds=PROVIDER_EXECUTION_MAX_SECONDS)
    assert worker_drain_seconds(max_turn_config) == 220
    assert required_railway_drain_seconds(max_turn_config) == 230
    assert (
        PROVIDER_EXECUTION_MAX_SECONDS
        + USAGE_RECONCILIATION_SECONDS
        + LOCAL_FINALIZATION_SECONDS
        == WORKER_DRAIN_SECONDS
    )
    reduced_turn_config = ChatConfig(max_turn_seconds=90)
    assert worker_drain_seconds(reduced_turn_config) == 130
    assert required_railway_drain_seconds(reduced_turn_config) == 140
    assert (
        UVICORN_CONNECTION_DRAIN_SECONDS + WORKER_DRAIN_SECONDS + RAILWAY_SHUTDOWN_MARGIN_SECONDS
        <= RAILWAY_DRAIN_SECONDS
    )


def test_worker_shutdown_rejects_execution_budget_above_hosted_limit():
    with pytest.raises(ValueError, match="CHAT_MAX_TURN_SECONDS cannot exceed 180 seconds"):
        worker_drain_seconds(ChatConfig(max_turn_seconds=181))


def test_hosted_runtime_rejects_turn_timeout_above_execution_cap(monkeypatch, tmp_path):
    values = {
        "CHAT_AUTH_MODE": "password",
        "CHAT_PASSWORDS_JSON": json.dumps(
            [{"user_id": "owner", "password_hash": hash_password("shutdown-test-password")}]
        ),
        "CHAT_ALLOWED_ORIGINS": "https://dashboard.example",
        "CHAT_PROVIDER": "mock",
        "CHAT_ADMISSION_ENABLED": "false",
        "CHAT_RETENTION_DAYS": "30",
        "CHAT_STATE_PATH": str(tmp_path / "chat.sqlite3"),
        "CHAT_MAX_TURN_SECONDS": "181",
        "PORT": "8080",
    }
    for name, value in values.items():
        monkeypatch.setenv(name, value)

    with pytest.raises(ValueError, match="CHAT_MAX_TURN_SECONDS cannot exceed 180 seconds"):
        runtime_config(volume_path=tmp_path)
    assert not list(tmp_path.glob(".chat-write-check-*"))


def test_runtime_sse_shutdown_keeps_active_turn_usage_and_leaves_pending_unclaimed(tmp_path: Path):
    path = tmp_path / "runtime-shutdown.sqlite3"

    class SlowProvider:
        supports_input_authorization = True

        def __init__(self):
            self.started = threading.Event()
            self.release = threading.Event()
            self.calls = 0

        def run_turn(self, **kwargs):
            kwargs["authorize_input"]()
            self.calls += 1
            kwargs["emit"]("message.delta", {"text": "chunk"})
            self.started.set()
            self.release.wait(timeout=3)
            return ProviderResult("respuesta", input_tokens=17, output_tokens=9, usage_complete=True)

        def cancel(self, session_id):
            pass

        def delete(self, session_id):
            pass

    provider = SlowProvider()
    config = ChatConfig(
        state_path=path,
        admission_enabled=True,
        max_active_per_user=2,
        poll_interval_seconds=0.01,
        max_turn_seconds=PROVIDER_EXECUTION_MAX_SECONDS,
        estimated_input_cost_per_million=0.10,
        estimated_output_cost_per_million=0.50,
    )
    app = create_app(
        config,
        snapshot=Snapshot(),
        provider=provider,
        worker_shutdown_timeout_seconds=worker_drain_seconds(config),
    )
    app.state.chat_worker._registry = EmptyRegistry()
    sse_open = threading.Event()
    sse_closed = threading.Event()

    with TestClient(app, base_url="http://127.0.0.1", client=("127.0.0.1", 50000)) as client:
        conversation = client.post("/api/chat/conversations").json()
        first = client.post(
            f"/api/chat/conversations/{conversation['id']}/messages",
            json={"content": "primera", "client_message_id": "first"},
        ).json()
        assert provider.started.wait(timeout=1)
        queued_conversation = client.post("/api/chat/conversations").json()
        second_response = client.post(
            f"/api/chat/conversations/{queued_conversation['id']}/messages",
            json={"content": "segunda", "client_message_id": "second"},
        )
        assert second_response.status_code == 202, second_response.text
        second = second_response.json()
        assert second["status"] == "pending"

        def read_sse():
            try:

                async def consume_sse():
                    scope = {
                        "type": "http",
                        "asgi": {"version": "3.0"},
                        "http_version": "1.1",
                        "method": "GET",
                        "scheme": "http",
                        "path": f"/api/chat/turns/{first['turn_id']}/events",
                        "raw_path": b"/events",
                        "query_string": b"",
                        "root_path": "",
                        "headers": [],
                        "client": ("127.0.0.1", 50000),
                        "server": ("127.0.0.1", 8080),
                        "state": {},
                        "app": app,
                    }
                    request = Request(scope)
                    request.state.owner_id = "local"

                    async def connected():
                        return False

                    request.is_disconnected = connected
                    endpoint = next(
                        route.endpoint
                        for route in app.routes
                        if getattr(route, "path", "") == "/api/chat/turns/{turn_id}/events"
                    )
                    response = await endpoint(first["turn_id"], request, after=0, last_event_id=None)
                    async for chunk in response.body_iterator:
                        if "chunk" in chunk:
                            sse_open.set()
                            # Keep the stream attached while shutdown fences claims.
                            await asyncio.to_thread(provider.release.wait, 1)

                asyncio.run(consume_sse())
            finally:
                sse_closed.set()

        sse_thread = threading.Thread(target=read_sse)
        sse_thread.start()
        assert sse_open.wait(timeout=1)

        app.state.begin_shutdown()
        worker = app.state.chat_worker
        assert worker._stop.is_set()
        store: ChatStore = app.state.chat_store
        assert store.get_turn("local", second["turn_id"])["status"] == "pending"
        provider.release.set()
        sse_thread.join(timeout=2)
        assert sse_closed.is_set()

    assert not app.state.chat_worker.running
    first_record = app.state.chat_store.get_turn("local", first["turn_id"])
    assert (first_record["status"], first_record["usage_complete"], first_record["reserved_tokens"]) == (
        "completed",
        1,
        0,
    )
    assert app.state.chat_store.get_turn("local", second["turn_id"])["status"] == "pending"
    assert provider.calls == 1
    usage = app.state.chat_store.usage("local")
    assert (usage["input_tokens"], usage["output_tokens"], usage["turn_count"]) == (17, 9, 1)


def test_lifespan_worker_drain_is_bounded(tmp_path: Path):
    path = tmp_path / "bounded-runtime-shutdown.sqlite3"

    class StuckProvider:
        supports_input_authorization = True

        def __init__(self):
            self.started = threading.Event()
            self.release = threading.Event()
            self.returned = threading.Event()

        def run_turn(self, **kwargs):
            kwargs["authorize_input"]()
            kwargs["persist_session"]("fixture-session")
            self.started.set()
            self.release.wait(timeout=2)
            self.returned.set()
            return ProviderResult("respuesta", input_tokens=4, output_tokens=2, usage_complete=True)

        def cancel(self, session_id):
            time.sleep(1)

        def delete(self, session_id):
            pass

    provider = StuckProvider()
    app = create_app(
        ChatConfig(state_path=path, admission_enabled=True),
        snapshot=Snapshot(),
        provider=provider,
        worker_shutdown_timeout_seconds=0.05,
    )
    app.state.chat_worker._registry = EmptyRegistry()
    with TestClient(app, base_url="http://127.0.0.1", client=("127.0.0.1", 50000)) as client:
        conversation = client.post("/api/chat/conversations").json()
        turn = client.post(
            f"/api/chat/conversations/{conversation['id']}/messages",
            json={"content": "lenta", "client_message_id": "slow"},
        ).json()
        assert provider.started.wait(timeout=1)
        started = time.monotonic()
        app.state.begin_shutdown()
    elapsed = time.monotonic() - started
    assert elapsed < 0.5
    record = app.state.chat_store.get_turn("local", turn["turn_id"])
    assert (record["status"], record["error_code"], record["usage_complete"]) == (
        "failed",
        "timeout",
        0,
    )
    assert record["reserved_tokens"] > 0
    provider.release.set()
    assert provider.returned.wait(timeout=1)
    deadline = time.monotonic() + 1
    while app.state.chat_store.get_turn("local", turn["turn_id"])["usage_complete"] != 1:
        assert time.monotonic() < deadline
        time.sleep(0.01)
    late = app.state.chat_store.get_turn("local", turn["turn_id"])
    assert (
        late["status"],
        late["estimated_input_tokens"],
        late["estimated_output_tokens"],
        late["reserved_tokens"],
    ) == (
        "failed",
        4,
        2,
        0,
    )
    assert app.state.chat_store.usage("local")["turn_count"] == 1
