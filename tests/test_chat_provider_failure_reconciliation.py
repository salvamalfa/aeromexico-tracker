from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from src.conversational_analytics.config import ChatConfig
from src.conversational_analytics.providers.openai import OpenAIProviderError
from src.conversational_analytics.storage import ChatStore
from src.conversational_analytics.worker import TurnWorker


def _run_declared_terminal_failure(tmp_path: Path, usage: tuple[int, int] | None):
    class Provider:
        def run_turn(self, **kwargs):
            kwargs["persist_session"]("session-private-terminal")
            kwargs["emit"]("provider.metadata", {"provider_turn_id": "turn-private-terminal"})
            error_args = {"usage": usage} if usage is not None else {}
            raise OpenAIProviderError(
                "private provider failure details",
                **error_args,
                reason_code="provider_terminal_failed",
                session_id="session-private-terminal",
                turn_id="turn-private-terminal",
            )

    state_path = tmp_path / "chat.sqlite3"
    store = ChatStore(state_path)
    conversation = store.create_conversation("alice", "snapshot-v1", "semantic-v1")
    turn, _ = store.submit_turn("alice", conversation["id"], "ask", "client-1", {})
    claim = store.claim_turn()
    worker = TurnWorker(
        store,
        ChatConfig(state_path=state_path, provider="openai"),
        Provider(),
        SimpleNamespace(version="snapshot-v1", semantic_version="semantic-v1", catalog=lambda: {}),
    )
    worker._registry = SimpleNamespace(tool_specs=lambda: [])
    worker._execute_turn(claim)
    return store, conversation, turn


def test_declared_terminal_failure_blocks_cli_recovery_and_keeps_confirmed_usage(
    tmp_path: Path, monkeypatch, capsys
):
    from scripts.chat.reconcile_failed_turn import run

    store, conversation, turn = _run_declared_terminal_failure(tmp_path, (900, 40))
    record = store.get_turn("alice", turn["id"])
    assert record["status"] == "failed"
    assert record["error_code"] == "provider_error"
    assert (
        record["usage_complete"],
        record["estimated_input_tokens"],
        record["estimated_output_tokens"],
    ) == (
        1,
        900,
        40,
    )
    failure = next(
        event for event in store.list_events("alice", turn["id"]) if event["type"] == "provider.failure"
    )
    assert failure["data"] == {"reason_code": "provider_terminal_failed"}
    assert "private provider failure details" not in str(store.list_events("alice", turn["id"]))
    assert store.turn_reconciliation_metadata("alice", turn["id"])["has_cancel_or_timeout_event"]

    monkeypatch.setenv("CHAT_STATE_PATH", str(store.path))
    monkeypatch.setenv("CHAT_PROVIDER", "openai")
    monkeypatch.setenv("CHAT_OPENAI_ENABLED", "true")
    assert run(["--turn-id", turn["id"], "--owner-id", "alice"]) == 0
    plan = json.loads(capsys.readouterr().out)
    assert plan["eligible_by_local_metadata"] is False
    assert plan["provider_calls"] == 0
    assert (
        run(
            [
                "--turn-id",
                turn["id"],
                "--owner-id",
                "alice",
                "--apply",
                "--conversation-id",
                conversation["id"],
                "--provider-session-id",
                "session-private-terminal",
                "--provider-turn-id",
                "turn-private-terminal",
                "--snapshot-version",
                "snapshot-v1",
                "--semantic-version",
                "semantic-v1",
            ]
        )
        == 2
    )
    assert "eligibility or recovery check failed" in capsys.readouterr().err
    assert not store.reconcile_failed_provider_turn(
        turn_id=turn["id"],
        owner_id="alice",
        conversation_id=conversation["id"],
        snapshot_version="snapshot-v1",
        semantic_version="semantic-v1",
        provider_session_id="session-private-terminal",
        provider_turn_id="turn-private-terminal",
        content="A later provider GET might say completed.",
        payload={},
        input_tokens=900,
        output_tokens=40,
        cost=0.00038,
    )
    assert store.get_turn("alice", turn["id"])["status"] == "failed"


def test_declared_terminal_failure_without_usage_stays_unknown(tmp_path: Path):
    store, _, turn = _run_declared_terminal_failure(tmp_path, None)
    record = store.get_turn("alice", turn["id"])
    assert record["status"] == "failed"
    assert record["usage_complete"] == 0
    assert store.usage("alice")["input_tokens"] == 0
    assert store.usage("alice")["output_tokens"] == 0
