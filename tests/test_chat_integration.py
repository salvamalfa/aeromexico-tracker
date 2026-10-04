# Optional chat dependencies are intentionally imported after pytest skips.
# ruff: noqa: E402,I001

from __future__ import annotations

import hashlib
import json
import re
import threading
from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")
from fastapi.testclient import TestClient

from src.conversational_analytics.config import ChatConfig
from src.conversational_analytics.data.snapshot import Snapshot
from src.conversational_analytics.providers.mock import MockProvider


ROOT = Path(__file__).resolve().parents[1]
QUESTION = "Compara el factor de ocupación de las tres aerolíneas en 2026Q2."
CONTEXT = {
    "tab": "economy",
    "period": "2026Q2",
    "entity": ["AEROMEXICO", "VOLARIS", "VIVA_AEROBUS"],
}


def _snapshot() -> Snapshot:
    return Snapshot(ROOT / "site")


def _config(path: Path, **overrides: Any) -> ChatConfig:
    return ChatConfig(state_path=path, **overrides)


def _sse_events(body: str) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for frame in re.split(r"\r?\n\r?\n", body):
        if not frame.strip() or frame.startswith(":"):
            continue
        fields: dict[str, str] = {}
        for line in frame.splitlines():
            if ":" in line:
                key, value = line.split(":", 1)
                fields[key] = value.lstrip()
        if "data" in fields:
            payload = json.loads(fields["data"])
            events.append(
                {
                    "id": int(fields["id"]) if fields.get("id", "").isdigit() else None,
                    "type": fields.get("event", "message"),
                    **payload,
                }
            )
    return events


class _VersionedSnapshot:
    """Expose the same verified public data under a different immutable version."""

    def __init__(self, source: Snapshot, version: str):
        self._source = source
        self.version = version
        self.semantic_version = source.semantic_version

    def catalog(self) -> dict[str, Any]:
        return self._source.catalog()

    def payload(self, relative_path: str) -> Any:
        return self._source.payload(relative_path)


class _DelayedMockProvider:
    def __init__(self, snapshot: Snapshot):
        self.delegate = MockProvider(snapshot)
        self.started = threading.Event()
        self.release = threading.Event()
        self.calls = 0

    def run_turn(self, **kwargs: Any):
        self.calls += 1
        self.started.set()
        if not self.release.wait(timeout=8):
            raise TimeoutError("test provider was not released")
        return self.delegate.run_turn(**kwargs)

    def cancel(self, session_id: str) -> None:
        self.delegate.cancel(session_id)

    def delete(self, session_id: str) -> None:
        self.delegate.delete(session_id)


def _create_conversation(client: TestClient) -> str:
    response = client.post("/api/chat/conversations")
    assert response.status_code == 201, response.text
    return response.json()["id"]


def _submit(
    client: TestClient, conversation_id: str, client_message_id: str = "integration-message-1"
) -> str:
    response = client.post(
        f"/api/chat/conversations/{conversation_id}/messages",
        json={"content": QUESTION, "client_message_id": client_message_id, "context": CONTEXT},
    )
    assert response.status_code == 202, response.text
    payload = response.json()
    assert payload["status"] in {"pending", "running"}
    return payload["turn_id"]


def test_default_mock_chat_uses_public_snapshot_and_replays_grounded_sse(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Exercise app defaults, quota admission, tools, evidence, and SSE replay offline."""
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    from src.conversational_analytics.api import create_app

    snapshot = _snapshot()
    app = create_app(config=_config(tmp_path / "chat.sqlite3"), snapshot=snapshot)
    with TestClient(app, base_url="http://127.0.0.1", client=("127.0.0.1", 50000)) as client:
        conversation_id = _create_conversation(client)
        turn_id = _submit(client, conversation_id)

        events_response = client.get(f"/api/chat/turns/{turn_id}/events?after=0")
        assert events_response.status_code == 200
        assert events_response.headers["content-type"].startswith("text/event-stream")
        events = _sse_events(events_response.text)
        assert [event["id"] for event in events] == sorted(event["id"] for event in events)
        assert [event["type"] for event in events][-1] == "turn.completed"
        tool_events = [event for event in events if event["type"] == "tool.completed"]
        assert len(tool_events) == 1
        result = tool_events[0]["result"]
        rows = result["rows"]
        assert {(row["entity_id"], row["period"]) for row in rows} == {
            ("AEROMEXICO", "2026Q2"),
            ("VOLARIS", "2026Q2"),
            ("VIVA_AEROBUS", "2026Q2"),
        }
        assert all(row["availability"] == "available" for row in rows)
        for row in rows:
            assert row["unit"] == "fraction"
            assert row["display_unit"] == "%"
            assert row["display_value"] == round(row["value"] * 100, 1)
            assert row["source_references"]
            assert all(ref["url"].startswith("https://") for ref in row["source_references"])
        # Replaying from the queue event returns stored events without invoking
        # the tool again or generating a second set of provider actions.
        queued_seq = next(event["id"] for event in events if event["type"] == "turn.queued")
        replay = _sse_events(client.get(f"/api/chat/turns/{turn_id}/events?after={queued_seq}").text)
        replayed_ids = [event["id"] for event in replay]
        expected_ids = [event["id"] for event in events if event["id"] > queued_seq]
        assert replayed_ids == expected_ids
        assert len([event for event in replay if event["type"] == "tool.started"]) == 1

        conversation = client.get(f"/api/chat/conversations/{conversation_id}").json()
        turn = next(item for item in conversation["turns"] if item["id"] == turn_id)
        assert turn["status"] == "completed"
        persisted_turn = app.state.chat_store.get_turn("local", turn_id)
        assert persisted_turn["usage_complete"] == 1
        assert persisted_turn["reserved_tokens"] == 0
        assert len([message for message in conversation["messages"] if message["role"] == "user"]) == 1


def test_bearer_users_cannot_read_each_others_conversations(tmp_path: Path) -> None:
    from src.conversational_analytics.api import create_app

    token_a, token_b = "offline-user-a-token", "offline-user-b-token"
    config = _config(
        tmp_path / "bearer.sqlite3",
        auth_mode="bearer",
        bearer_users={
            hashlib.sha256(token_a.encode()).hexdigest(): "user-a",
            hashlib.sha256(token_b.encode()).hexdigest(): "user-b",
        },
    )
    app = create_app(config=config, snapshot=_snapshot(), start_worker=False)
    with TestClient(app, base_url="http://testserver") as client:
        created = client.post("/api/chat/conversations", headers={"Authorization": f"Bearer {token_a}"})
        assert created.status_code == 201, created.text
        conversation_id = created.json()["id"]
        assert (
            client.get(
                f"/api/chat/conversations/{conversation_id}", headers={"Authorization": f"Bearer {token_a}"}
            ).status_code
            == 200
        )
        assert (
            client.get(
                f"/api/chat/conversations/{conversation_id}", headers={"Authorization": f"Bearer {token_b}"}
            ).status_code
            == 404
        )


def test_snapshot_change_rejects_followup_to_pending_v1_conversation(tmp_path: Path) -> None:
    from src.conversational_analytics.api import create_app

    snapshot_v1 = _snapshot()
    provider = _DelayedMockProvider(snapshot_v1)
    state_path = tmp_path / "snapshot.sqlite3"
    app_v1 = create_app(config=_config(state_path), snapshot=snapshot_v1, provider=provider)
    with TestClient(app_v1, base_url="http://127.0.0.1", client=("127.0.0.1", 50000)) as client_v1:
        conversation_id = _create_conversation(client_v1)
        turn_id = _submit(client_v1, conversation_id, "pinned-turn-1")
        assert provider.started.wait(timeout=3)
        pending = client_v1.get(f"/api/chat/conversations/{conversation_id}").json()
        assert next(turn for turn in pending["turns"] if turn["id"] == turn_id)["status"] == "running"

        app_v2 = create_app(
            config=_config(state_path),
            snapshot=_VersionedSnapshot(snapshot_v1, "snapshot-v2-test"),
            provider=MockProvider(snapshot_v1),
        )
        with TestClient(app_v2, base_url="http://127.0.0.1", client=("127.0.0.1", 50000)) as client_v2:
            response = client_v2.post(
                f"/api/chat/conversations/{conversation_id}/messages",
                json={"content": QUESTION, "client_message_id": "v2-followup", "context": CONTEXT},
            )
            assert response.status_code == 409
            assert "snapshot_changed" in response.text
        provider.release.set()


def test_delayed_worker_keeps_turn_and_replay_does_not_duplicate_tool_call(tmp_path: Path) -> None:
    from src.conversational_analytics.api import create_app

    snapshot = _snapshot()
    provider = _DelayedMockProvider(snapshot)
    app = create_app(config=_config(tmp_path / "delayed.sqlite3"), snapshot=snapshot, provider=provider)
    with TestClient(app, base_url="http://127.0.0.1", client=("127.0.0.1", 50000)) as client:
        conversation_id = _create_conversation(client)
        turn_id = _submit(client, conversation_id, "delayed-message-1")
        assert provider.started.wait(timeout=3)
        while_running = client.get(f"/api/chat/conversations/{conversation_id}").json()
        assert next(turn for turn in while_running["turns"] if turn["id"] == turn_id)["status"] == "running"
        assert sum(message["role"] == "user" for message in while_running["messages"]) == 1
        assert not any(message["role"] == "assistant" for message in while_running["messages"])

        provider.release.set()
        events = _sse_events(client.get(f"/api/chat/turns/{turn_id}/events?after=0").text)
        assert events[-1]["type"] == "turn.completed"
        assert provider.calls == 1
        replay = _sse_events(client.get(f"/api/chat/turns/{turn_id}/events?after=0").text)
        assert [event["id"] for event in replay] == [event["id"] for event in events]
        assert len([event for event in replay if event["type"] == "tool.completed"]) == 1
        assert provider.calls == 1
