"""Exercise the minimal chat runtime against the checked-in public snapshot.

This profile needs no provider credentials, network access, warehouse, or
browser. It is intended to run inside an isolated `chat-runtime` environment.
"""

from __future__ import annotations

import asyncio
import argparse
import hashlib
import json
import os
import secrets
import shutil
import sys
import tempfile
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from typing import Any
from unittest.mock import patch

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


def _check_packaged_business_metrics_snapshot() -> None:
    """Verify the image's pinned proposal can validate a receipt-bound fixture.

    The receipt and published financial payload below exist only in a temporary
    fixture tree. This proves the isolated runtime has the proposal closure it
    needs without adding an approval receipt or financial data to the image.
    """
    from src.publish import manifest as manifest_mod
    from src.web_export.business_metrics import build_approved_payload
    from src.web_export.business_metrics_approval import (
        APPROVAL_RECEIPT_SHA256_ENV,
        canonical_receipt_sha256,
    )
    from src.web_export.writer import write_json

    proposal = ROOT / "config/chat/business-metrics-proposal.json"
    definitions = ROOT / "config/chat/metrics-candidates.json"
    assert proposal.is_file(), "packaged business-metrics proposal is missing"
    assert definitions.is_file(), "packaged business-metrics definitions are missing"
    with tempfile.TemporaryDirectory(prefix="chat-runtime-approved-metrics-") as temp:
        fixture_root = Path(temp)
        site = fixture_root / "site"
        shutil.copytree(ROOT / "tests/fixtures/chat/site", site)
        receipt_path = fixture_root / "receipt-fixture-only.json"
        receipt = {
            "schema_version": "business_metrics_approval_v1",
            "status": "owner_approved",
            "receipt_id": "runtime-smoke-fixture-only",
            "approved_at": "2026-01-01T00:00:00Z",
            "approved_metric_ids": ["total_revenue"],
            "definitions_sha256": hashlib.sha256(definitions.read_bytes()).hexdigest(),
            "proposal_sha256": hashlib.sha256(proposal.read_bytes()).hexdigest(),
            "owner_id": "salvamalfa",
            "decision_reference": "synthetic runtime smoke fixture only",
        }
        write_json(receipt_path, receipt)
        pin = canonical_receipt_sha256(receipt)
        with patch.dict(os.environ, {APPROVAL_RECEIPT_SHA256_ENV: pin}):
            payload, receipt = build_approved_payload(proposal, definitions, receipt_path)
            write_json(site / "data/v1/business_metrics.json", payload)
            write_json(site / "data/v1/business_metrics.approval.json", receipt)
            manifest = json.loads((site / "publication_manifest.json").read_text(encoding="utf-8"))
            manifest["contracts"] = manifest_mod.contract_hashes()
            manifest["files"] = manifest_mod.file_entries(site)
            manifest_mod.write_manifest(site, manifest)

            approved_snapshot = Snapshot(site)
            approved = approved_snapshot.payload("data/v1/business_metrics.json")
            assert approved["metadata"]["metric_ids"] == ["total_revenue"]


async def _check(*, fixture_only: bool = False) -> None:
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

    # Keep the real snapshot as the default. The explicit fixture mode tests
    # runtime mechanics without asserting trust in the published snapshot.
    snapshot = Snapshot(ROOT / ("tests/fixtures/chat/site" if fixture_only else "site"))
    assert snapshot.version != "unavailable"
    _check_packaged_business_metrics_snapshot()
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
    assert not any(name == "src.analytics" or name.startswith("src.analytics.") for name in sys.modules)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--fixture-only",
        action="store_true",
        help="Test synthetic runtime mechanics only; does not validate the published snapshot.",
    )
    args = parser.parse_args(argv)
    asyncio.run(_check(fixture_only=args.fixture_only))
    scope = "fixture-only; published snapshot NOT checked" if args.fixture_only else "published snapshot"
    print(f"chat runtime smoke: ok ({scope}, auth, worker, compare_metrics; no provider calls)")


if __name__ == "__main__":
    main()
