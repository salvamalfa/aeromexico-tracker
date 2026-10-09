from __future__ import annotations

import threading
import time

from src.conversational_analytics.config import ChatConfig
from src.conversational_analytics.providers.base import ProviderResult
from src.conversational_analytics.storage import ChatStore
from src.conversational_analytics.worker import TurnWorker


class Snapshot:
    version = "snapshot-v1"
    semantic_version = "semantic-v1"

    def catalog(self):
        return {}


class ShutdownProvider:
    supports_input_authorization = True

    def __init__(self, *, block_cancel=False):
        self.started = threading.Event()
        self.release = threading.Event()
        self.returned = threading.Event()
        self.cancel_started = threading.Event()
        self.cancel_release = threading.Event()
        if not block_cancel:
            self.cancel_release.set()
        self.cancelled = []
        self.calls = 0

    def run_turn(self, **kwargs):
        kwargs["authorize_input"]()
        self.calls += 1
        kwargs["persist_session"]("shutdown-session")
        self.started.set()
        self.release.wait()
        self.returned.set()
        return ProviderResult("respuesta", input_tokens=31, output_tokens=7, usage_complete=True)

    def cancel(self, session_id):
        self.cancelled.append(session_id)
        self.cancel_started.set()
        self.cancel_release.wait()

    def delete(self, session_id):
        pass


def _queued(store: ChatStore, key: str):
    conversation = store.create_conversation("alice", "snapshot-v1", "semantic-v1", provider="mock")
    turn, _ = store.submit_turn(
        "alice",
        conversation["id"],
        "consulta",
        key,
        {},
        provider="mock",
        max_active_per_user=2,
        reserved_tokens=100,
        reserved_cost_usd=0.01,
    )
    return turn


def _worker(store, path, provider):
    worker = TurnWorker(
        store,
        ChatConfig(state_path=path, poll_interval_seconds=0.01),
        provider,
        Snapshot(),
    )
    worker._registry = type("EmptyRegistry", (), {"tool_specs": lambda self: []})()
    return worker


def test_stop_drains_active_turn_without_claiming_queued_work(tmp_path):
    path = tmp_path / "chat.sqlite3"
    store = ChatStore(path)
    first = _queued(store, "first")
    queued = _queued(store, "queued")
    provider = ShutdownProvider()
    worker = _worker(store, path, provider)
    worker.start()
    assert provider.started.wait(1)

    stopped = threading.Event()
    stopper = threading.Thread(target=lambda: (worker.stop(timeout=1), stopped.set()))
    stopper.start()
    assert worker._stop.wait(1)
    assert store.get_turn("alice", queued["id"])["status"] == "pending"
    provider.release.set()
    stopper.join(2)

    assert stopped.is_set()
    assert not worker.running
    record = store.get_turn("alice", first["id"])
    assert (record["status"], record["usage_complete"], record["reserved_tokens"]) == (
        "completed",
        1,
        0,
    )
    usage = store.usage("alice")
    assert (usage["input_tokens"], usage["output_tokens"], usage["turn_count"]) == (31, 7, 1)
    assert store.get_turn("alice", queued["id"])["status"] == "pending"


def test_stop_deadline_keeps_unknown_hold_and_books_late_usage_once(tmp_path):
    path = tmp_path / "chat.sqlite3"
    store = ChatStore(path)
    active = _queued(store, "active")
    queued = _queued(store, "queued")
    provider = ShutdownProvider(block_cancel=True)
    worker = _worker(store, path, provider)
    worker.start()
    assert provider.started.wait(1)

    stopped = threading.Event()
    stopper = threading.Thread(target=lambda: (worker.stop(timeout=0.02), stopped.set()))
    stopper.start()
    try:
        assert stopped.wait(0.5)
        assert provider.cancel_started.wait(1)
        assert not provider.cancel_release.is_set()

        record = store.get_turn("alice", active["id"])
        assert (record["status"], record["error_code"], record["usage_complete"]) == (
            "failed",
            "timeout",
            0,
        )
        assert record["reserved_tokens"] == 100
        assert store.get_turn("alice", queued["id"])["status"] == "pending"

        provider.release.set()
        assert provider.returned.wait(1)
        deadline = time.monotonic() + 1
        while store.get_turn("alice", active["id"])["usage_complete"] != 1 and time.monotonic() < deadline:
            threading.Event().wait(0.01)
        assert store.get_turn("alice", active["id"])["usage_complete"] == 1
    finally:
        provider.cancel_release.set()
        provider.release.set()
        stopper.join(1)
        worker._thread.join(1)

    assert not worker.running
    record = store.get_turn("alice", active["id"])
    assert (record["status"], record["usage_complete"], record["reserved_tokens"]) == (
        "failed",
        1,
        0,
    )
    usage = store.usage("alice")
    assert (usage["input_tokens"], usage["output_tokens"], usage["turn_count"]) == (31, 7, 1)
    assert store.get_turn("alice", queued["id"])["status"] == "pending"


def test_expired_stop_between_claim_and_registration_fails_without_provider_input(tmp_path):
    path = tmp_path / "chat.sqlite3"
    store = ChatStore(path)
    active = _queued(store, "active")
    queued = _queued(store, "queued")
    provider = ShutdownProvider()
    worker = _worker(store, path, provider)
    claimed = threading.Event()
    resume = threading.Event()
    execute = worker._execute_turn

    def pause_after_claim(turn):
        claimed.set()
        resume.wait()
        execute(turn)

    worker._execute_turn = pause_after_claim
    worker.start()
    assert claimed.wait(1)
    try:
        worker.stop(timeout=0.02)
        resume.set()
        worker._thread.join(1)
    finally:
        resume.set()
        worker._thread.join(1)

    record = store.get_turn("alice", active["id"])
    assert (record["status"], record["error_code"], record["usage_complete"]) == (
        "failed",
        "timeout",
        1,
    )
    assert (record["reserved_tokens"], record["estimated_input_tokens"], record["estimated_cost_usd"]) == (
        0,
        0,
        0,
    )
    assert provider.calls == 0
    assert store.get_turn("alice", queued["id"])["status"] == "pending"


def test_expired_stop_before_reused_session_input_does_not_cancel_old_session(tmp_path):
    path = tmp_path / "chat.sqlite3"
    store = ChatStore(path)
    conversation = store.create_conversation("alice", "snapshot-v1", "semantic-v1", provider="mock")
    store.set_provider_session(conversation["id"], "reused-session")
    active, _ = store.submit_turn(
        "alice", conversation["id"], "consulta", "active", {}, provider="mock", reserved_tokens=100,
        reserved_cost_usd=0.01
    )

    class BeforeInputProvider(ShutdownProvider):
        def __init__(self):
            super().__init__()
            self.before_input = threading.Event()
            self.authorize_now = threading.Event()

        def run_turn(self, **kwargs):
            assert kwargs["session_id"] == "reused-session"
            self.before_input.set()
            self.authorize_now.wait()
            kwargs["authorize_input"]()
            self.calls += 1

    provider = BeforeInputProvider()
    worker = _worker(store, path, provider)
    worker.start()
    assert provider.before_input.wait(1)
    stopped = threading.Event()
    stopper = threading.Thread(target=lambda: (worker.stop(timeout=0.02), stopped.set()))
    stopper.start()
    try:
        assert stopped.wait(0.5)
        provider.authorize_now.set()
        stopper.join(1)
        worker._thread.join(1)
    finally:
        provider.authorize_now.set()
        stopper.join(1)
        worker._thread.join(1)

    record = store.get_turn("alice", active["id"])
    assert (record["status"], record["error_code"], record["usage_complete"]) == (
        "failed",
        "timeout",
        1,
    )
    assert provider.calls == 0
    assert provider.cancelled == []
    assert store.get_provider_session(conversation["id"]) == "reused-session"


def test_strict_legacy_provider_signature_completes_and_books_usage(tmp_path):
    path = tmp_path / "chat.sqlite3"
    store = ChatStore(path)
    turn = _queued(store, "strict-legacy")

    class StrictLegacyProvider:
        def __init__(self):
            self.calls = 0

        def run_turn(
            self,
            *,
            session_id,
            messages,
            context,
            tool_specs,
            call_tool,
            emit,
            persist_session,
            cancel_event,
        ):
            self.calls += 1
            return ProviderResult("respuesta", input_tokens=2, output_tokens=1, usage_complete=True)

        def cancel(self, session_id):
            pass

        def delete(self, session_id):
            pass

    provider = StrictLegacyProvider()
    worker = _worker(store, path, provider)
    claim = store.claim_turn()
    worker._execute_turn(claim)

    record = store.get_turn("alice", turn["id"])
    assert (record["status"], record["usage_complete"], record["reserved_tokens"]) == (
        "completed",
        1,
        0,
    )
    usage = store.usage("alice")
    assert (provider.calls, usage["input_tokens"], usage["output_tokens"], usage["turn_count"]) == (
        1,
        2,
        1,
        1,
    )
