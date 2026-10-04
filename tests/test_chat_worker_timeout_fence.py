from __future__ import annotations

import threading
from pathlib import Path

from src.conversational_analytics.config import ChatConfig
from src.conversational_analytics.providers.base import ProviderResult
from src.conversational_analytics.storage import ChatStore
from src.conversational_analytics.worker import TurnWorker


class Snapshot:
    version = "snapshot-v1"
    semantic_version = "semantic-v1"

    def catalog(self):
        return {}


class Registry:
    def tool_specs(self):
        return []


def _claimed_turn(store: ChatStore):
    conversation = store.create_conversation("alice", "snapshot-v1", "semantic-v1")
    turn, _ = store.submit_turn("alice", conversation["id"], "consulta", "fence-test", {})
    return turn, store.claim_turn()


def _worker(store: ChatStore, provider, *, max_seconds: float = 0.05):
    worker = TurnWorker(
        store,
        ChatConfig(state_path=store.path, max_turn_seconds=max_seconds),
        provider,
        Snapshot(),
    )
    worker._registry = Registry()
    return worker


def test_watchdog_fences_input_authorization_before_recording_zero_usage(tmp_path: Path):
    store = ChatStore(tmp_path / "timeout-input-fence.sqlite3")
    turn, claim = _claimed_turn(store)
    timeout_paused = threading.Event()
    finish_timeout = threading.Event()
    auth_attempting = threading.Event()
    auth_result: list[str] = []

    class FenceProvider:
        supports_input_authorization = True

        def __init__(self):
            self.started = threading.Event()
            self.release = threading.Event()

        def run_turn(self, **kwargs):
            self.authorize = kwargs["authorize_input"]
            self.started.set()
            self.release.wait(timeout=1)
            raise InterruptedError("watchdog finished")

        def cancel(self, session_id):
            pass

        def delete(self, session_id):
            pass

    provider = FenceProvider()
    worker = _worker(store, provider)
    original_fail_turn = store.fail_turn

    def pause_timeout_write(turn_id, code, message, usage=None):
        if code == "timeout" and message == "El turno excedió el tiempo máximo configurado.":
            timeout_paused.set()
            assert finish_timeout.wait(timeout=1)
        return original_fail_turn(turn_id, code, message, usage)

    store.fail_turn = pause_timeout_write
    thread = threading.Thread(target=worker._execute_turn, args=(claim,))
    thread.start()
    assert provider.started.wait(timeout=1)
    assert timeout_paused.wait(timeout=1)

    def authorize_during_terminal_write():
        auth_attempting.set()
        try:
            provider.authorize()
        except InterruptedError:
            auth_result.append("denied")
        else:
            auth_result.append("granted")

    authorizer = threading.Thread(target=authorize_during_terminal_write)
    authorizer.start()
    assert auth_attempting.wait(timeout=1)
    finish_timeout.set()
    authorizer.join(timeout=1)
    provider.release.set()
    thread.join(timeout=1)

    assert not authorizer.is_alive()
    assert not thread.is_alive()
    assert auth_result == ["denied"]
    record = store.get_turn("alice", turn["id"])
    assert (record["status"], record["error_code"], record["usage_complete"]) == (
        "failed",
        "timeout",
        1,
    )
    assert record["reserved_tokens"] == 0


def test_legacy_provider_is_not_invoked_after_timeout_terminal_before_cancel_event(tmp_path: Path):
    store = ChatStore(tmp_path / "legacy-timeout-fence.sqlite3")
    turn, claim = _claimed_turn(store)
    messages_paused = threading.Event()
    continue_messages = threading.Event()
    timeout_terminal = threading.Event()
    cancel_waiting = threading.Event()
    allow_cancel = threading.Event()
    checked_terminal_before_input = threading.Event()

    class LegacyProvider:
        def __init__(self):
            self.calls = 0

        def run_turn(self, **kwargs):
            self.calls += 1
            return ProviderResult("unexpected", input_tokens=1, output_tokens=1, usage_complete=True)

        def cancel(self, session_id):
            pass

        def delete(self, session_id):
            pass

    provider = LegacyProvider()
    worker = _worker(store, provider)
    original_messages = store.turn_messages
    original_fail_turn = store.fail_turn
    original_cancel = worker._cancel_terminal_session
    original_is_running = store.is_running

    def pause_messages(*args, **kwargs):
        messages_paused.set()
        assert continue_messages.wait(timeout=1)
        return original_messages(*args, **kwargs)

    def observe_terminal(turn_id, code, message, usage=None):
        result = original_fail_turn(turn_id, code, message, usage)
        if code == "timeout" and message == "El turno excedió el tiempo máximo configurado.":
            timeout_terminal.set()
        return result

    def pause_cancel(turn_id, *args, **kwargs):
        cancel_waiting.set()
        assert allow_cancel.wait(timeout=1)
        return original_cancel(turn_id, *args, **kwargs)

    def observe_running(turn_id):
        running = original_is_running(turn_id)
        if timeout_terminal.is_set() and threading.current_thread() is thread:
            checked_terminal_before_input.set()
        return running

    store.turn_messages = pause_messages
    store.fail_turn = observe_terminal
    store.is_running = observe_running
    worker._cancel_terminal_session = pause_cancel
    thread = threading.Thread(target=worker._execute_turn, args=(claim,))
    thread.start()
    assert messages_paused.wait(timeout=1)
    assert timeout_terminal.wait(timeout=1)
    assert cancel_waiting.wait(timeout=1)

    # Hold the watchdog between terminal persistence and cancel_event.set().
    continue_messages.set()
    try:
        assert checked_terminal_before_input.wait(timeout=1)
    finally:
        allow_cancel.set()
    thread.join(timeout=1)

    assert not thread.is_alive()
    assert provider.calls == 0
    record = store.get_turn("alice", turn["id"])
    assert (record["status"], record["error_code"], record["usage_complete"]) == (
        "failed",
        "timeout",
        1,
    )
    assert record["reserved_tokens"] == 0
