from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.conversational_analytics.storage import ChatStore


def failed_provider_turn(tmp_path: Path) -> tuple[ChatStore, dict, dict]:
    store = ChatStore(tmp_path / "chat.sqlite3")
    conversation = store.create_conversation("alice", "snapshot-v1", "semantic-v1")
    turn, _ = store.submit_turn("alice", conversation["id"], "private question", "client-1", {})
    assert store.claim_turn()
    store.set_provider_session(conversation["id"], "session-existing")
    store.set_provider_turn(turn["id"], "provider-turn-existing")
    store.fail_turn(turn["id"], "provider_error", "provider stream ended")
    return store, conversation, turn


def apply(store: ChatStore, conversation: dict, turn: dict) -> bool:
    return store.reconcile_failed_provider_turn(
        turn_id=turn["id"],
        owner_id="alice",
        conversation_id=conversation["id"],
        snapshot_version="snapshot-v1",
        semantic_version="semantic-v1",
        provider_session_id="session-existing",
        provider_turn_id="provider-turn-existing",
        content="Private recovered answer.",
        payload={"references": []},
        input_tokens=40,
        output_tokens=12,
        cost=0.00038,
    )


def test_reconcile_preserves_failure_and_books_known_usage_once(tmp_path: Path):
    store, conversation, turn = failed_provider_turn(tmp_path)

    assert apply(store, conversation, turn)
    assert not apply(store, conversation, turn)

    recovered = store.get_turn("alice", turn["id"])
    assert recovered["status"] == "completed"
    assert recovered["usage_complete"] == 1
    assert store.get_conversation("alice", conversation["id"])["messages"][-1]["content"] == (
        "Private recovered answer."
    )
    events = store.list_events("alice", turn["id"])
    assert [event["type"] for event in events][-4:] == [
        "turn.failed",
        "message.completed",
        "turn.completed",
        "turn.reconciled",
    ]
    assert store.usage("alice")["turn_count"] == 1


def test_reconcile_accepts_already_booked_matching_usage_without_duplicate(tmp_path: Path):
    store, conversation, turn = failed_provider_turn(tmp_path)
    store.record_terminal_usage(turn["id"], 40, 12, 0.00038)

    assert apply(store, conversation, turn)
    assert store.usage("alice")["turn_count"] == 1
    assert store.get_turn("alice", turn["id"])["usage_complete"] == 1


def test_reconcile_rolls_back_answer_and_usage_together_on_transaction_error(tmp_path: Path, monkeypatch):
    store, conversation, turn = failed_provider_turn(tmp_path)
    append = ChatStore._append_event_db

    def fail_before_commit(db, turn_id, event_type, payload):
        if event_type == "turn.reconciled":
            raise RuntimeError("injected write failure")
        return append(db, turn_id, event_type, payload)

    monkeypatch.setattr(ChatStore, "_append_event_db", staticmethod(fail_before_commit))
    with pytest.raises(RuntimeError, match="injected write failure"):
        apply(store, conversation, turn)

    assert store.get_turn("alice", turn["id"])["status"] == "failed"
    events = store.list_events("alice", turn["id"])
    assert [event["type"] for event in events][-1:] == ["turn.failed"]
    assert len(events) == 3
    assert store.usage("alice")["turn_count"] == 0
    monkeypatch.setattr(ChatStore, "_append_event_db", staticmethod(append))
    assert apply(store, conversation, turn)
    assert store.usage("alice")["turn_count"] == 1


def test_reconcile_rejects_nonrecoverable_provider_guard_event(tmp_path: Path):
    store, conversation, turn = failed_provider_turn(tmp_path)
    store.add_event(turn["id"], "provider.failure", {"reason_code": "turn_timeout"})

    assert not apply(store, conversation, turn)
    assert store.get_turn("alice", turn["id"])["status"] == "failed"


def test_reconcile_fences_same_millisecond_turn_with_lower_uuid(tmp_path: Path):
    store, conversation, turn = failed_provider_turn(tmp_path)
    created_at = store.get_turn("alice", turn["id"])["created_at"]
    lower_id = "00000000-0000-4000-8000-000000000000"
    with store._connect() as db:
        db.execute(
            "INSERT INTO turns(id,conversation_id,owner_id,client_message_id,status,user_content,"
            "context_json,created_at) VALUES(?,?,?,?,'failed',?,?,?)",
            (lower_id, conversation["id"], "alice", "client-later", "later", "{}", created_at),
        )

    assert lower_id < turn["id"]
    assert store.turn_reconciliation_metadata("alice", turn["id"])["has_later_turn"]
    assert not apply(store, conversation, turn)


def test_reconcile_fences_unknown_identity_later_turn_and_concurrent_apply(tmp_path: Path):
    store, conversation, turn = failed_provider_turn(tmp_path)
    wrong = store.reconcile_failed_provider_turn(
        turn_id=turn["id"],
        owner_id="bob",
        conversation_id=conversation["id"],
        snapshot_version="snapshot-v1",
        semantic_version="semantic-v1",
        provider_session_id="session-existing",
        provider_turn_id="provider-turn-existing",
        content="Private recovered answer.",
        payload={},
        input_tokens=40,
        output_tokens=12,
        cost=0.00038,
    )
    assert not wrong
    assert store.get_turn("alice", turn["id"])["status"] == "failed"

    later, _ = store.submit_turn("alice", conversation["id"], "later", "client-2", {})
    assert later["status"] == "pending"
    assert not apply(store, conversation, turn)
    assert store.get_turn("alice", turn["id"])["status"] == "failed"

    store2, conversation2, turn2 = failed_provider_turn(tmp_path / "parallel")
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: apply(store2, conversation2, turn2), range(2)))
    assert sorted(results) == [False, True]
    assert store2.usage("alice")["turn_count"] == 1


def test_cli_dry_run_reads_only_sanitized_metadata(tmp_path: Path, monkeypatch, capsys):
    from scripts.chat.reconcile_failed_turn import run

    store, _, turn = failed_provider_turn(tmp_path)
    monkeypatch.setenv("CHAT_STATE_PATH", str(store.path))
    monkeypatch.setenv("CHAT_PROVIDER", "mock")
    monkeypatch.delenv("CHAT_OPENAI_ENABLED", raising=False)

    assert run(["--turn-id", turn["id"], "--owner-id", "alice"]) == 0

    output = capsys.readouterr().out
    plan = json.loads(output)
    assert plan["mode"] == "dry_run"
    assert plan["eligible_by_local_metadata"] is True
    assert plan["planned_provider_requests"] == {
        "turn_gets": 1,
        "turn_get_timeout_seconds": 30,
        "item_get_pages": {"minimum": 1, "maximum": 10, "read_window_seconds": 30},
        "total_bounded_seconds": 60,
        "estimated_units": {
            "minimum": 2,
            "maximum": 11,
            "unit": "read-only GET requests",
            "model_generations": 0,
            "provider_inputs_sent": False,
        },
    }
    assert plan["write_destinations"] == [str(store.path.resolve())]
    assert plan["database_writes"] == 0
    assert plan["provider_calls"] == 0
    assert "Private recovered answer" not in output
    assert turn["id"] not in output
    assert store.get_turn("alice", turn["id"])["status"] == "failed"


def test_exact_sdk_recovery_reads_only_final_answer_and_existing_items():
    from scripts.chat.reconcile_failed_turn import _recover_exact

    class Turns:
        def __init__(self):
            self.calls = []

        def retrieve(self, turn_id, *, session_id, timeout):
            self.calls.append((turn_id, session_id))
            return {
                "id": turn_id,
                "session_id": session_id,
                "status": "completed",
                "usage": {"input_tokens": 21, "output_tokens": 5, "total_tokens": 26},
            }

    class Items:
        calls = []

        def list(self, session_id, **kwargs):
            self.calls.append((session_id, kwargs))
            return SimpleNamespace(
                has_more=False,
                data=[
                    {
                        "id": "item-analysis",
                        "type": "message",
                        "role": "assistant",
                        "turn_id": "turn-exact",
                        "phase": "analysis",
                        "status": "completed",
                        "content": [{"type": "output_text", "text": "hidden reasoning"}],
                    },
                    {
                        "id": "item-final",
                        "type": "message",
                        "role": "assistant",
                        "turn_id": "turn-exact",
                        "phase": "final_answer",
                        "status": "completed",
                        "content": [{"type": "output_text", "text": "Canonical answer."}],
                    },
                    {
                        "id": "item-call",
                        "type": "function_call",
                        "turn_id": "turn-exact",
                        "call_id": "call-existing",
                        "name": "query_metrics",
                        "arguments": {"periods": ["2026Q2"]},
                    },
                ],
            )

    turns, items = Turns(), Items()
    provider = SimpleNamespace(
        client=SimpleNamespace(
            beta=SimpleNamespace(agents=SimpleNamespace(sessions=SimpleNamespace(turns=turns, items=items)))
        )
    )
    content, input_tokens, output_tokens, calls = _recover_exact(provider, "session-exact", "turn-exact")
    assert content == "Canonical answer."
    assert (input_tokens, output_tokens) == (21, 5)
    assert calls == [
        {
            "call_id": "call-existing",
            "tool_name": "query_metrics",
            "arguments": {"periods": ["2026Q2"]},
        }
    ]
    assert turns.calls == [("turn-exact", "session-exact")]
    assert items.calls[0][0] == "session-exact"
    assert items.calls[0][1]["limit"] == 100
    assert items.calls[0][1]["order"] == "desc"
    assert items.calls[0][1]["timeout"] <= 5


def test_exact_sdk_recovery_rejects_mismatch_and_truncated_item_page():
    from scripts.chat.reconcile_failed_turn import _recover_exact

    class Turns:
        def retrieve(self, turn_id, *, session_id, timeout):
            return {
                "id": "different-turn",
                "session_id": session_id,
                "status": "completed",
                "usage": {"input_tokens": 1, "output_tokens": 1, "total_tokens": 2},
            }

    provider = SimpleNamespace(
        client=SimpleNamespace(
            beta=SimpleNamespace(agents=SimpleNamespace(sessions=SimpleNamespace(turns=Turns())))
        )
    )
    with pytest.raises(ValueError):
        _recover_exact(provider, "session-exact", "turn-exact")

    class MatchingTurns:
        def retrieve(self, turn_id, *, session_id, timeout):
            return {
                "id": turn_id,
                "session_id": session_id,
                "status": "completed",
                "usage": {"input_tokens": 1, "output_tokens": 1, "total_tokens": 2},
            }

    class TruncatedItems:
        def list(self, session_id, **_kwargs):
            return SimpleNamespace(has_more=True, data=[])

    truncated = SimpleNamespace(
        client=SimpleNamespace(
            beta=SimpleNamespace(
                agents=SimpleNamespace(
                    sessions=SimpleNamespace(turns=MatchingTurns(), items=TruncatedItems())
                )
            )
        )
    )
    with pytest.raises(ValueError):
        _recover_exact(truncated, "session-exact", "turn-exact")


def test_exact_sdk_recovery_uses_paginated_items_for_final_and_tool_calls():
    from scripts.chat.reconcile_failed_turn import _recover_exact

    class Turns:
        def retrieve(self, turn_id, *, session_id, timeout):
            return {
                "id": turn_id,
                "session_id": session_id,
                "status": "completed",
                "usage": {"input_tokens": 30, "output_tokens": 8, "total_tokens": 38},
            }

    class Items:
        calls = []

        def list(self, session_id, *, limit, order, timeout, after=None):
            self.calls.append(after)
            if after is None:
                return SimpleNamespace(
                    has_more=True,
                    data=[
                        {
                            "id": "item-final",
                            "type": "message",
                            "role": "assistant",
                            "turn_id": "turn-exact",
                            "phase": "final_answer",
                            "status": "completed",
                            "content": [{"type": "output_text", "text": "Paginated answer."}],
                        }
                    ],
                )
            return SimpleNamespace(
                has_more=True,
                data=[
                    {
                        "id": "item-call",
                        "type": "function_call",
                        "turn_id": "turn-exact",
                        "call_id": "call-existing",
                        "name": "query_metrics",
                        "arguments": {"periods": ["2026Q2"]},
                    },
                    {
                        "id": "item-old",
                        "type": "message",
                        "role": "assistant",
                        "turn_id": "turn-old",
                    },
                ],
            )

    items = Items()
    provider = SimpleNamespace(
        client=SimpleNamespace(
            beta=SimpleNamespace(
                agents=SimpleNamespace(sessions=SimpleNamespace(turns=Turns(), items=items))
            )
        )
    )
    content, input_tokens, output_tokens, calls = _recover_exact(provider, "session-exact", "turn-exact")
    assert content == "Paginated answer."
    assert (input_tokens, output_tokens) == (30, 8)
    assert calls[0]["call_id"] == "call-existing"
    assert items.calls == [None, "item-final"]


def test_recovery_accepts_multipart_final_in_chronological_order_and_counts_gets():
    from scripts.chat.reconcile_failed_turn import _counting_provider, _recover_exact

    class Turns:
        def retrieve(self, turn_id, *, session_id, timeout):
            return {
                "id": turn_id,
                "session_id": session_id,
                "status": "completed",
                "usage": {"input_tokens": 3, "output_tokens": 2, "total_tokens": 5},
            }

    class Items:
        def __init__(self):
            self.calls = []

        def list(self, session_id, *, after=None, **kwargs):
            self.calls.append(after)
            if after is None:
                return SimpleNamespace(has_more=True, data=[
                    {"id": "part-2", "type": "message", "role": "assistant", "turn_id": "t",
                     "phase": "final_answer", "status": "completed", "content": [
                         {"type": "output_text", "text": " second"}]},
                    {"id": "comment", "type": "message", "role": "assistant", "turn_id": "t",
                     "phase": "commentary", "status": "completed", "content": [
                         {"type": "output_text", "text": " excluded"}]},
                ])
            return SimpleNamespace(has_more=False, data=[
                {"id": "part-1", "type": "message", "role": "assistant", "turn_id": "t",
                 "phase": "final_answer", "status": "completed", "content": [
                     {"type": "output_text", "text": "First"}]},
                {"id": "older", "type": "message", "role": "assistant", "turn_id": "previous"},
            ])

    items = Items()
    provider = SimpleNamespace(client=SimpleNamespace(beta=SimpleNamespace(agents=SimpleNamespace(
        sessions=SimpleNamespace(turns=Turns(), items=items)))))
    count = [0]
    result = _recover_exact(_counting_provider(provider, count), "s", "t")
    assert result[0] == "First second"
    assert count == [3]  # one exact-turn GET and two item-page GETs
    assert items.calls == [None, "comment"]


def test_recovery_legacy_phase_none_uses_only_last_completed_assistant_message():
    from scripts.chat.reconcile_failed_turn import _recover_exact

    class Turns:
        def retrieve(self, turn_id, *, session_id, timeout):
            return {"id": turn_id, "session_id": session_id, "status": "completed",
                    "usage": {"input_tokens": 1, "output_tokens": 1, "total_tokens": 2}}

    class Items:
        def list(self, session_id, **kwargs):
            return SimpleNamespace(has_more=False, data=[
                {"id": "legacy-final", "type": "message", "role": "assistant", "turn_id": "t",
                 "status": "completed", "content": [
                     {"type": "output_text", "text": "Legacy result"}]},
                {"id": "analysis", "type": "message", "role": "assistant", "turn_id": "t",
                 "phase": "analysis", "status": "completed", "content": [
                     {"type": "output_text", "text": "secret reasoning"}]},
            ])

    provider = SimpleNamespace(client=SimpleNamespace(beta=SimpleNamespace(agents=SimpleNamespace(
        sessions=SimpleNamespace(turns=Turns(), items=Items())))))
    assert _recover_exact(provider, "s", "t")[0] == "Legacy result"


def test_recovered_answer_obeys_configured_worker_output_limit():
    from scripts.chat.reconcile_failed_turn import _validate_recovered_content

    _validate_recovered_content("x" * 40, max_message_chars=10)
    with pytest.raises(ValueError, match="provider-output limit"):
        _validate_recovered_content("x" * 41, max_message_chars=10)

