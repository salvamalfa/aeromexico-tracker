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
        self.cancelled = threading.Event()
        self.cancel_count = 0
        self.message_posts = 0

    def run_turn(self, *, emit, persist_session, cancel_event, cancel_provider, **_kwargs):
        self.message_posts += 1
        persist_session("sess_fixture")
        emit("provider.metadata", {"provider_turn_id": "turn_fixture"})
        # The loop represents an SDK stream receiving comments/heartbeats. They
        # do not yield provider events, so application-level deadline checks
        # cannot run until the independent watchdog cancels the session.
        while not self.cancelled.wait(0.005):
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
        self.cancelled.set()


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
    assert provider.cancel_count == 1
    assert caught.value.original_error.deadline_watchdog_fired is True
    assert caught.value.original_error.reason_code == "turn_timeout"
    assert caught.value.original_error.session_id == "sess_fixture"
    assert caught.value.original_error.turn_id == "turn_fixture"
    assert caught.value.usage == usage
    # The timer has been cancelled and joined; it cannot issue a late cancel.
    time.sleep(0.08)
    assert provider.cancel_count == 1


def test_deadline_during_session_creation_cancels_after_session_id_is_known():
    session_creation_release = threading.Event()

    class SlowSessionCreationProvider(HeartbeatingProvider):
        def run_turn(self, *, persist_session, cancel_event, cancel_provider, **_kwargs):
            self.message_posts += 1
            assert session_creation_release.wait(1)
            persist_session("sess_fixture")
            while not self.cancelled.wait(0.005):
                pass
            cancel_provider("sess_fixture")
            raise RuntimeError("stream cancelled after session creation")

    provider = SlowSessionCreationProvider(max_turn_seconds=0.04)
    errors: list[BaseException] = []

    def run():
        try:
            _run(provider)
        except BaseException as exc:
            errors.append(exc)

    thread = threading.Thread(target=run)
    thread.start()
    time.sleep(0.08)
    session_creation_release.set()
    thread.join(1)

    assert not thread.is_alive()
    assert len(errors) == 1 and isinstance(errors[0], ConversationRunError)
    assert provider.message_posts == 1
    assert provider.cancel_count == 1
    assert errors[0].original_error.deadline_watchdog_fired is True


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
