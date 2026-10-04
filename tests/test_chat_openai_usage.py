"""Delayed official Agents API turn-usage reconciliation tests."""

# The optional dependency must be gated before its generated types are imported.
# ruff: noqa: E402,I001

from __future__ import annotations

import threading
import time
from types import SimpleNamespace

import pytest

openai = pytest.importorskip("openai")

from openai.types.beta.agent_session import (  # noqa: E402
    AgentSession,
    RequiredActionSessionRequiredActionResourceFunctionCall,
)
from openai.types.beta.agent_session_created_event import AgentSessionCreatedEvent  # noqa: E402
from openai.types.beta.agent_session_turn_completed_event import AgentSessionTurnCompletedEvent  # noqa: E402
from openai.types.beta.agent_session_turn_created_event import AgentSessionTurnCreatedEvent  # noqa: E402
from openai.types.beta.agent_session_turn_output_text_delta_event import (
    AgentSessionTurnOutputTextDeltaEvent,  # noqa: E402
)
from openai.types.beta.agents.sessions.turn import Turn  # noqa: E402

from src.conversational_analytics.providers import _openai_helpers as helpers  # noqa: E402
from src.conversational_analytics.providers.openai import (  # noqa: E402
    OpenAIProvider,
    OpenAIProviderError,
)
from src.conversational_analytics.tools.registry import ToolRegistry  # noqa: E402


def _usage() -> dict:
    return {
        "input_tokens": 31,
        "output_tokens": 19,
        "total_tokens": 50,
        "input_tokens_details": {"cached_tokens": 8},
        "output_tokens_details": {"reasoning_tokens": 4},
    }


def _turn(turn_id: str, *, status: str = "in_progress", usage=None) -> Turn:
    value = {
        "id": turn_id,
        "agent_id": "agent_fixture",
        "created_at": 1_791_100_000,
        "object": "agent.session.turn",
        "session_id": "sess_fixture",
        "status": status,
        "subagent_id": None,
    }
    if usage is not None:
        value["usage"] = usage
    return Turn.model_validate(value)


def _events_without_usage():
    session = AgentSession.model_construct(id="sess_fixture", required_actions=[], status="in_progress")
    return [
        AgentSessionCreatedEvent.model_construct(
            event_id="evt_created", session=session, type="agent.session.created"
        ),
        AgentSessionTurnCreatedEvent.model_validate(
            {
                "event_id": "evt_turn_created",
                "session_id": "sess_fixture",
                "turn_id": "turn_fixture",
                "type": "agent.session.turn.created",
                "turn": _turn("turn_fixture").model_dump(),
            }
        ),
        AgentSessionTurnOutputTextDeltaEvent.model_validate(
            {
                "event_id": "evt_delta",
                "session_id": "sess_fixture",
                "turn_id": "turn_fixture",
                "item_id": "item_fixture",
                "output_index": 0,
                "content_index": 0,
                "type": "agent.session.turn.output_text.delta",
                "delta": "Respuesta offline.",
            }
        ),
        AgentSessionTurnCompletedEvent.model_validate(
            {
                "event_id": "evt_completed",
                "session_id": "sess_fixture",
                "turn_id": "turn_fixture",
                "type": "agent.session.turn.completed",
                "turn": _turn("turn_fixture", status="completed").model_dump(),
            }
        ),
    ]


class _FakeStream:
    def __init__(self, events):
        self._events = iter(events)
        self.closed = False
        self.exit_count = 0

    def with_result_collection(self):
        return self

    def __enter__(self):
        return self

    def __iter__(self):
        return self

    def __next__(self):
        return next(self._events)

    def __exit__(self, *_):
        self.exit_count += 1
        self.closed = True


class _FakeSessions:
    def __init__(self, stream, retrieved_turns):
        self.stream = stream
        self.created = []
        self.turn_retrieve_calls = []
        self._retrieved_turns = list(retrieved_turns)
        self.turns = SimpleNamespace(retrieve=self._retrieve_turn)

    def create(self, **kwargs):
        self.created.append(kwargs)
        return self.stream

    def _retrieve_turn(self, turn_id, *, session_id, timeout):
        assert self.stream.closed, "the event stream must close before the usage GET"
        self.turn_retrieve_calls.append((turn_id, session_id, timeout))
        return self._retrieved_turns.pop(0) if self._retrieved_turns else None


def _provider_call(retrieved_turns):
    stream = _FakeStream(_events_without_usage())
    sessions = _FakeSessions(stream, retrieved_turns)
    client = SimpleNamespace(beta=SimpleNamespace(agents=SimpleNamespace(sessions=sessions)))
    provider = OpenAIProvider(
        SimpleNamespace(openai_enabled=True, model="model-explicit", max_turn_seconds=5), client=client
    )
    result = provider.run_turn(
        session_id=None,
        messages=[{"role": "user", "content": "Pregunta fixture", "turn_id": "app-turn-fixture"}],
        context={"period": "2026Q2"},
        tool_specs=ToolRegistry._make_specs(),
        call_tool=lambda *_: {"ok": True},
        emit=lambda *_: None,
        persist_session=lambda *_: None,
        cancel_event=threading.Event(),
    )
    return result, sessions, stream


def _limited_provider_run(events, *, config=None, call_tool=None):
    class Stream:
        def with_result_collection(self):
            return self

        def __enter__(self):
            return iter(events)

        def __exit__(self, *_):
            return None

    tool_events = []
    sessions = SimpleNamespace(
        create=lambda **_: Stream(),
        events=SimpleNamespace(create=lambda _session_id, **kwargs: tool_events.append(kwargs)),
    )
    client = SimpleNamespace(beta=SimpleNamespace(agents=SimpleNamespace(sessions=sessions)))
    settings = {"openai_enabled": True, "model": "explicit", "max_turn_seconds": 5}
    settings.update(config or {})
    provider = OpenAIProvider(SimpleNamespace(**settings), client=client)

    def run():
        return provider.run_turn(
            session_id=None,
            messages=[{"role": "user", "content": "Pregunta", "turn_id": "app-turn"}],
            context={"period": "2026Q2"},
            tool_specs=ToolRegistry._make_specs(),
            call_tool=call_tool or (lambda *_: {"ok": True}),
            emit=lambda *_: None,
            persist_session=lambda *_: None,
            cancel_event=threading.Event(),
        )

    return tool_events, run


def test_provider_polls_until_typed_turn_usage_appears_without_resubmitting_input(monkeypatch):
    monkeypatch.setattr(helpers, "USAGE_POLL_INTERVAL_SECONDS", 0.001)
    result, sessions, stream = _provider_call(
        [None, _turn("turn_fixture", status="completed", usage=_usage())]
    )

    assert result.content == "Respuesta offline."
    assert (result.input_tokens, result.output_tokens, result.usage_complete) == (31, 19, True)
    assert len(sessions.turn_retrieve_calls) == 2
    assert sessions.created[0]["stream"] is True
    assert sessions.created[0]["input"][0]["content"][0]["text"].endswith('"question":"Pregunta fixture"}')
    assert stream.exit_count == 1


def test_provider_stops_after_five_missing_usage_reads_and_keeps_turn_successful(monkeypatch):
    monkeypatch.setattr(helpers, "USAGE_POLL_INTERVAL_SECONDS", 0.001)
    result, sessions, _ = _provider_call([None] * 5)

    assert result.content == "Respuesta offline."
    assert result.usage_complete is False
    assert len(sessions.turn_retrieve_calls) == 5
    assert len(sessions.created) == 1


def test_usage_poll_stops_promptly_on_cancel_and_never_reads_after_deadline():
    cancel_event = threading.Event()
    calls = []

    def cancelled_read(*_, **__):
        calls.append(True)
        cancel_event.set()
        return None

    client = SimpleNamespace(
        beta=SimpleNamespace(
            agents=SimpleNamespace(sessions=SimpleNamespace(turns=SimpleNamespace(retrieve=cancelled_read)))
        )
    )
    result = helpers.poll_turn_usage(
        client,
        "sess_fixture",
        "turn_fixture",
        cancel_event=cancel_event,
        deadline=time.monotonic() + 20,
        wait_seconds=2,
    )
    assert result is None
    assert len(calls) == 1

    calls.clear()
    result = helpers.poll_turn_usage(
        client,
        "sess_fixture",
        "turn_fixture",
        cancel_event=threading.Event(),
        deadline=time.monotonic() - 1,
    )
    assert result is None
    assert calls == []


def test_usage_poll_attempt_count_is_bounded():
    calls = []

    def empty_read(*_, **__):
        calls.append(True)
        return None

    client = SimpleNamespace(
        beta=SimpleNamespace(
            agents=SimpleNamespace(sessions=SimpleNamespace(turns=SimpleNamespace(retrieve=empty_read)))
        )
    )
    result = helpers.poll_turn_usage(
        client,
        "sess_fixture",
        "turn_fixture",
        cancel_event=threading.Event(),
        deadline=time.monotonic() + 20,
        max_attempts=3,
        wait_seconds=0,
    )
    assert result is None
    assert len(calls) == 3


def test_usage_parser_rejects_conflicting_total():
    assert helpers.parse_usage({"input_tokens": 31, "output_tokens": 19}) == (31, 19, True)
    assert helpers.parse_usage({"input_tokens": 31, "output_tokens": 19, "total_tokens": 51}) == (
        0,
        0,
        False,
    )


def test_provider_errors_expose_only_allowlisted_reason_codes():
    assert OpenAIProviderError("limit", reason_code="tool_call_limit").reason_code == "tool_call_limit"
    assert OpenAIProviderError("timeout", reason_code="turn_timeout").reason_code == "turn_timeout"
    assert OpenAIProviderError("size", reason_code="tool_result_limit").reason_code == "tool_result_limit"
    assert OpenAIProviderError("unsafe", reason_code="secret:raw payload").reason_code is None


def test_turn_deadline_has_a_stable_reason_code(monkeypatch):
    import src.conversational_analytics.providers.openai as provider_module

    ticks = iter([0.0, 2.0])
    monkeypatch.setattr(provider_module.time, "monotonic", lambda: next(ticks))
    _, run = _limited_provider_run(
        [{"type": "agent.session.created", "session": {"id": "sess_fixture"}}],
        config={"max_turn_seconds": 1},
    )

    with pytest.raises(OpenAIProviderError) as caught:
        run()

    assert caught.value.reason_code == "turn_timeout"


def test_tool_call_limit_has_reason_code_after_first_validated_action():
    actions = [
        RequiredActionSessionRequiredActionResourceFunctionCall.model_validate(
            {
                "type": "function_call",
                "turn_id": "turn_provider",
                "call_id": call_id,
                "name": "get_metric_definition",
                "arguments": {"metric_id": "load_factor"},
            }
        )
        for call_id in ("call_one", "call_two")
    ]
    event = {
        "type": "agent.session.requires_action",
        "event_id": "evt_action",
        "turn_id": "turn_provider",
        "session": {"id": "sess_fixture", "required_actions": actions},
    }
    tool_events, run = _limited_provider_run(
        [
            {"type": "agent.session.created", "session": {"id": "sess_fixture"}},
            {"type": "agent.session.turn.created", "turn_id": "turn_provider"},
            event,
        ],
        config={"max_tool_calls": 1},
    )

    with pytest.raises(OpenAIProviderError) as caught:
        run()

    assert caught.value.reason_code == "tool_call_limit"
    assert caught.value.session_id == "sess_fixture"
    assert caught.value.turn_id == "turn_provider"
    assert len(tool_events) == 1


def test_post_cancel_usage_reads_only_exact_terminal_root_turn():
    from types import SimpleNamespace

    calls = []

    class Turns:
        def retrieve(self, turn_id, *, session_id, timeout):
            calls.append((turn_id, session_id, timeout))
            return SimpleNamespace(
                id=turn_id,
                session_id=session_id,
                status="cancelled",
                subagent_id=None,
                usage=SimpleNamespace(input_tokens=35_573, output_tokens=208, total_tokens=35_781),
            )

    client = SimpleNamespace(
        beta=SimpleNamespace(agents=SimpleNamespace(sessions=SimpleNamespace(turns=Turns())))
    )
    assert helpers.read_terminal_turn_usage_after_cancel(client, "sess_fixture", "turn_fixture") == (
        35_573,
        208,
    )
    assert len(calls) == 1
    assert calls[0][:2] == ("turn_fixture", "sess_fixture")
    assert 0 < calls[0][2] <= 5


def test_post_cancel_usage_recovers_after_four_fast_unavailable_reads(monkeypatch):
    clock = [0.0]
    monkeypatch.setattr(helpers.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(helpers.time, "sleep", lambda seconds: clock.__setitem__(0, clock[0] + seconds))
    calls = []

    class Turns:
        def retrieve(self, turn_id, *, session_id, timeout):
            calls.append((turn_id, session_id, timeout))
            if len(calls) < 5:
                return {"id": turn_id, "session_id": session_id, "status": "cancelled", "usage": None}
            return {
                "id": turn_id,
                "session_id": session_id,
                "status": "cancelled",
                "usage": {"input_tokens": 35_573, "output_tokens": 208},
            }

    client = SimpleNamespace(
        beta=SimpleNamespace(agents=SimpleNamespace(sessions=SimpleNamespace(turns=Turns())))
    )
    assert helpers.read_terminal_turn_usage_after_cancel(client, "sess_fixture", "turn_fixture") == (
        35_573,
        208,
    )
    assert len(calls) == 5
    assert all(0 < call[2] <= 5 for call in calls)
    assert clock[0] == 20


def test_post_cancel_usage_stays_unknown_at_deadline(monkeypatch):
    clock = [0.0]
    monkeypatch.setattr(helpers.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(helpers.time, "sleep", lambda seconds: clock.__setitem__(0, clock[0] + seconds))
    calls = []

    class Turns:
        def retrieve(self, turn_id, *, session_id, timeout):
            calls.append((turn_id, session_id, timeout))
            clock[0] += min(4.0, timeout)
            return {"id": turn_id, "session_id": session_id, "status": "cancelled", "usage": None}

    client = SimpleNamespace(
        beta=SimpleNamespace(agents=SimpleNamespace(sessions=SimpleNamespace(turns=Turns())))
    )
    assert helpers.read_terminal_turn_usage_after_cancel(client, "sess_fixture", "turn_fixture") is None
    assert len(calls) == 4
    assert clock[0] == helpers.POST_CANCEL_USAGE_TIMEOUT_SECONDS
    assert all(0 < call[2] <= 5 for call in calls)


@pytest.mark.parametrize(
    "turn_data",
    [
        {"id": "other", "status": "cancelled", "usage": {"input_tokens": 4, "output_tokens": 2}},
        {
            "id": "turn_fixture",
            "session_id": "other",
            "status": "cancelled",
            "usage": {"input_tokens": 4, "output_tokens": 2},
        },
        {
            "id": "turn_fixture",
            "status": "cancelled",
            "subagent_id": "sub",
            "usage": {"input_tokens": 4, "output_tokens": 2},
        },
        {"id": "turn_fixture", "status": "cancelled", "usage": {"input_tokens": None, "output_tokens": 2}},
    ],
)
def test_post_cancel_usage_rejects_unverified_or_incomplete_turn(turn_data, monkeypatch):
    from types import SimpleNamespace

    clock = [0.0]
    monkeypatch.setattr(helpers.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(helpers.time, "sleep", lambda seconds: clock.__setitem__(0, clock[0] + seconds))

    class Turns:
        def retrieve(self, *_args, **_kwargs):
            return turn_data

    client = SimpleNamespace(
        beta=SimpleNamespace(agents=SimpleNamespace(sessions=SimpleNamespace(turns=Turns())))
    )
    assert helpers.read_terminal_turn_usage_after_cancel(client, "sess_fixture", "turn_fixture") is None


def test_tool_result_limit_has_reason_code_for_locally_verified_oversize():
    action = RequiredActionSessionRequiredActionResourceFunctionCall.model_validate(
        {
            "type": "function_call",
            "turn_id": "turn_provider",
            "call_id": "call_oversize",
            "name": "get_metric_definition",
            "arguments": {"metric_id": "load_factor"},
        }
    )
    event = {
        "type": "agent.session.requires_action",
        "event_id": "evt_action",
        "turn_id": "turn_provider",
        "session": {"id": "sess_fixture", "required_actions": [action]},
    }
    _, run = _limited_provider_run(
        [
            {"type": "agent.session.created", "session": {"id": "sess_fixture"}},
            {"type": "agent.session.turn.created", "turn_id": "turn_provider"},
            event,
        ],
        config={"max_tool_result_bytes": 1},
        call_tool=lambda *_: {"validated": True},
    )

    with pytest.raises(OpenAIProviderError) as caught:
        run()

    assert caught.value.reason_code == "tool_result_limit"
