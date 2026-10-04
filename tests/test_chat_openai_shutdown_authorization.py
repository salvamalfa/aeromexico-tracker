"""Offline fences at actual OpenAI session input writes."""

# ruff: noqa: E402,I001

from __future__ import annotations

import threading

import pytest

pytest.importorskip("openai")

from src.conversational_analytics.tools.registry import ToolRegistry
from test_chat_openai import (
    FakeClient,
    FakeSessions,
    FakeStream,
    _completed,
    _provider,
    _session_created,
    _text_done,
    _turn,
    _turn_created,
)


def _run(provider, *, session_id, authorize_input):
    return provider.run_turn(
        session_id=session_id,
        messages=[{"role": "user", "content": "Pregunta", "turn_id": "app-turn"}],
        context={"period": "2026Q2"},
        tool_specs=ToolRegistry._make_specs(),
        call_tool=lambda *_: {},
        emit=lambda *_: None,
        persist_session=lambda *_: None,
        cancel_event=threading.Event(),
        authorize_input=authorize_input,
    )


@pytest.mark.parametrize("reused", [False, True])
def test_authorization_immediately_precedes_each_user_input_write(reused):
    events = []
    stream = FakeStream(
        [_session_created(), _turn_created(), _text_done(), _completed()]
        if not reused
        else [_turn_created("turn_new"), _text_done("turn_new"), _completed("turn_new")]
    )
    fake = FakeSessions(
        create_stream=stream,
        event_stream=stream,
        prior_turns=[_turn("turn_old", status="completed")] if reused else [],
    )
    provider = _provider(FakeClient(fake))
    if reused:
        write_input = fake.events.create

        def track_write(*args, **kwargs):
            events.append("sdk.input.create")
            return write_input(*args, **kwargs)

        fake.events.create = track_write
    else:
        create_session = fake.create

        def track_create(**kwargs):
            events.append("sdk.session.create")
            return create_session(**kwargs)

        fake.create = track_create

    _run(
        provider,
        session_id="sess_fixture" if reused else None,
        authorize_input=lambda: events.append("authorized"),
    )

    assert events == ["authorized", "sdk.input.create" if reused else "sdk.session.create"]


@pytest.mark.parametrize("reused", [False, True])
def test_denied_authorization_never_sends_provider_input(reused):
    stream = FakeStream([_session_created()] if not reused else [_turn_created("turn_new")])
    fake = FakeSessions(
        create_stream=stream,
        event_stream=stream,
        prior_turns=[_turn("turn_old", status="completed")] if reused else [],
    )
    provider = _provider(FakeClient(fake))

    def deny():
        raise InterruptedError("shutdown fence closed")

    with pytest.raises(InterruptedError, match="shutdown fence"):
        _run(provider, session_id="sess_fixture" if reused else None, authorize_input=deny)

    assert fake.created == []
    assert fake.events.created == []
