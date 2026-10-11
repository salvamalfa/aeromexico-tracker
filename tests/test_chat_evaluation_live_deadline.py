"""Wall-clock watchdog tests for blocking live-evaluation provider streams."""

from __future__ import annotations

import threading
import time

import pytest

from src.conversational_analytics.evaluation_live_turns import ConversationRunError, run_conversation
from src.conversational_analytics.providers.base import ProviderResult


class HeartbeatingProvider:
    """Model an SSE stream that keeps producing transport heartbeats forever."""

    def __init__(self, *, max_turn_seconds: float, usage: tuple[int, int] | None = None):
        self.max_turn_seconds = max_turn_seconds
        self.usage = usage
        self.stream_closed = threading.Event()
        self.cancel_count = 0
        self.close_count = 0
        self.message_posts = 0

    def run_turn(
        self,
        *,
        emit,
        persist_session,
        register_stream_close,
        cancel_provider,
        **_kwargs,
    ):
        self.message_posts += 1
        persist_session("sess_fixture")
        emit("provider.metadata", {"provider_turn_id": "turn_fixture"})

        def close_stream():
            self.close_count += 1
            self.stream_closed.set()

        register_stream_close(close_stream)
        # The loop represents an SDK stream receiving comments/heartbeats. They
        # do not yield provider events, so application-level deadline checks
        # cannot run until the independent watchdog cancels the session.
        while not self.stream_closed.wait(0.005):
            pass
        # Exercise the provider's own cancellation path racing the watchdog.
        cancel_provider("sess_fixture")
        error = RuntimeError("stream cancelled by wall-clock watchdog")
        if self.usage is not None:
            error.usage = self.usage
        raise error

    def cancel(self, session_id: str) -> None:
        assert session_id == "sess_fixture"
        self.cancel_count += 1


def _run(provider):
    session: list[str] = []
    run_conversation(
        provider,
        {"id": "case_fixture", "question": "safe fixture question"},
        context={},
        tool_specs=[],
        call_tool=lambda *_args: {},
        emit=lambda *_args: None,
        persist_session=session.append,
        session=session,
        current_turn_index=[0],
        calls_by_turn=[],
    )


@pytest.mark.parametrize("usage", [(12, 3), None])
def test_live_deadline_cancels_blocking_stream_once_and_preserves_usage(usage):
    provider = HeartbeatingProvider(max_turn_seconds=0.06, usage=usage)
    started = time.monotonic()

    with pytest.raises(ConversationRunError) as caught:
        _run(provider)

    assert time.monotonic() - started < 1
    assert provider.message_posts == 1
    assert provider.close_count == 1
    # Cancellation is deliberately detached; it cannot delay timeout return.
    for _ in range(50):
        if provider.cancel_count:
            break
        time.sleep(0.005)
    assert provider.cancel_count == 1
    assert caught.value.original_error.deadline_watchdog_fired is True
    assert caught.value.original_error.reason_code == "turn_timeout"
    assert caught.value.original_error.session_id == "sess_fixture"
    assert caught.value.original_error.turn_id == "turn_fixture"
    assert caught.value.usage == usage
    # Watchdog actions are one-shot; late worker unwind cannot send another.
    time.sleep(0.08)
    assert provider.cancel_count == 1


def test_deadline_during_session_creation_blocks_late_message_post():
    session_creation_release = threading.Event()

    class SlowSessionCreationProvider(HeartbeatingProvider):
        def __init__(self):
            super().__init__(max_turn_seconds=0.04)
            self.create_posts = 0

        def run_turn(self, *, persist_session, authorize_input, **_kwargs):
            self.create_posts += 1
            session_creation_release.wait()
            persist_session("sess_fixture")
            authorize_input()
            self.message_posts += 1

    provider = SlowSessionCreationProvider()
    errors: list[BaseException] = []

    def run():
        try:
            _run(provider)
        except BaseException as exc:
            errors.append(exc)

    thread = threading.Thread(target=run)
    thread.start()
    time.sleep(0.08)
    thread.join(0.5)
    assert not thread.is_alive()
    assert len(errors) == 1 and isinstance(errors[0], ConversationRunError)

    # The create request was already in flight, but after it returns the
    # authorization fence prevents any new paid user-message request.
    session_creation_release.set()
    for _ in range(100):
        if provider.cancel_count:
            break
        time.sleep(0.005)
    assert provider.create_posts == 1
    assert provider.message_posts == 0
    assert provider.cancel_count == 1
    assert errors[0].original_error.deadline_watchdog_fired is True


def test_unresolved_session_creation_returns_without_worker_join():
    class NeverReturningCreateProvider:
        max_turn_seconds = 0.03
        create_posts = 0
        message_posts = 0
        cancel_count = 0

        def run_turn(self, **_kwargs):
            self.create_posts += 1
            threading.Event().wait()

        def cancel(self, _session_id):
            self.cancel_count += 1

    provider = NeverReturningCreateProvider()
    started = time.monotonic()
    with pytest.raises(ConversationRunError) as caught:
        _run(provider)

    assert time.monotonic() - started < 0.3
    assert caught.value.original_error.deadline_watchdog_fired is True
    assert provider.create_posts == 1
    assert provider.message_posts == 0
    assert provider.cancel_count == 0  # no exact session ID exists to cancel


def test_dispatch_fence_rejects_post_after_authorization_gap():
    release_dispatch = threading.Event()

    class Provider:
        max_turn_seconds = 0.04
        message_posts = 0
        cancel_count = 0

        def run_turn(self, *, persist_session, authorize_input, dispatch_input, **_kwargs):
            persist_session("sess_fixture")
            authorize_input()
            release_dispatch.wait()
            dispatch_input(lambda: setattr(self, "message_posts", self.message_posts + 1))

        def cancel(self, _session_id):
            self.cancel_count += 1

    provider = Provider()
    errors: list[BaseException] = []

    def run():
        try:
            _run(provider)
        except BaseException as exc:
            errors.append(exc)

    thread = threading.Thread(target=run)
    thread.start()
    time.sleep(0.08)
    thread.join(0.5)
    assert not thread.is_alive()
    assert len(errors) == 1 and isinstance(errors[0], ConversationRunError)
    release_dispatch.set()
    time.sleep(0.03)
    assert provider.message_posts == 0
    assert provider.cancel_count == 1


def test_blocked_remote_cancel_does_not_extend_deadline_return():
    class HangingCancelProvider(HeartbeatingProvider):
        def cancel(self, session_id):
            self.cancel_count += 1
            threading.Event().wait(0.25)

    provider = HangingCancelProvider(max_turn_seconds=0.04)
    started = time.monotonic()
    with pytest.raises(ConversationRunError):
        _run(provider)
    assert time.monotonic() - started < 0.2
    assert provider.close_count == 1
    assert provider.message_posts == 1


def test_failed_deadline_cancel_is_exposed_for_manual_reconciliation():
    class FailingCancelProvider(HeartbeatingProvider):
        def cancel(self, session_id):
            self.cancel_count += 1
            raise OSError("cancel endpoint unavailable")

    provider = FailingCancelProvider(max_turn_seconds=0.03)
    with pytest.raises(ConversationRunError) as caught:
        _run(provider)

    error = caught.value.original_error
    assert error.cancel_done.wait(0.5)
    outcome = error.cancel_outcome()
    assert outcome["status"] == "failed_manual_reconciliation"
    assert isinstance(outcome["error"], OSError)
    assert provider.cancel_count == 1
    assert provider.message_posts == 1


def test_hanging_deadline_cancel_stays_pending_without_blocking_return():
    release_cancel = threading.Event()

    class HangingCancelProvider(HeartbeatingProvider):
        def cancel(self, session_id):
            self.cancel_count += 1
            release_cancel.wait()

    provider = HangingCancelProvider(max_turn_seconds=0.03)
    started = time.monotonic()
    with pytest.raises(ConversationRunError) as caught:
        _run(provider)

    error = caught.value.original_error
    assert time.monotonic() - started < 0.5
    assert error.cancel_outcome()["status"] == "pending_manual_reconciliation"
    assert provider.cancel_count == 1
    assert provider.message_posts == 1
    release_cancel.set()


class FastProvider:
    max_turn_seconds = 0.15

    def __init__(self):
        self.cancel_count = 0
        self.message_posts = 0

    def run_turn(self, *, persist_session, **_kwargs):
        self.message_posts += 1
        persist_session("sess_fast")
        return ProviderResult(
            content="done", input_tokens=8, output_tokens=2, usage_complete=True
        )

    def cancel(self, _session_id):
        self.cancel_count += 1


def test_live_turn_completing_before_deadline_is_not_cancelled_later():
    provider = FastProvider()
    turns, result, _ = run_conversation(
        provider,
        {"id": "case_fixture", "question": "safe fixture question"},
        context={},
        tool_specs=[],
        call_tool=lambda *_args: {},
        emit=lambda *_args: None,
        persist_session=lambda _session: None,
        session=[],
        current_turn_index=[0],
        calls_by_turn=[],
    )

    time.sleep(0.18)
    assert len(turns) == 1
    assert result.usage_complete is True
    assert provider.message_posts == 1
    assert provider.cancel_count == 0
