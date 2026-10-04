"""Offline fences at actual OpenAI session input writes."""

# ruff: noqa: E402,I001

from __future__ import annotations

import threading
import time

import pytest

pytest.importorskip("openai")

from src.conversational_analytics.tools.registry import ToolRegistry
from src.conversational_analytics.config import ChatConfig
from src.conversational_analytics.storage import ChatStore
from src.conversational_analytics.worker import TurnWorker
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
from src.conversational_analytics.providers.openai import OpenAIProviderError


def _run(provider, *, session_id, authorize_input, cancel_event=None):
    return provider.run_turn(
        session_id=session_id,
        messages=[{"role": "user", "content": "Pregunta", "turn_id": "app-turn"}],
        context={"period": "2026Q2"},
        tool_specs=ToolRegistry._make_specs(),
        call_tool=lambda *_: {},
        emit=lambda *_: None,
        persist_session=lambda *_: None,
        cancel_event=cancel_event or threading.Event(),
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


@pytest.mark.parametrize(
    ("acknowledgment_lost", "second_cancel_fails"),
    [(False, False), (True, False), (True, True)],
)
def test_reused_session_cancel_before_input_write_is_reissued_after_write(
    acknowledgment_lost, second_cancel_fails
):
    stream = FakeStream([_turn_created("turn_new"), _text_done("turn_new"), _completed("turn_new")])
    fake = FakeSessions(
        event_stream=stream,
        prior_turns=[_turn("turn_old", status="completed")],
    )
    provider = _provider(FakeClient(fake))
    cancel_event = threading.Event()
    input_write_entered = threading.Event()
    allow_input_write = threading.Event()
    order = []
    run_errors = []
    cancel_count = 0
    original_create = fake.events.create

    def block_input_write(*args, **kwargs):
        nonlocal cancel_count
        event = kwargs["events"][0]["type"]
        if event == "agent.session.input.message":
            input_write_entered.set()
            assert allow_input_write.wait(timeout=1)
            order.append("input")
        elif event == "agent.session.input.cancel":
            cancel_count += 1
            order.append("cancel")
        result = original_create(*args, **kwargs)
        if event == "agent.session.input.message" and acknowledgment_lost:
            raise RuntimeError("write accepted but acknowledgment lost")
        if event == "agent.session.input.cancel" and cancel_count == 2 and second_cancel_fails:
            raise RuntimeError("best-effort cancel failed")
        return result

    fake.events.create = block_input_write

    def run():
        try:
            _run(
                provider,
                session_id="sess_fixture",
                authorize_input=lambda: order.append("authorized"),
                cancel_event=cancel_event,
            )
        except (InterruptedError, OpenAIProviderError) as exc:
            run_errors.append(exc)

    thread = threading.Thread(target=run)
    thread.start()
    try:
        assert input_write_entered.wait(timeout=1)
        cancel_event.set()
        provider.cancel("sess_fixture")
        allow_input_write.set()
        thread.join(timeout=1)
    finally:
        allow_input_write.set()
        thread.join(timeout=1)

    assert not thread.is_alive()
    if acknowledgment_lost:
        assert len(run_errors) == 1
        assert isinstance(run_errors[0], OpenAIProviderError)
        assert run_errors[0].usage is None
    else:
        assert len(run_errors) == 1
        assert isinstance(run_errors[0], InterruptedError)
    assert order == ["authorized", "cancel", "input", "cancel"]
    assert [item["events"][0]["type"] for item in fake.events.created] == [
        "agent.session.input.cancel",
        "agent.session.input.message",
        "agent.session.input.cancel",
    ]


def test_worker_shutdown_stays_bounded_while_post_write_cancel_is_blocked(tmp_path):
    path = tmp_path / "reused-session-shutdown.sqlite3"
    store = ChatStore(path)
    conversation = store.create_conversation("alice", "snapshot-v1", "semantic-v1")
    store.set_provider_session(conversation["id"], "sess_fixture")
    first, _ = store.submit_turn(
        "alice",
        conversation["id"],
        "primera",
        "first",
        {},
        max_active_per_user=2,
        reserved_tokens=100,
        reserved_cost_usd=0.01,
    )
    next_conversation = store.create_conversation("alice", "snapshot-v1", "semantic-v1")
    queued, _ = store.submit_turn(
        "alice",
        next_conversation["id"],
        "siguiente",
        "queued",
        {},
        max_active_per_user=2,
        reserved_tokens=100,
        reserved_cost_usd=0.01,
    )
    fake = FakeSessions(
        event_stream=FakeStream([]),
        prior_turns=[_turn("turn_old", status="completed")],
    )
    provider = _provider(FakeClient(fake))
    input_started = threading.Event()
    release_input = threading.Event()
    first_cancel_sent = threading.Event()
    second_cancel_started = threading.Event()
    release_second_cancel = threading.Event()
    order = []
    original_create = fake.events.create
    cancel_count = 0

    def controlled_create(*args, **kwargs):
        nonlocal cancel_count
        event_type = kwargs["events"][0]["type"]
        if event_type == "agent.session.input.message":
            input_started.set()
            assert release_input.wait(timeout=2)
            order.append("input")
        elif event_type == "agent.session.input.cancel":
            cancel_count += 1
            order.append("cancel")
            if cancel_count == 1:
                first_cancel_sent.set()
            elif cancel_count == 2:
                second_cancel_started.set()
                assert release_second_cancel.wait(timeout=2)
        return original_create(*args, **kwargs)

    fake.events.create = controlled_create

    class Snapshot:
        version = "snapshot-v1"
        semantic_version = "semantic-v1"

        def catalog(self):
            return {"metrics": {"metrics": []}, "entities": {"entities": []}}

    worker = TurnWorker(
        store,
        ChatConfig(state_path=path, max_turn_seconds=90, poll_interval_seconds=0.01),
        provider,
        Snapshot(),
    )
    worker._registry = type("Registry", (), {"tool_specs": lambda self: ToolRegistry._make_specs()})()
    worker.start()
    try:
        assert input_started.wait(timeout=1)
        assert store.request_cancel("alice", first["id"]) == "cancelled"
        worker.cancel(first["id"])
        assert first_cancel_sent.wait(timeout=1)
        release_input.set()
        assert second_cancel_started.wait(timeout=1)
        stop_started = time.monotonic()
        worker.stop(timeout=0.05)
        assert time.monotonic() - stop_started < 0.5
        terminal = store.get_turn("alice", first["id"])
        assert (terminal["status"], terminal["error_code"], terminal["usage_complete"]) == (
            "cancelled",
            "cancelled",
            0,
        )
        assert terminal["reserved_tokens"] == 100
        assert store.get_turn("alice", queued["id"])["status"] == "pending"
        release_second_cancel.set()
        worker._thread.join(timeout=1)
    finally:
        release_input.set()
        release_second_cancel.set()
        if worker._thread:
            worker._thread.join(timeout=1)

    assert not worker.running
    assert order == ["cancel", "input", "cancel"]
    assert [item["events"][0]["type"] for item in fake.events.created].count(
        "agent.session.input.message"
    ) == 1
    final = store.get_turn("alice", first["id"])
    assert (final["status"], final["usage_complete"], final["reserved_tokens"]) == ("cancelled", 0, 100)
    assert store.get_turn("alice", queued["id"])["status"] == "pending"
