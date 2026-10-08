"""Offline contract tests against typed events in the official OpenAI SDK."""

# The optional dependency must be gated before its generated types are imported.
# ruff: noqa: E402,I001

from __future__ import annotations

import json
import threading
from types import SimpleNamespace

import pytest

openai = pytest.importorskip("openai")

from openai.types.beta.agent_session import (  # noqa: E402
    AgentSession,
    RequiredActionSessionRequiredActionResourceFunctionCall,
)
from openai.types.beta.agent_session_created_event import AgentSessionCreatedEvent  # noqa: E402
from openai.types.beta.agent_session_idle_event import AgentSessionIdleEvent  # noqa: E402
from openai.types.beta.agent_session_requires_action_event import AgentSessionRequiresActionEvent  # noqa: E402
from openai.types.beta.agent_session_turn_cancelled_event import AgentSessionTurnCancelledEvent  # noqa: E402
from openai.types.beta.agent_session_turn_completed_event import AgentSessionTurnCompletedEvent  # noqa: E402
from openai.types.beta.agent_session_turn_created_event import AgentSessionTurnCreatedEvent  # noqa: E402
from openai.types.beta.agent_session_turn_failed_event import AgentSessionTurnFailedEvent  # noqa: E402
from openai.types.beta.agent_session_turn_output_text_delta_event import AgentSessionTurnOutputTextDeltaEvent  # noqa: E402
from openai.types.beta.agent_session_turn_output_text_done_event import AgentSessionTurnOutputTextDoneEvent  # noqa: E402
from openai.types.beta.agents.sessions.turn import Turn  # noqa: E402

from src.conversational_analytics.providers.openai import OpenAIProvider, OpenAIProviderError  # noqa: E402
from src.conversational_analytics.tools.registry import ToolRegistry  # noqa: E402


def _usage(input_tokens: int = 31, output_tokens: int = 19) -> dict:
    return {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": input_tokens + output_tokens,
        "input_tokens_details": {"cached_tokens": 0},
        "output_tokens_details": {"reasoning_tokens": 4},
    }


def _turn(turn_id: str, *, status: str = "in_progress", subagent_id=None, usage=None) -> Turn:
    value = {
        "id": turn_id,
        "agent_id": "agent_fixture",
        "created_at": 1_791_100_000,
        "object": "agent.session.turn",
        "session_id": "sess_fixture",
        "status": status,
        "subagent_id": subagent_id,
    }
    if usage is not None:
        value["usage"] = usage
    return Turn.model_validate(value)


def _session_created(session_id: str = "sess_fixture"):
    session = AgentSession.model_construct(id=session_id, required_actions=[], status="in_progress")
    return AgentSessionCreatedEvent.model_construct(
        event_id="evt_session_created", session=session, type="agent.session.created"
    )


def _turn_created(turn_id: str = "turn_provider"):
    return AgentSessionTurnCreatedEvent.model_validate(
        {
            "event_id": "evt_turn_created",
            "session_id": "sess_fixture",
            "turn_id": turn_id,
            "type": "agent.session.turn.created",
            "turn": _turn(turn_id).model_dump(),
        }
    )


def _text_delta(turn_id: str = "turn_provider", delta: str = "Respuesta"):
    return AgentSessionTurnOutputTextDeltaEvent.model_validate(
        {
            "event_id": "evt_text_delta",
            "session_id": "sess_fixture",
            "turn_id": turn_id,
            "item_id": "item_assistant",
            "output_index": 0,
            "content_index": 0,
            "type": "agent.session.turn.output_text.delta",
            "delta": delta,
        }
    )


def _text_done(turn_id: str = "turn_provider", text: str = "Respuesta final"):
    return AgentSessionTurnOutputTextDoneEvent.model_validate(
        {
            "event_id": "evt_text_done",
            "session_id": "sess_fixture",
            "turn_id": turn_id,
            "item_id": "item_assistant",
            "output_index": 0,
            "content_index": 0,
            "type": "agent.session.turn.output_text.done",
            "text": text,
        }
    )


def _completed(turn_id: str = "turn_provider", usage=None):
    return AgentSessionTurnCompletedEvent.model_validate(
        {
            "event_id": "evt_turn_completed",
            "session_id": "sess_fixture",
            "turn_id": turn_id,
            "type": "agent.session.turn.completed",
            "turn": _turn(turn_id, status="completed", usage=usage or _usage()).model_dump(),
            "usage": usage or _usage(),
        }
    )


def _completed_without_usage(turn_id: str = "turn_provider"):
    return AgentSessionTurnCompletedEvent.model_validate(
        {
            "event_id": "evt_turn_completed",
            "session_id": "sess_fixture",
            "turn_id": turn_id,
            "type": "agent.session.turn.completed",
            "turn": _turn(turn_id, status="completed").model_dump(),
        }
    )


def _failed(turn_id: str = "turn_provider"):
    return AgentSessionTurnFailedEvent.model_validate(
        {
            "event_id": "evt_turn_failed",
            "session_id": "sess_fixture",
            "turn_id": turn_id,
            "type": "agent.session.turn.failed",
            "turn": _turn(turn_id, status="failed").model_dump(),
        }
    )


def _cancelled(turn_id: str = "turn_provider"):
    return AgentSessionTurnCancelledEvent.model_validate(
        {
            "event_id": "evt_turn_cancelled",
            "session_id": "sess_fixture",
            "turn_id": turn_id,
            "type": "agent.session.turn.cancelled",
            "turn": _turn(turn_id, status="cancelled").model_dump(),
        }
    )


class FakeStream:
    def __init__(self, events):
        self.events = list(events)
        self.entered = False
        self.closed = False
        self.read_count = 0

    def with_result_collection(self):
        return self

    def __enter__(self):
        self.entered = True

        def iterate():
            for event in self.events:
                self.read_count += 1
                if isinstance(event, BaseException):
                    raise event
                yield event

        return iterate()

    def __exit__(self, *_):
        self.closed = True


class FakeEvents:
    def __init__(self, stream_factory):
        self._stream_factory = stream_factory
        self.stream_was_open = False
        self.created = []
        self.streams = []

    def stream(self, session_id):
        assert session_id == "sess_fixture"
        stream = self._stream_factory()
        self.streams.append(stream)
        self.stream_was_open = True
        return stream

    def create(self, session_id, **kwargs):
        assert session_id == "sess_fixture"
        events = kwargs.get("events", [])
        if any(event.get("type") == "agent.session.input.message" for event in events):
            assert self.stream_was_open, "follow-up input must be sent after subscribing"
        self.created.append(kwargs)
        return SimpleNamespace(id="accepted")


class FakeSessions:
    def __init__(
        self,
        *,
        create_stream=None,
        event_stream=None,
        prior_turns=None,
        recovery=None,
        retrieved_turn=None,
    ):
        self._create_stream = create_stream or FakeStream([])
        self.events = FakeEvents(lambda: event_stream or FakeStream([]))
        self._prior_turns = list(prior_turns or [])
        self._recovery = recovery
        self.created = []
        self.deleted = []
        self.retrieve_calls = 0
        self.retrieve_timeouts = []
        self.turn_list_calls = 0
        self.turn_list_timeouts = []
        self.retrieved_turn = retrieved_turn
        self._retrieved_turns = list(retrieved_turn) if isinstance(retrieved_turn, list) else None
        self.turn_retrieve_calls = []
        self.stream_closed_at_turn_retrieve = []
        self.turns = SimpleNamespace(list=self._list_turns, retrieve=self._retrieve_turn)
        self.items = SimpleNamespace(list=self._list_items)

    def create(self, **kwargs):
        self.created.append(kwargs)
        if kwargs.get("stream") is True:
            # Session creation with stream=True both creates the first turn and
            # opens the subscription before the initial input is processed.
            self.events.stream_was_open = True
        return self._create_stream

    def retrieve(self, session_id, *, timeout=None):
        assert session_id == "sess_fixture"
        self.retrieve_calls += 1
        self.retrieve_timeouts.append(timeout)
        return self._recovery or {"id": session_id, "status": "idle", "required_actions": []}

    def delete(self, session_id):
        self.deleted.append(session_id)

    def _list_turns(self, session_id, **kwargs):
        assert session_id == "sess_fixture"
        self.turn_list_calls += 1
        self.turn_list_timeouts.append(kwargs.get("timeout"))
        if self._recovery and self.turn_list_calls > 1:
            turns = self._recovery.get("turns", [])
        else:
            turns = self._prior_turns
        return SimpleNamespace(data=turns)

    def _list_items(self, session_id, **kwargs):
        assert session_id == "sess_fixture"
        items = self._recovery or {}
        return SimpleNamespace(data=items.get("items", []), has_more=bool(items.get("items_has_more")))

    def _retrieve_turn(self, turn_id, *, session_id, timeout):
        self.turn_retrieve_calls.append((turn_id, session_id, timeout))
        self.stream_closed_at_turn_retrieve.append(self._create_stream.closed)
        if self._retrieved_turns is not None:
            return self._retrieved_turns.pop(0) if self._retrieved_turns else None
        return self.retrieved_turn


class FakeClient:
    def __init__(self, sessions):
        self.beta = SimpleNamespace(agents=SimpleNamespace(sessions=sessions))


def _provider(client, **config_overrides):
    values = {"openai_enabled": True, "model": "model-explicit", "max_turn_seconds": 5}
    values.update(config_overrides)
    return OpenAIProvider(SimpleNamespace(**values), client=client)


def _specs():
    return ToolRegistry._make_specs()


def _run(provider, *, session_id=None, events=None, context=None, call_tool=None, messages=None):
    emissions = []
    saved_sessions = []
    result = provider.run_turn(
        session_id=session_id,
        messages=messages
        or [{"role": "user", "content": "¿Cómo cambió el factor de ocupación?", "turn_id": "app-turn-1"}],
        context=context or {"tab": "executive", "period": "2026Q1", "entity": "AEROMEXICO"},
        tool_specs=_specs(),
        call_tool=call_tool or (lambda provider_turn, call_id, name, args: {"ok": True}),
        emit=lambda kind, payload: emissions.append((kind, payload)),
        persist_session=saved_sessions.append,
        cancel_event=threading.Event(),
    )
    return result, emissions, saved_sessions


def test_creates_none_session_with_explicit_model_tools_and_live_context_envelope():
    fake = FakeSessions(
        create_stream=FakeStream(
            [
                _session_created(),
                _turn_created(),
                _text_delta(),
                _text_done(),
                _completed(),
                AssertionError("provider consumed events after the intended terminal turn"),
            ]
        )
    )
    provider = _provider(FakeClient(fake))

    result, events, saved = _run(provider)

    request = fake.created[0]
    assert request["environment"] == {"type": "none"}
    assert request["agent"]["model"] == "model-explicit"
    assert len(request["agent"]["tools"]) == 7
    assert {tool["name"] for tool in request["agent"]["tools"]} == {
        "get_data_catalog",
        "get_metric_definition",
        "query_metrics",
        "compare_metrics",
        "get_time_series",
        "get_source_references",
        "get_dashboard_context",
    }
    assert "OPENAI_API_KEY" not in request["agent"]["instructions"]
    envelope = json.loads(request["input"][0]["content"][0]["text"])
    assert envelope == {
        "dashboard_context": {"tab": "executive", "period": "2026Q1", "entity": "AEROMEXICO"},
        "question": "¿Cómo cambió el factor de ocupación?",
    }
    assert saved == ["sess_fixture"]
    assert result.provider_session_id == "sess_fixture"
    assert result.content == "Respuesta final"
    assert (result.input_tokens, result.output_tokens, result.usage_complete) == (31, 19, True)
    assert any(
        kind == "provider.metadata" and payload["provider_event_id"] == "evt_turn_completed"
        for kind, payload in events
    )
    assert fake._create_stream.read_count == 5


def test_cancel_during_session_creation_persists_first_discovered_session_before_interrupt():
    cancel_event = threading.Event()

    class CancellingSessions(FakeSessions):
        def create(self, **kwargs):
            stream = super().create(**kwargs)
            cancel_event.set()
            return stream

    fake = CancellingSessions(create_stream=FakeStream([_session_created()]))
    provider = _provider(FakeClient(fake))
    saved_sessions = []
    emissions = []

    with pytest.raises(InterruptedError, match="turn cancelled"):
        provider.run_turn(
            session_id=None,
            messages=[{"role": "user", "content": "Pregunta", "turn_id": "app-turn"}],
            context={"period": "2026Q2"},
            tool_specs=_specs(),
            call_tool=lambda *_: pytest.fail("cancelled turn dispatched a tool"),
            emit=lambda kind, payload: emissions.append((kind, payload)),
            persist_session=saved_sessions.append,
            cancel_event=cancel_event,
        )

    assert saved_sessions == ["sess_fixture"]
    assert any(payload.get("provider_event_type") == "agent.session.created" for _, payload in emissions)
    assert fake._create_stream.read_count == 1


def test_function_call_uses_official_required_action_shape_and_persists_provider_turn_call_ids():
    action = RequiredActionSessionRequiredActionResourceFunctionCall.model_validate(
        {
            "type": "function_call",
            "turn_id": "provider-turn-different-from-local-turn",
            "call_id": "call_123",
            "name": "get_metric_definition",
            "arguments": {"metric_id": "load_factor"},
        }
    )
    session = AgentSession.model_construct(
        id="sess_fixture", required_actions=[action], status="requires_action"
    )
    requires_action = AgentSessionRequiresActionEvent.model_construct(
        type="agent.session.requires_action", event_id="evt_action", session=session
    )
    fake = FakeSessions(
        create_stream=FakeStream(
            [
                _session_created(),
                _turn_created("provider-turn-different-from-local-turn"),
                requires_action,
                _text_done("provider-turn-different-from-local-turn", "Factor de ocupación consultado."),
                _completed("provider-turn-different-from-local-turn"),
            ]
        )
    )
    calls = []
    provider = _provider(FakeClient(fake))
    result, events, _ = _run(
        provider,
        call_tool=lambda turn, call, name, args: (
            calls.append((turn, call, name, args))
            or {
                "metric": {"id": "load_factor"},
                "source_references": [
                    {
                        "label": "Dashboard público",
                        "url": "https://salvamalfa.github.io/aeromexico-tracker/data/v1/executive.json",
                    }
                ],
            }
        ),
    )

    assert calls == [
        (
            "provider-turn-different-from-local-turn",
            "call_123",
            "get_metric_definition",
            {"metric_id": "load_factor"},
        )
    ]
    tool_result = fake.events.created[0]["events"][0]
    assert tool_result == {
        "type": "agent.session.input.tool_result",
        "turn_id": "provider-turn-different-from-local-turn",
        "call_id": "call_123",
        "success": True,
        "output": json.dumps(
            calls
            and {
                "metric": {"id": "load_factor"},
                "source_references": [
                    {
                        "label": "Dashboard público",
                        "url": "https://salvamalfa.github.io/aeromexico-tracker/data/v1/executive.json",
                    }
                ],
            },
            ensure_ascii=False,
            separators=(",", ":"),
        ),
    }
    assert result.references == [
        {
            "label": "Dashboard público",
            "url": "https://salvamalfa.github.io/aeromexico-tracker/data/v1/executive.json",
        }
    ]
    assert any(
        kind == "tool.completed" and payload["name"] == "get_metric_definition" for kind, payload in events
    )


def test_existing_session_subscribes_before_input_and_sends_current_context_on_every_turn():
    turn_old = _turn("turn_old", status="completed")
    event_stream = FakeStream(
        [
            _turn_created("turn_new"),
            _text_done("turn_new", "Respuesta al periodo actual."),
            _completed("turn_new"),
        ]
    )
    fake = FakeSessions(event_stream=event_stream, prior_turns=[turn_old])
    provider = _provider(FakeClient(fake))
    new_context = {"tab": "economy", "period": "2026Q2", "entity": "VOLARIS"}

    result, _, saved = _run(provider, session_id="sess_fixture", context=new_context)

    assert fake.events.streams[0].entered
    assert fake.events.created[0]["idempotency_key"] == "airline-tracker-turn-app-turn-1"
    envelope = json.loads(fake.events.created[0]["events"][0]["input"][0]["content"][0]["text"])
    assert envelope["dashboard_context"] == new_context
    assert result.content == "Respuesta al periodo actual."
    assert result.provider_session_id == "sess_fixture"
    assert saved == ["sess_fixture"]
    assert event_stream.closed


@pytest.mark.parametrize("terminal", [_failed(), _cancelled()], ids=["failed", "cancelled"])
def test_terminal_failure_and_cancellation_are_not_reported_as_completed(terminal):
    fake = FakeSessions(
        event_stream=FakeStream([_turn_created(), terminal]),
        prior_turns=[_turn("turn_old", status="completed")],
    )
    provider = _provider(FakeClient(fake))

    with pytest.raises((OpenAIProviderError, InterruptedError)):
        _run(provider, session_id="sess_fixture")


def test_idle_without_new_terminal_turn_is_not_success():
    old = _turn("turn_old", status="completed")
    fake = FakeSessions(
        event_stream=FakeStream(
            [AgentSessionIdleEvent.model_construct(type="agent.session.idle", session={"id": "sess_fixture"})]
        ),
        prior_turns=[old],
        recovery={"id": "sess_fixture", "status": "idle", "required_actions": [], "turns": [old]},
    )
    provider = _provider(FakeClient(fake))

    with pytest.raises(OpenAIProviderError, match="sin resultado terminal"):
        _run(provider, session_id="sess_fixture")


@pytest.mark.parametrize(
    ("status", "error_type"),
    [("failed", OpenAIProviderError), ("cancelled", InterruptedError)],
)
def test_recovered_terminal_failure_or_cancel_preserves_reported_usage(status, error_type):
    recovered_turn = _turn("turn_recovered", status=status, usage=_usage())
    fake = FakeSessions(
        event_stream=FakeStream(
            [
                _turn_created("turn_recovered"),
                AgentSessionIdleEvent.model_construct(
                    type="agent.session.idle", session={"id": "sess_fixture"}
                ),
            ]
        ),
        prior_turns=[_turn("turn_old", status="completed")],
        recovery={"id": "sess_fixture", "status": "idle", "required_actions": [], "turns": [recovered_turn]},
    )
    with pytest.raises(error_type) as caught:
        _run(_provider(FakeClient(fake)), session_id="sess_fixture")
    assert caught.value.usage == (31, 19)
    if status == "failed":
        assert caught.value.reason_code == "provider_terminal_failed"
        assert caught.value.session_id == "sess_fixture"
        assert caught.value.turn_id == "turn_recovered"
    assert fake.retrieve_calls == 1
    assert fake.turn_list_calls == 2  # prior turn lookup plus one recovery read
    assert 0 < fake.retrieve_timeouts[-1] <= 180
    assert 0 < fake.turn_list_timeouts[-1] <= fake.retrieve_timeouts[-1]


def test_cancel_and_delete_use_documented_events_and_session_endpoint():
    fake = FakeSessions()
    provider = _provider(FakeClient(fake))

    provider.cancel("sess_fixture")
    provider.delete("sess_fixture")

    assert fake.events.created[0]["events"] == [{"type": "agent.session.input.cancel"}]
    assert fake.deleted == ["sess_fixture"]


def test_tool_schema_is_exactly_allowlisted_and_closed():
    specs = _specs()
    assert len(OpenAIProvider._validate_tool_specs(specs)) == 7
    with pytest.raises(OpenAIProviderError, match="herramienta desconocida"):
        OpenAIProvider._validate_tool_specs(specs + [{"type": "function", "name": "shell", "parameters": {}}])


def test_openai_client_requires_existing_key_without_printing_or_probing(monkeypatch, capsys):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    with pytest.raises(OpenAIProviderError, match="no está configurada"):
        OpenAIProvider(SimpleNamespace(openai_enabled=True, model="explicit-model"))

    assert capsys.readouterr().out == ""
