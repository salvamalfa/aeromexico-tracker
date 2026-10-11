"""Offline tests for provider input fencing and concurrent stream cleanup."""

from __future__ import annotations

import threading

import pytest
from test_chat_openai import FakeClient, FakeSessions, _provider, _specs

from src.conversational_analytics.providers.openai import OpenAIProviderError


def test_input_dispatch_hook_is_the_only_path_to_followup_message_post():
    fake = FakeSessions()
    provider = _provider(FakeClient(fake))

    def reject_dispatch(_request):
        raise TimeoutError("deadline fence rejected input")

    with pytest.raises(OpenAIProviderError, match="no se reenviará"):
        provider.run_turn(
            session_id="sess_fixture",
            messages=[{"role": "user", "content": "fixture"}],
            context={},
            tool_specs=_specs(),
            call_tool=lambda *_args: {},
            emit=lambda *_args: None,
            persist_session=lambda _session: None,
            cancel_event=threading.Event(),
            dispatch_input=reject_dispatch,
        )

    assert fake.events.created == []


def test_registered_stream_close_is_idempotent_under_watchdog_race():
    class BlockingStream:
        def __init__(self):
            self.release = threading.Event()
            self.entered = threading.Event()
            self.close_count = 0

        def __enter__(self):
            self.entered.set()

            def iterate():
                self.release.wait(1)
                if False:
                    yield None

            return iterate()

        def __exit__(self, *_args):
            self.close_count += 1
            self.release.set()

    stream = BlockingStream()
    fake = FakeSessions(event_stream=stream)
    provider = _provider(FakeClient(fake))
    registered = []
    registration_ready = threading.Event()

    def register(closer):
        registered.append(closer)
        registration_ready.set()

    def invoke():
        try:
            provider.run_turn(
                session_id="sess_fixture",
                messages=[{"role": "user", "content": "fixture"}],
                context={},
                tool_specs=_specs(),
                call_tool=lambda *_args: {},
                emit=lambda *_args: None,
                persist_session=lambda _session: None,
                cancel_event=threading.Event(),
                register_stream_close=register,
            )
        except (OpenAIProviderError, InterruptedError):
            pass

    worker = threading.Thread(target=invoke)
    worker.start()
    assert registration_ready.wait(1)
    assert stream.entered.wait(1)
    closers = [threading.Thread(target=registered[0]) for _ in range(2)]
    for closer in closers:
        closer.start()
    for closer in closers:
        closer.join(1)
    worker.join(1)

    assert not worker.is_alive()
    assert stream.close_count == 1


def test_cancel_uses_finite_timeout_and_returns_remote_failure():
    fake = FakeSessions()
    client = FakeClient(fake)
    client_options = []
    client.with_options = lambda **kwargs: (client_options.append(kwargs) or client)
    provider = _provider(client)

    def fail_cancel(session_id, **kwargs):
        fake.events.created.append({"session_id": session_id, **kwargs})
        raise OSError("remote cancel failed")

    fake.events.create = fail_cancel
    result = provider.cancel("sess_fixture")

    assert fake.events.created[0]["timeout"] == 10.0
    assert fake.events.created[0]["events"] == [{"type": "agent.session.input.cancel"}]
    assert client_options == [{"timeout": 10.0, "max_retries": 0}]
    assert result["status"] == "failed_manual_reconciliation"
    assert result["error_metadata"]["upstream_exception_type"] == "OSError"
