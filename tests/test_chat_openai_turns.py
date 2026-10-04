"""Offline adapter tests for tool errors, history, failure usage and input limits."""

# ruff: noqa: E402,I001

from __future__ import annotations

import json

import pytest

pytest.importorskip("openai")

from openai.types.beta.agent_session import (
    AgentSession,
    RequiredActionSessionRequiredActionResourceFunctionCall,
)
from openai.types.beta.agent_session_requires_action_event import AgentSessionRequiresActionEvent
from openai.types.beta.agent_session_turn_failed_event import AgentSessionTurnFailedEvent

from src.conversational_analytics.providers.openai import OpenAIProviderError
from test_chat_openai import (
    FakeClient,
    FakeSessions,
    FakeStream,
    _completed,
    _provider,
    _run,
    _session_created,
    _text_done,
    _turn,
    _turn_created,
    _usage,
)


def _requires_action(call_id: str, arguments: dict, turn_id: str = "turn_provider"):
    action = RequiredActionSessionRequiredActionResourceFunctionCall.model_validate(
        {
            "type": "function_call",
            "turn_id": turn_id,
            "call_id": call_id,
            "name": "compare_metrics",
            "arguments": arguments,
        }
    )
    session = AgentSession.model_construct(
        id="sess_fixture", required_actions=[action], status="requires_action"
    )
    return AgentSessionRequiresActionEvent.model_construct(
        type="agent.session.requires_action", event_id=f"evt_{call_id}", session=session
    )


def test_rejected_tool_arguments_are_returned_to_the_model_as_failed_calls():
    fake = FakeSessions(
        create_stream=FakeStream(
            [
                _session_created(),
                _turn_created(),
                _requires_action("call_bad", {"metric_id": "load_factor", "entity_id": "AEROMEXICO"}),
                _text_done(text="Necesito dos periodos distintos."),
                _completed(),
            ]
        )
    )
    error = {"error": {"code": "tool_rejected", "message": "compare_metrics requiere dos periodos distintos"}}
    result, events, _ = _run(_provider(FakeClient(fake)), call_tool=lambda *_: error)

    sent = fake.events.created[0]["events"][0]
    assert sent["success"] is False and sent["call_id"] == "call_bad"
    assert sent["error"] == "compare_metrics requiere dos periodos distintos"
    assert "output" not in sent
    assert result.content == "Necesito dos periodos distintos."
    assert result.references == [] and result.chart is None


def test_new_session_for_existing_conversation_carries_bounded_history():
    fake = FakeSessions(
        create_stream=FakeStream([_session_created(), _turn_created(), _text_done(), _completed()])
    )
    messages = [
        {"role": "user", "content": "¿Factor de ocupación de Volaris en 2026Q2?"},
        {"role": "assistant", "content": "Fue 87.1% en 2026Q2."},
        {"role": "user", "content": "x" * 5_000},
        {"role": "assistant", "content": "Respuesta larga."},
        {"role": "user", "content": "¿Y el trimestre anterior?", "turn_id": "app-turn-3"},
    ]
    _run(_provider(FakeClient(fake)), messages=messages)

    envelope = json.loads(fake.created[0]["input"][0]["content"][0]["text"])
    assert envelope["question"] == "¿Y el trimestre anterior?"
    history = envelope["conversation_history"]
    assert history[0] == {"role": "user", "content": "¿Factor de ocupación de Volaris en 2026Q2?"}
    assert history[2]["content"] == "x" * 2_000  # each prior message is truncated
    assert history[-1] == {"role": "assistant", "content": "Respuesta larga."}


def test_existing_session_does_not_resend_history():
    event_stream = FakeStream([_turn_created("turn_new"), _text_done("turn_new"), _completed("turn_new")])
    fake = FakeSessions(event_stream=event_stream, prior_turns=[_turn("turn_old", status="completed")])
    messages = [
        {"role": "user", "content": "Primera"},
        {"role": "assistant", "content": "Respuesta"},
        {"role": "user", "content": "Segunda", "turn_id": "app-turn-2"},
    ]
    _run(_provider(FakeClient(fake)), session_id="sess_fixture", messages=messages)
    envelope = json.loads(fake.events.created[0]["events"][0]["input"][0]["content"][0]["text"])
    assert "conversation_history" not in envelope


def test_failed_turn_reports_provider_usage_for_quota_accounting():
    failed = AgentSessionTurnFailedEvent.model_validate(
        {
            "event_id": "evt_turn_failed",
            "session_id": "sess_fixture",
            "turn_id": "turn_provider",
            "type": "agent.session.turn.failed",
            "turn": _turn("turn_provider", status="failed", usage=_usage(120, 7)).model_dump(),
        }
    )
    fake = FakeSessions(
        event_stream=FakeStream([_turn_created(), failed]),
        prior_turns=[_turn("turn_old", status="completed")],
    )
    with pytest.raises(OpenAIProviderError) as raised:
        _run(_provider(FakeClient(fake)), session_id="sess_fixture")
    assert raised.value.usage == (120, 7)


def test_oversized_question_envelope_is_rejected_before_any_call():
    fake = FakeSessions()
    with pytest.raises(OpenAIProviderError, match="exceden"):
        _run(_provider(FakeClient(fake)), messages=[{"role": "user", "content": "á" * 7_000}])
    assert fake.created == []
