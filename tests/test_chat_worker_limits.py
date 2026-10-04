from __future__ import annotations

import threading
from pathlib import Path

from src.conversational_analytics.config import ChatConfig
from src.conversational_analytics.providers.base import ProviderResult
from src.conversational_analytics.service import ChatService
from src.conversational_analytics.storage import ChatStore
from src.conversational_analytics.worker import TurnWorker


class Snapshot:
    version = "snapshot-v1"
    semantic_version = "semantic-v1"

    def catalog(self):
        return {}


class Registry:
    def __init__(self, result):
        self.result = result
        self.invoked = 0

    def tool_specs(self):
        return [{"name": "query_metrics", "parameters": {}}]

    def invoke(self, name, args, context=None):
        assert name == "query_metrics"
        self.invoked += 1
        return self.result


class ToolCallingProvider:
    def __init__(self, calls):
        self.calls = calls
        self.cancelled = []
        self.deleted = []

    def run_turn(self, **kwargs):
        for index, arguments in enumerate(self.calls):
            kwargs["call_tool"]("provider-turn", f"call-{index}", "query_metrics", arguments)
        return ProviderResult("completado")

    def cancel(self, session_id):
        self.cancelled.append(session_id)

    def delete(self, session_id):
        self.deleted.append(session_id)


def _claimed_turn(store: ChatStore, key: str = "client-1"):
    conversation = store.create_conversation("alice", "snapshot-v1", "semantic-v1")
    turn, _ = store.submit_turn("alice", conversation["id"], "consulta", key, {})
    return conversation, turn, store.claim_turn()


def _worker(store, path, provider, *, max_tool_calls=5, max_result_bytes=16_000, max_seconds=2):
    worker = TurnWorker(
        store,
        ChatConfig(
            state_path=path,
            max_tool_calls=max_tool_calls,
            max_tool_result_bytes=max_result_bytes,
            max_turn_seconds=max_seconds,
        ),
        provider,
        Snapshot(),
    )
    return worker


def test_tool_call_limit_stops_dispatch_before_excess_tool_execution(tmp_path: Path):
    db = tmp_path / "chat.sqlite3"
    store = ChatStore(db)
    _, turn, claim = _claimed_turn(store)
    provider = ToolCallingProvider([{}, {}])
    worker = _worker(store, db, provider, max_tool_calls=1)
    registry = Registry({"rows": [{"value": 1}]})
    worker._registry = registry

    worker._execute_turn(claim)

    assert registry.invoked == 1
    assert store.get_turn("alice", turn["id"])["status"] == "failed"
    assert [event["type"] for event in store.list_events("alice", turn["id"])] == [
        "turn.queued",
        "turn.started",
        "turn.failed",
    ]


def test_tool_result_byte_limit_fails_turn_without_persisting_oversized_result(tmp_path: Path):
    db = tmp_path / "chat.sqlite3"
    store = ChatStore(db)
    _, turn, claim = _claimed_turn(store)
    provider = ToolCallingProvider([{}])
    worker = _worker(store, db, provider, max_result_bytes=128)
    registry = Registry({"rows": [{"value": "x" * 512}]})
    worker._registry = registry

    worker._execute_turn(claim)

    assert registry.invoked == 1
    assert store.get_tool_result(turn["id"], "call-0") is None
    assert store.get_turn("alice", turn["id"])["status"] == "failed"
    assert "turn.completed" not in [event["type"] for event in store.list_events("alice", turn["id"])]


class WaitUntilCancelledProvider(ToolCallingProvider):
    def __init__(self):
        super().__init__([])
        self.started = threading.Event()
        self.cancelled_event = threading.Event()

    def run_turn(self, **kwargs):
        kwargs["persist_session"]("provider-session")
        self.started.set()
        kwargs["cancel_event"].wait(timeout=2)
        raise InterruptedError("cancelled")

    def cancel(self, session_id):
        super().cancel(session_id)
        self.cancelled_event.set()


def test_worker_timeout_cancels_provider_and_writes_one_terminal_failure(tmp_path: Path):
    db = tmp_path / "chat.sqlite3"
    store = ChatStore(db)
    _, turn, claim = _claimed_turn(store)
    provider = WaitUntilCancelledProvider()
    worker = _worker(store, db, provider, max_seconds=0.05)
    worker._registry = Registry({"rows": []})
    thread = threading.Thread(target=worker._execute_turn, args=(claim,))
    thread.start()

    assert provider.started.wait(timeout=1)
    assert provider.cancelled_event.wait(timeout=1)
    thread.join(timeout=1)

    assert not thread.is_alive()
    record = store.get_turn("alice", turn["id"])
    assert (record["status"], record["error_code"]) == ("failed", "timeout")
    assert provider.cancelled == ["provider-session"]
    terminal = [
        event["type"]
        for event in store.list_events("alice", turn["id"])
        if event["type"] in {"turn.completed", "turn.failed", "turn.cancelled"}
    ]
    assert terminal == ["turn.failed"]


class RetryDeleteProvider:
    def __init__(self):
        self.delete_attempts = 0

    def delete(self, session_id):
        assert session_id == "provider-session"
        self.delete_attempts += 1
        if self.delete_attempts == 1:
            raise RuntimeError("temporary remote failure")

    def cancel(self, session_id):
        pass


def test_failed_manual_remote_delete_stays_queued_until_worker_retry_succeeds(tmp_path: Path):
    db = tmp_path / "chat.sqlite3"
    store = ChatStore(db)
    snapshot = Snapshot()
    provider = RetryDeleteProvider()
    service = ChatService(store, ChatConfig(state_path=db), snapshot, provider=provider)
    conversation = service.create_conversation("alice")
    store.set_provider_session(conversation["id"], "provider-session")

    service.delete_conversation("alice", conversation["id"])

    assert provider.delete_attempts == 1
    assert store.pending_provider_deletions() == ["provider-session"]
    with store._connect() as db_conn:
        queued = db_conn.execute(
            "SELECT session_id,attempts FROM provider_deletions WHERE session_id=?", ("provider-session",)
        ).fetchone()
        assert queued["attempts"] == 0

    worker = _worker(store, db, provider)
    worker._drain_provider_deletions()

    assert provider.delete_attempts == 2
    assert store.pending_provider_deletions() == []
    with store._connect() as db_conn:
        assert (
            db_conn.execute(
                "SELECT 1 FROM provider_deletions WHERE session_id=?", ("provider-session",)
            ).fetchone()
            is None
        )
