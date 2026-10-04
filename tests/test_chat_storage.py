from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from src.conversational_analytics.storage import AdmissionDenied, ChatStore, Conflict, NotFound


def test_owner_scope_dedup_replay_and_tool_call_are_durable(tmp_path: Path):
    db = tmp_path / "chat.sqlite3"
    store = ChatStore(db)
    conversation = store.create_conversation("alice", "data-v1", "semantic-v1")
    turn, duplicate = store.submit_turn("alice", conversation["id"], "ask", "client-1", {})
    again, was_duplicate = store.submit_turn("alice", conversation["id"], "ask", "client-1", {})
    assert not duplicate and was_duplicate
    assert again["id"] == turn["id"]
    with pytest.raises(Conflict, match="different content"):
        store.submit_turn("alice", conversation["id"], "different", "client-1", {})
    with pytest.raises(NotFound):
        store.get_conversation("bob", conversation["id"])
    with pytest.raises(AdmissionDenied):
        store.submit_turn("alice", conversation["id"], "next", "client-2", {})

    claimed = store.claim_turn()
    assert claimed and claimed["id"] == turn["id"]
    seq = store.add_event(turn["id"], "message.delta", {"text": "part"})
    assert seq == 3
    assert [e["seq"] for e in store.list_events("alice", turn["id"], after=1)] == [2, 3]
    claimed_tool, _ = store.begin_tool_call(turn["id"], "call-1", "query_metrics", "provider-turn-1")
    assert claimed_tool
    store.save_tool_result(
        turn["id"], "call-1", "query_metrics", {"periods": ["2026Q2"]}, {"rows": []}, "provider-turn-1"
    )
    assert store.get_tool_result(
        turn["id"], "call-1", "query_metrics", {"periods": ["2026Q2"]}, "provider-turn-1"
    ) == {"rows": []}
    assert store.begin_tool_call(turn["id"], "call-1", "query_metrics", "provider-turn-1")[1] == {"rows": []}
    assert store.begin_tool_call(turn["id"], "call-unresolved", "query_metrics", "provider-turn-1")[0]
    with pytest.raises(Conflict, match="ambiguous"):
        store.begin_tool_call(turn["id"], "call-unresolved", "query_metrics", "provider-turn-1")

    reopened = ChatStore(db)
    assert [e["seq"] for e in reopened.list_events("alice", turn["id"], after=0)] == [1, 2, 3]
    assert reopened.get_conversation("alice", conversation["id"])["snapshot_version"] == "data-v1"


def test_concurrent_admission_uses_atomic_daily_reservations(tmp_path: Path):
    store = ChatStore(tmp_path / "chat.sqlite3")
    a = store.create_conversation("alice", "v1")
    b = store.create_conversation("bob", "v1")
    barrier = threading.Barrier(2)

    def attempt(owner: str, conversation_id: str, key: str) -> str:
        barrier.wait()
        try:
            store.submit_turn(
                owner,
                conversation_id,
                "ask",
                key,
                {},
                reserved_tokens=80,
                reserved_cost_usd=0.8,
                user_token_budget=100,
                global_token_budget=100,
                user_cost_budget=1,
                global_cost_budget=1,
            )
        except AdmissionDenied:
            return "denied"
        return "admitted"

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(attempt, ("alice", "bob"), (a["id"], b["id"]), ("a1", "b1")))
    assert sorted(results) == ["admitted", "denied"]


def test_running_turn_recovery_is_terminal_and_never_reclaimed(tmp_path: Path):
    store = ChatStore(tmp_path / "chat.sqlite3")
    conv = store.create_conversation("alice", "v1")
    turn, _ = store.submit_turn("alice", conv["id"], "ask", "a1", {})
    store.claim_turn()
    store.set_provider_session(conv["id"], "provider-session")
    interrupted = store.recover_interrupted()
    assert interrupted == [{"id": turn["id"], "provider_session_id": "provider-session"}]
    assert store.get_turn("alice", turn["id"])["status"] == "failed"
    assert store.claim_turn() is None


def test_pending_cancel_releases_reservation_but_running_cancel_keeps_uncertain_hold(tmp_path: Path):
    store = ChatStore(tmp_path / "chat.sqlite3")
    conv = store.create_conversation("alice", "v1")
    pending, _ = store.submit_turn(
        "alice", conv["id"], "ask", "a1", {}, reserved_tokens=10, reserved_cost_usd=0.2
    )
    assert store.request_cancel("alice", pending["id"]) == "cancelled"
    assert store.get_turn("alice", pending["id"])["reserved_tokens"] == 0


def test_remote_session_deletion_retries_use_durable_backoff(tmp_path: Path):
    store = ChatStore(tmp_path / "chat.sqlite3")
    store.queue_provider_deletion("provider-session")
    assert store.pending_provider_deletions() == ["provider-session"]
    store.failed_provider_deletion("provider-session")
    assert store.pending_provider_deletions() == []
