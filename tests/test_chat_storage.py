from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
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


def test_deleted_running_turn_leaves_private_usage_tombstone_and_keeps_hold(tmp_path: Path):
    store = ChatStore(tmp_path / "chat.sqlite3")
    conversation = store.create_conversation("alice", "v1")
    turn, _ = store.submit_turn(
        "alice",
        conversation["id"],
        "private prompt",
        "c1",
        {},
        reserved_tokens=100,
        reserved_cost_usd=0.1,
    )
    store.claim_turn()
    assert store.request_cancel("alice", turn["id"]) == "cancelled"

    store.delete_conversation("alice", conversation["id"])

    assert store.usage("alice")["usage_incomplete_turns"] == 1
    assert store.usage("bob")["usage_incomplete_turns"] == 0
    with store._connect() as db:
        tombstone = db.execute("SELECT * FROM usage_tombstones WHERE turn_id=?", (turn["id"],)).fetchone()
        columns = {row[1] for row in db.execute("PRAGMA table_info(usage_tombstones)")}
        foreign_keys = db.execute("PRAGMA foreign_key_list(usage_tombstones)").fetchall()
    assert tombstone["status"] == "unknown"
    assert tombstone["reserved_tokens"] == 100
    assert tombstone["reserved_cost_usd"] == 0.1
    assert columns == {
        "turn_id",
        "owner_id",
        "usage_date",
        "reserved_tokens",
        "reserved_cost_usd",
        "status",
        "input_tokens",
        "output_tokens",
        "estimated_cost_usd",
    }
    assert foreign_keys == []
    bob = store.create_conversation("bob", "v1")
    admitted, _ = store.submit_turn(
        "bob",
        bob["id"],
        "new",
        "bob-1",
        {},
        reserved_tokens=1,
        user_token_budget=10,
        global_token_budget=200,
        user_cost_budget=1,
        global_cost_budget=10,
    )
    assert admitted["status"] == "pending"
    with pytest.raises(AdmissionDenied, match="daily token budget exhausted"):
        store.submit_turn(
            "alice",
            store.create_conversation("alice", "v1")["id"],
            "new",
            "c2",
            {},
            reserved_tokens=1,
            user_token_budget=100,
            global_token_budget=100,
        )


def test_late_usage_books_deleted_tombstone_once_and_releases_hold(tmp_path: Path):
    store = ChatStore(tmp_path / "chat.sqlite3")
    conversation = store.create_conversation("alice", "v1")
    turn, _ = store.submit_turn(
        "alice",
        conversation["id"],
        "private prompt",
        "c1",
        {},
        reserved_tokens=100,
        reserved_cost_usd=0.1,
    )
    store.claim_turn()
    assert store.complete_turn(turn["id"], "private answer", {}, 0, 0, 0.0, usage_complete=False)
    yesterday = "2000-01-01"
    with store._connect() as db:
        db.execute("UPDATE turns SET reserved_usage_date=? WHERE id=?", (yesterday, turn["id"]))
    store.delete_conversation("alice", conversation["id"])

    store.record_terminal_usage(turn["id"], 11, 4, 0.012)
    first = store.usage("alice")
    store.record_terminal_usage(turn["id"], 99, 99, 9.99)
    second = store.usage("alice")
    with store._connect() as db:
        tombstone = db.execute("SELECT * FROM usage_tombstones WHERE turn_id=?", (turn["id"],)).fetchone()
        booked = db.execute(
            "SELECT input_tokens,output_tokens,estimated_cost_usd,turn_count FROM usage_daily "
            "WHERE owner_id=? AND usage_date=?",
            ("alice", datetime.now(UTC).date().isoformat()),
        ).fetchone()
    assert first["usage_incomplete_turns"] == second["usage_incomplete_turns"] == 0
    assert first["input_tokens"] == second["input_tokens"] == 11
    assert first["output_tokens"] == second["output_tokens"] == 4
    assert first["turn_count"] == second["turn_count"] == 1
    assert tombstone["usage_date"] == yesterday
    assert tombstone["status"] == "booked"
    assert (tombstone["reserved_tokens"], tombstone["reserved_cost_usd"]) == (0, 0)
    assert (tombstone["input_tokens"], tombstone["output_tokens"], tombstone["estimated_cost_usd"]) == (
        11,
        4,
        0.012,
    )
    assert tuple(booked) == (11, 4, 0.012, 1)


def test_unresolved_holds_cross_utc_date_but_pending_cancel_never_becomes_usage(tmp_path: Path):
    store = ChatStore(tmp_path / "chat.sqlite3")
    alice = store.create_conversation("alice", "v1")
    pending, _ = store.submit_turn(
        "alice", alice["id"], "ask", "c1", {}, reserved_tokens=100, reserved_cost_usd=0.1
    )
    with store._connect() as db:
        db.execute("UPDATE turns SET reserved_usage_date='2000-01-01' WHERE id=?", (pending["id"],))
    assert store.usage("alice")["usage_incomplete_turns"] == 1
    bob = store.create_conversation("bob", "v1")
    with pytest.raises(AdmissionDenied, match="daily token budget exhausted"):
        store.submit_turn(
            "bob",
            bob["id"],
            "ask",
            "b1",
            {},
            reserved_tokens=1,
            user_token_budget=100,
            global_token_budget=100,
        )

    assert store.request_cancel("alice", pending["id"]) == "cancelled"
    assert store.get_turn("alice", pending["id"])["usage_complete"] == 1
    assert store.usage("alice")["usage_incomplete_turns"] == 0
    admitted, _ = store.submit_turn(
        "bob",
        bob["id"],
        "ask",
        "b1",
        {},
        reserved_tokens=1,
        user_token_budget=100,
        global_token_budget=100,
    )
    assert admitted["status"] == "pending"
    with store._connect() as db:
        assert db.execute("SELECT COUNT(*) FROM usage_tombstones").fetchone()[0] == 0


def test_retention_preserves_deleted_terminal_unknown_hold(tmp_path: Path):
    store = ChatStore(tmp_path / "chat.sqlite3")
    conversation = store.create_conversation("alice", "v1")
    turn, _ = store.submit_turn(
        "alice",
        conversation["id"],
        "private prompt",
        "c1",
        {},
        reserved_tokens=100,
        reserved_cost_usd=0.1,
    )
    store.claim_turn()
    assert store.complete_turn(turn["id"], "private answer", {}, 0, 0, 0.0, usage_complete=False)
    with store._connect() as db:
        db.execute(
            "UPDATE conversations SET updated_at='2000-01-01T00:00:00+00:00' WHERE id=?",
            (conversation["id"],),
        )

    assert store.cleanup_expired(30) == 1

    assert store.usage("alice")["usage_incomplete_turns"] == 1
    with pytest.raises(NotFound):
        store.get_turn("alice", turn["id"])
    with store._connect() as db:
        tombstone = db.execute("SELECT * FROM usage_tombstones WHERE turn_id=?", (turn["id"],)).fetchone()
    assert tombstone["status"] == "unknown"
    assert tombstone["reserved_tokens"] == 100
    with pytest.raises(AdmissionDenied, match="daily token budget exhausted"):
        store.submit_turn(
            "alice",
            store.create_conversation("alice", "v1")["id"],
            "new",
            "c2",
            {},
            reserved_tokens=1,
            user_token_budget=100,
            global_token_budget=100,
        )


def test_deleting_known_usage_keeps_daily_booking_without_unknown_tombstone(tmp_path: Path):
    store = ChatStore(tmp_path / "chat.sqlite3")
    conversation = store.create_conversation("alice", "v1")
    turn, _ = store.submit_turn("alice", conversation["id"], "ask", "c1", {})
    store.claim_turn()
    assert store.complete_turn(turn["id"], "answer", {}, 23, 4, 0.25, usage_complete=True)
    before = store.usage("alice")

    store.delete_conversation("alice", conversation["id"])
    store.record_terminal_usage(turn["id"], 999, 999, 99.0)

    after = store.usage("alice")
    assert after == before
    assert after["usage_incomplete_turns"] == 0
    with store._connect() as db:
        assert db.execute("SELECT COUNT(*) FROM usage_tombstones").fetchone()[0] == 0


def test_remote_session_deletion_retries_use_durable_backoff(tmp_path: Path):
    store = ChatStore(tmp_path / "chat.sqlite3")
    store.queue_provider_deletion("provider-session")
    assert store.pending_provider_deletions() == ["provider-session"]
    store.failed_provider_deletion("provider-session")
    assert store.pending_provider_deletions() == []


def test_retention_never_queues_remote_deletion_for_a_kept_conversation(tmp_path: Path):
    store = ChatStore(tmp_path / "chat.sqlite3")
    kept = store.create_conversation("alice", "v1")
    gone = store.create_conversation("alice", "v1")
    store.set_provider_session(kept["id"], "session-kept")
    store.set_provider_session(gone["id"], "session-gone")
    store.submit_turn("alice", kept["id"], "ask", "k1", {})
    with store._connect() as db:
        db.execute("UPDATE conversations SET updated_at='2000-01-01T00:00:00.000+00:00'")
    assert store.cleanup_expired(30) == 1
    assert store.pending_provider_deletions() == ["session-gone"]
    assert store.get_conversation("alice", kept["id"])["id"] == kept["id"]
