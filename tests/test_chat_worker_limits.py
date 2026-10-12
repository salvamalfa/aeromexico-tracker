from __future__ import annotations

import threading
from pathlib import Path

import pytest

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


def _claimed_turn(store: ChatStore, key: str = "client-1", *, reserved_tokens: int = 0):
    conversation = store.create_conversation("alice", "snapshot-v1", "semantic-v1", provider="mock")
    turn, _ = store.submit_turn(
        "alice",
        conversation["id"],
        "consulta",
        key,
        {},
        provider="mock",
        reserved_tokens=reserved_tokens,
        user_token_budget=max(100_000, reserved_tokens),
    )
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


def test_worker_boundary_stops_ninth_tool_dispatch_at_eight(tmp_path: Path):
    db = tmp_path / "worker-tool-limit-eight.sqlite3"
    store = ChatStore(db)
    _, turn, claim = _claimed_turn(store)
    provider = ToolCallingProvider([{} for _ in range(9)])
    worker = _worker(store, db, provider, max_tool_calls=8)
    registry = Registry({"rows": [{"value": 1}]})
    worker._registry = registry

    worker._execute_turn(claim)

    assert registry.invoked == 8
    assert store.get_turn("alice", turn["id"])["status"] == "failed"


def test_terminal_usage_window_does_not_extend_provider_execution_or_drop_completed_answer(tmp_path: Path):
    class CompletedButDelayedProvider(ToolCallingProvider):
        supports_terminal_usage_reconciliation = True

        def run_turn(self, **kwargs):
            kwargs["mark_terminal_completed"]()
            # Simulate a bounded post-terminal usage read that crosses the
            # execution deadline. The worker must keep the result and its hold.
            assert kwargs["cancel_event"].wait(timeout=0.06) is False
            return ProviderResult("terminal answer", usage_complete=False)

    db = tmp_path / "terminal-usage-window.sqlite3"
    store = ChatStore(db)
    _, turn, claim = _claimed_turn(store, reserved_tokens=150_000)
    provider = CompletedButDelayedProvider([])
    worker = _worker(store, db, provider, max_seconds=0.02)
    worker._registry = Registry({})

    worker._execute_turn(claim)

    record = store.get_turn("alice", turn["id"])
    assert record["status"] == "completed"
    assert not record["usage_complete"]
    assert record["reserved_tokens"] >= 150_000


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


class ReturnUsageWhenCancelledProvider(WaitUntilCancelledProvider):
    def run_turn(self, **kwargs):
        kwargs["persist_session"]("provider-session")
        self.started.set()
        kwargs["cancel_event"].wait(timeout=2)
        return ProviderResult(
            "resultado tardío",
            input_tokens=123,
            output_tokens=17,
            usage_complete=True,
        )


class SlowCancelProvider(ToolCallingProvider):
    def __init__(self):
        super().__init__([])
        self.started = threading.Event()
        self.cancel_started = threading.Event()
        self.cancel_release = threading.Event()
        self.cancel_finished = threading.Event()
        self.calls = 0

    def run_turn(self, **kwargs):
        self.calls += 1
        if self.calls == 1:
            kwargs["persist_session"]("provider-session")
            self.started.set()
            kwargs["cancel_event"].wait(timeout=2)
        else:
            assert self.cancel_finished.is_set()
        return ProviderResult("respuesta")

    def cancel(self, session_id):
        self.cancelled.append(session_id)
        self.cancel_started.set()
        assert self.cancel_release.wait(timeout=2)
        self.cancel_finished.set()


class LateSessionDiscoveryProvider(ToolCallingProvider):
    def __init__(self):
        super().__init__([])
        self.started = threading.Event()
        self.allow_discovery = threading.Event()
        self.cancel_started = threading.Event()
        self.cancel_release = threading.Event()
        self.cancel_finished = threading.Event()
        self.calls = 0

    def run_turn(self, **kwargs):
        self.calls += 1
        if self.calls == 1:
            self.started.set()
            assert self.allow_discovery.wait(timeout=2)
            kwargs["persist_session"]("late-provider-session")
            kwargs["emit"](
                "provider.metadata",
                {
                    "provider_turn_id": "late-provider-turn",
                    "provider_event_id": "late-event",
                    "provider_event_type": "agent.session.created",
                },
            )
            kwargs["emit"]("message.delta", {"text": "contenido posterior al terminal"})
            raise InterruptedError("cancelled")
        assert kwargs["session_id"] == "late-provider-session"
        assert self.cancel_finished.is_set()
        return ProviderResult("segunda consulta", input_tokens=10, output_tokens=2, usage_complete=True)

    def cancel(self, session_id):
        self.cancelled.append(session_id)
        self.cancel_started.set()
        assert self.cancel_release.wait(timeout=2)
        self.cancel_finished.set()


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


@pytest.mark.parametrize("terminal_status", ["timeout", "cancelled"])
def test_late_provider_result_books_known_usage_once_without_completing_turn(
    tmp_path: Path, terminal_status: str
):
    db = tmp_path / f"chat-{terminal_status}.sqlite3"
    store = ChatStore(db)
    _, turn, claim = _claimed_turn(store, key=f"client-{terminal_status}")
    provider = ReturnUsageWhenCancelledProvider()
    worker = _worker(store, db, provider, max_seconds=0.05 if terminal_status == "timeout" else 2)
    worker._registry = Registry({"rows": []})
    thread = threading.Thread(target=worker._execute_turn, args=(claim,))
    thread.start()

    assert provider.started.wait(timeout=1)
    if terminal_status == "cancelled":
        assert store.request_cancel("alice", turn["id"]) == "cancelled"
        worker.cancel(turn["id"])
    assert provider.cancelled_event.wait(timeout=1)
    thread.join(timeout=1)

    assert not thread.is_alive()
    record = store.get_turn("alice", turn["id"])
    assert record["status"] == ("failed" if terminal_status == "timeout" else "cancelled")
    assert record["error_code"] == terminal_status
    usage = store.usage("alice")
    assert (usage["input_tokens"], usage["output_tokens"], usage["turn_count"]) == (123, 17, 1)
    assert usage["usage_incomplete_turns"] == 0
    events = [event["type"] for event in store.list_events("alice", turn["id"])]
    assert "message.completed" not in events
    assert events.count("turn.failed") + events.count("turn.cancelled") == 1


def test_next_turn_waits_for_timeout_provider_cancel_to_drain(tmp_path: Path):
    db = tmp_path / "chat.sqlite3"
    store = ChatStore(db)
    conversation = store.create_conversation("alice", "snapshot-v1", "semantic-v1", provider="mock")
    store.submit_turn("alice", conversation["id"], "primera", "client-1", {}, provider="mock")
    first_claim = store.claim_turn()
    provider = SlowCancelProvider()
    worker = _worker(store, db, provider, max_seconds=0.05)
    worker._registry = Registry({"rows": []})
    first_thread = threading.Thread(target=worker._execute_turn, args=(first_claim,))
    first_thread.start()

    assert provider.started.wait(timeout=1)
    assert provider.cancel_started.wait(timeout=1)
    first_thread.join(timeout=0.1)
    assert first_thread.is_alive()

    store.submit_turn("alice", conversation["id"], "segunda", "client-2", {}, provider="mock")
    provider.cancel_release.set()
    first_thread.join(timeout=1)
    assert not first_thread.is_alive()
    second_claim = store.claim_turn()
    assert second_claim is not None
    worker._execute_turn(second_claim)

    assert provider.cancel_finished.is_set()
    assert provider.calls == 2
    assert store.get_turn("alice", first_claim["id"])["error_code"] == "timeout"
    assert store.get_turn("alice", second_claim["id"])["status"] == "completed"


def test_next_turn_waits_for_explicit_provider_cancel_to_drain(tmp_path: Path):
    db = tmp_path / "chat.sqlite3"
    store = ChatStore(db)
    conversation = store.create_conversation("alice", "snapshot-v1", "semantic-v1", provider="mock")
    store.submit_turn("alice", conversation["id"], "primera", "client-1", {}, provider="mock")
    first_claim = store.claim_turn()
    provider = SlowCancelProvider()
    worker = _worker(store, db, provider, max_seconds=2)
    worker._registry = Registry({"rows": []})
    first_thread = threading.Thread(target=worker._execute_turn, args=(first_claim,))
    first_thread.start()

    assert provider.started.wait(timeout=1)
    assert store.request_cancel("alice", first_claim["id"]) == "cancelled"
    cancel_thread = threading.Thread(target=worker.cancel, args=(first_claim["id"],))
    cancel_thread.start()
    assert provider.cancel_started.wait(timeout=1)
    first_thread.join(timeout=0.1)
    assert first_thread.is_alive()

    store.submit_turn("alice", conversation["id"], "segunda", "client-2", {}, provider="mock")
    provider.cancel_release.set()
    cancel_thread.join(timeout=1)
    first_thread.join(timeout=1)
    assert not cancel_thread.is_alive()
    assert not first_thread.is_alive()
    second_claim = store.claim_turn()
    assert second_claim is not None
    worker._execute_turn(second_claim)

    assert provider.cancel_finished.is_set()
    assert provider.calls == 2
    assert store.get_turn("alice", second_claim["id"])["status"] == "completed"


def test_watchdog_does_not_cancel_session_after_turn_completed(tmp_path: Path):
    db = tmp_path / "chat.sqlite3"
    store = ChatStore(db)
    _, turn, claim = _claimed_turn(store)
    provider = ToolCallingProvider([])
    worker = _worker(store, db, provider, max_seconds=0.05)
    worker._registry = Registry({"rows": []})
    timeout_attempted = threading.Event()
    original_fail_turn = store.fail_turn
    original_complete_turn = store.complete_turn

    def observe_timeout_attempt(turn_id, code, message, usage=None):
        result = original_fail_turn(turn_id, code, message, usage)
        timeout_attempted.set()
        return result

    def wait_for_watchdog(*args, **kwargs):
        result = original_complete_turn(*args, **kwargs)
        assert timeout_attempted.wait(timeout=1)
        return result

    store.fail_turn = observe_timeout_attempt
    store.complete_turn = wait_for_watchdog
    worker._execute_turn(claim)

    assert store.get_turn("alice", turn["id"])["status"] == "completed"
    assert provider.cancelled == []


def test_late_explicit_cancel_does_not_cancel_completed_session(tmp_path: Path):
    db = tmp_path / "chat.sqlite3"
    store = ChatStore(db)
    _, turn, claim = _claimed_turn(store)
    provider = ToolCallingProvider([])
    worker = _worker(store, db, provider, max_seconds=2)
    worker._registry = Registry({"rows": []})
    completed = threading.Event()
    allow_return = threading.Event()
    original_complete_turn = store.complete_turn

    def hold_after_completion(*args, **kwargs):
        result = original_complete_turn(*args, **kwargs)
        completed.set()
        assert allow_return.wait(timeout=1)
        return result

    store.complete_turn = hold_after_completion
    thread = threading.Thread(target=worker._execute_turn, args=(claim,))
    thread.start()
    assert completed.wait(timeout=1)

    worker.cancel(turn["id"])
    allow_return.set()
    thread.join(timeout=1)

    assert not thread.is_alive()
    assert store.get_turn("alice", turn["id"])["status"] == "completed"
    assert provider.cancelled == []


@pytest.mark.parametrize("terminal_status", ["cancelled", "timeout"])
def test_terminal_during_session_creation_cancels_late_session_and_drains(
    tmp_path: Path, terminal_status: str
):
    db = tmp_path / f"late-session-{terminal_status}.sqlite3"
    store = ChatStore(db)
    conversation = store.create_conversation("alice", "snapshot-v1", "semantic-v1", provider="mock")
    store.submit_turn("alice", conversation["id"], "primera", "client-1", {}, provider="mock")
    first_claim = store.claim_turn()
    provider = LateSessionDiscoveryProvider()
    worker = _worker(store, db, provider, max_seconds=0.05 if terminal_status == "timeout" else 2)
    worker._registry = Registry({"rows": []})
    timeout_written = threading.Event()
    original_fail_turn = store.fail_turn

    def observe_timeout(turn_id, code, message, usage=None):
        result = original_fail_turn(turn_id, code, message, usage)
        if code == "timeout":
            timeout_written.set()
        return result

    store.fail_turn = observe_timeout
    first_thread = threading.Thread(target=worker._execute_turn, args=(first_claim,))
    first_thread.start()
    assert provider.started.wait(timeout=1)

    if terminal_status == "cancelled":
        assert store.request_cancel("alice", first_claim["id"]) == "cancelled"
        worker.cancel(first_claim["id"])
    else:
        assert timeout_written.wait(timeout=1)
    provider.allow_discovery.set()
    assert provider.cancel_started.wait(timeout=1)
    first_thread.join(timeout=0.1)
    assert first_thread.is_alive()

    first_record = store.get_turn("alice", first_claim["id"])
    assert first_record["status"] == ("cancelled" if terminal_status == "cancelled" else "failed")
    assert first_record["error_code"] == terminal_status
    assert first_record["provider_turn_id"] == "late-provider-turn"
    assert first_record["provider_event_id"] == "late-event"
    assert store.usage("alice")["usage_incomplete_turns"] == 1
    event_types = [event["type"] for event in store.list_events("alice", first_claim["id"])]
    assert "message.delta" not in event_types
    assert "provider.metadata" not in event_types

    store.submit_turn("alice", conversation["id"], "segunda", "client-2", {}, provider="mock")
    provider.cancel_release.set()
    first_thread.join(timeout=1)
    assert not first_thread.is_alive()
    assert provider.cancelled == ["late-provider-session"]
    second_claim = store.claim_turn()
    assert second_claim is not None
    worker._execute_turn(second_claim)

    assert provider.calls == 2
    assert store.get_turn("alice", second_claim["id"])["status"] == "completed"


def test_conversation_delete_during_session_creation_queues_late_remote_session(tmp_path: Path):
    db = tmp_path / "deleted-late-session.sqlite3"
    store = ChatStore(db)
    snapshot = Snapshot()
    provider = LateSessionDiscoveryProvider()
    config = ChatConfig(state_path=db, max_turn_seconds=2)
    service = ChatService(store, config, snapshot, provider=provider)
    conversation = service.create_conversation("alice")
    store.submit_turn("alice", conversation["id"], "consulta", "client-1", {})
    claim = store.claim_turn()
    worker = TurnWorker(store, config, provider, snapshot)
    worker._registry = Registry({"rows": []})
    service.worker = worker
    thread = threading.Thread(target=worker._execute_turn, args=(claim,))
    thread.start()
    assert provider.started.wait(timeout=1)

    service.delete_conversation("alice", conversation["id"])
    with store._connect() as db_conn:
        assert db_conn.execute("SELECT COUNT(*) FROM conversations").fetchone()[0] == 0
    provider.allow_discovery.set()
    assert provider.cancel_started.wait(timeout=1)
    thread.join(timeout=0.1)
    assert thread.is_alive()
    assert provider.cancelled == ["late-provider-session"]
    assert store.pending_provider_deletions() == ["late-provider-session"]

    provider.cancel_release.set()
    thread.join(timeout=1)
    assert not thread.is_alive()
    worker._drain_provider_deletions()

    assert provider.deleted == ["late-provider-session"]
    assert store.pending_provider_deletions() == []


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
