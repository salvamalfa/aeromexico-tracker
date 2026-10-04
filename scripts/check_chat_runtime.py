"""Exercise the minimal chat runtime against the checked-in public snapshot.

This profile needs no provider credentials, network access, warehouse, or
browser. It is intended to run inside an isolated `chat-runtime` environment.
"""

from __future__ import annotations

import asyncio
import json
import secrets
import sys
import tempfile
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from typing import Any

from src.conversational_analytics.__main__ import main as chat_main
from src.conversational_analytics.api import create_app
from src.conversational_analytics.auth import hash_password
from src.conversational_analytics.config import ChatConfig
from src.conversational_analytics.data.snapshot import Snapshot
from src.conversational_analytics.providers.openai import OpenAIProvider
from src.conversational_analytics.usage_import import validate_ledger

ROOT = Path(__file__).resolve().parents[1]
ORIGIN = "https://dashboard.example"


async def _request(
    app: Any,
    method: str,
    path: str,
    *,
    body: bytes = b"",
    headers: dict[str, str] | None = None,
) -> tuple[int, bytes]:
    request_headers = {"host": "localhost", "content-length": str(len(body)), **(headers or {})}
    incoming = [{"type": "http.request", "body": body, "more_body": False}]
    sent: list[dict[str, Any]] = []

    async def receive() -> dict[str, Any]:
        if incoming:
            return incoming.pop(0)
        await asyncio.Future()

    async def send(message: dict[str, Any]) -> None:
        sent.append(message)

    raw_path = path.split("?", 1)[0].encode("ascii")
    scope = {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.3"},
        "http_version": "1.1",
        "method": method,
        "scheme": "http",
        "path": path.split("?", 1)[0],
        "raw_path": raw_path,
        "query_string": path.split("?", 1)[1].encode("ascii") if "?" in path else b"",
        "root_path": "",
        "headers": [
            (key.lower().encode("ascii"), value.encode("latin-1")) for key, value in request_headers.items()
        ],
        "client": ("127.0.0.1", 43210),
        "server": ("127.0.0.1", 8765),
    }
    await app(scope, receive, send)
    status = next(item["status"] for item in sent if item["type"] == "http.response.start")
    response_body = b"".join(item.get("body", b"") for item in sent if item["type"] == "http.response.body")
    return status, response_body


def _events(body: bytes) -> list[dict[str, Any]]:
    parsed = []
    for frame in body.decode("utf-8").split("\n\n"):
        fields = {}
        for line in frame.splitlines():
            key, separator, value = line.partition(":")
            if separator:
                fields[key] = value.lstrip()
        if "data" in fields:
            parsed.append({"type": fields.get("event", "message"), **json.loads(fields["data"])})
    return parsed


async def _check() -> None:
    # The command parser and official provider adapter must import without
    # creating a client or making a provider request.
    assert OpenAIProvider and validate_ledger
    help_output = StringIO()
    try:
        with redirect_stdout(help_output):
            chat_main(["import-usage", "--help"])
    except SystemExit as exc:
        assert exc.code == 0
    else:  # pragma: no cover - argparse always exits after --help.
        raise AssertionError("import-usage help did not exit successfully")

    snapshot = Snapshot(ROOT / "site")
    assert snapshot.version != "unavailable"
    password = secrets.token_urlsafe(18)
    with tempfile.TemporaryDirectory(prefix="airline-chat-runtime-") as temp:
        config = ChatConfig(
            state_path=Path(temp) / "chat.sqlite3",
            auth_mode="password",
            password_users={"owner": hash_password(password)},
            allowed_origins=(ORIGIN,),
            provider="mock",
        )
        app = create_app(config, snapshot=snapshot, start_worker=True)
        async with app.router.lifespan_context(app):
            assert app.state.chat_worker and app.state.chat_worker.running
            unauthenticated, _ = await _request(
                app, "POST", "/api/chat/conversations", headers={"origin": ORIGIN}
            )
            assert unauthenticated == 401

            login_body = json.dumps({"password": password}).encode("utf-8")
            login_status, login_content = await _request(
                app,
                "POST",
                "/api/chat/login",
                body=login_body,
                headers={"origin": ORIGIN, "content-type": "application/json"},
            )
            assert login_status == 200
            session = json.loads(login_content)["session"]
            auth_headers = {"origin": ORIGIN, "authorization": f"Bearer {session}"}

            create_status, create_content = await _request(
                app, "POST", "/api/chat/conversations", headers=auth_headers
            )
            assert create_status == 201
            conversation_id = json.loads(create_content)["id"]

            question = "Compara el factor de ocupación de Aeroméxico entre 2026Q2 y 2026Q1."
            turn_body = json.dumps(
                {
                    "content": question,
                    "client_message_id": "runtime-profile-turn",
                    "context": {"tab": "economy", "period": "2026Q2", "entity": "AEROMEXICO"},
                }
            ).encode("utf-8")
            turn_status, turn_content = await _request(
                app,
                "POST",
                f"/api/chat/conversations/{conversation_id}/messages",
                body=turn_body,
                headers={**auth_headers, "content-type": "application/json"},
            )
            assert turn_status == 202
            turn_id = json.loads(turn_content)["turn_id"]
            event_status, event_content = await _request(
                app, "GET", f"/api/chat/turns/{turn_id}/events?after=0", headers=auth_headers
            )
            assert event_status == 200
            events = _events(event_content)
            assert events[-1]["type"] == "turn.completed"
            tool_events = [event for event in events if event["type"] == "tool.completed"]
            assert len(tool_events) == 1 and tool_events[0]["name"] == "compare_metrics"
            comparison = tool_events[0]["result"]["comparison"]
            assert comparison["previous"]["period"] == "2026Q1"
            assert comparison["current"]["period"] == "2026Q2"

    heavyweight = {"pandas", "polars", "pyarrow", "duckdb", "playwright"}
    assert not heavyweight.intersection(sys.modules)


if __name__ == "__main__":
    asyncio.run(_check())
    print("chat runtime smoke: ok (snapshot, auth, worker, compare_metrics; no provider calls)")
