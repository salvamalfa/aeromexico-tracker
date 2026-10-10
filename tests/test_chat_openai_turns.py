"""Offline adapter tests for tool errors, history, failure usage and input limits."""

# ruff: noqa: E402,I001

from __future__ import annotations

import json
import time
from types import SimpleNamespace

import pytest

pytest.importorskip("openai")

from openai.types.beta.agent_session import (
    AgentSession,
    RequiredActionSessionRequiredActionResourceFunctionCall,
)
from openai.types.beta.agent_session_idle_event import AgentSessionIdleEvent
from openai.types.beta.agent_session_requires_action_event import AgentSessionRequiresActionEvent
from openai.types.beta.agent_session_turn_failed_event import AgentSessionTurnFailedEvent

from src.conversational_analytics.providers.openai import OpenAIProviderError
from src.conversational_analytics.providers import openai as openai_provider_module
from src.conversational_analytics.providers._openai_recovery import retrieve_completed_turn_output
from test_chat_openai import (
    FakeClient,
    FakeSessions,
    FakeStream,
    _completed,
    _provider,
    _run,
    _session_created,
    _text_delta,
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
    assert raised.value.reason_code == "provider_terminal_failed"
    assert raised.value.session_id == "sess_fixture"
    assert raised.value.turn_id == "turn_provider"
    assert fake.retrieve_calls == 1
    # The initial session-version check is the only session read; terminal
    # failure must not trigger an additional recovery read.
    assert fake.turn_list_calls == 1


@pytest.mark.parametrize(
    "event_type",
    ["agent.session.failed", "agent.session.environment.failed", "error"],
)
@pytest.mark.parametrize("guard", ["normal", "deadline", "cancel"])
def test_late_session_failures_preserve_usage_and_skip_recovery_gets(
    monkeypatch, event_type, guard
):
    clock = [0.0]
    cancel_event = {}
    monkeypatch.setattr(openai_provider_module.time, "monotonic", lambda: clock[0])

    original_guards = openai_provider_module.completion_guards

    def capture_cancel_event(event, *args, **kwargs):
        cancel_event["event"] = event
        return original_guards(event, *args, **kwargs)

    monkeypatch.setattr(openai_provider_module, "completion_guards", capture_cancel_event)
    original_usage = openai_provider_module.usage_from_event

    def trigger_guard(data):
        if data.get("type") == event_type:
            if guard == "deadline":
                clock[0] = 5.0
            elif guard == "cancel":
                cancel_event["event"].set()
        return original_usage(data)

    monkeypatch.setattr(openai_provider_module, "usage_from_event", trigger_guard)

    fake = FakeSessions(
        event_stream=FakeStream(
            [
                _turn_created(),
                {"type": event_type, "usage": _usage(13, 2)},
            ]
        ),
        prior_turns=[_turn("turn_old", status="completed")],
    )

    expected_error = InterruptedError if guard == "cancel" else OpenAIProviderError
    with pytest.raises(expected_error) as raised:
        _run(_provider(FakeClient(fake)), session_id="sess_fixture")

    assert raised.value.usage == (13, 2)
    if guard == "deadline":
        assert raised.value.reason_code == "turn_timeout"
    elif guard == "normal":
        assert raised.value.reason_code == "provider_terminal_failed"
    assert fake.retrieve_calls == 1
    # The initial session-version check is the only session read.
    assert fake.turn_list_calls == 1


def test_recovery_gets_are_capped_by_the_original_turn_deadline():
    fake = FakeSessions()
    timeout_calls = []

    def retrieve(session_id, *, timeout):
        timeout_calls.append(("session", timeout))
        raise TimeoutError("offline provider")

    fake.retrieve = retrieve
    provider = _provider(FakeClient(fake))
    assert provider._recover(
        "sess_fixture", "turn_new", deadline=time.monotonic() + 0.25
    ) is None
    assert timeout_calls and timeout_calls[0][0] == "session"
    assert 0 < timeout_calls[0][1] <= 0.25
    assert fake.turn_list_calls == 0


def test_recovery_performs_no_get_after_turn_deadline():
    fake = FakeSessions()
    provider = _provider(FakeClient(fake))
    assert provider._recover("sess_fixture", "turn_new", deadline=0.0) is None
    assert provider._recover("sess_fixture", None, deadline=time.monotonic() + 1) is None
    assert fake.retrieve_calls == 0
    assert fake.turn_list_calls == 0


def test_oversized_question_envelope_is_rejected_before_any_call():
    fake = FakeSessions()
    with pytest.raises(OpenAIProviderError, match="exceden"):
        _run(_provider(FakeClient(fake)), messages=[{"role": "user", "content": "á" * 7_000}])
    assert fake.created == []


def test_recovered_answer_replaces_partial_deltas_instead_of_appending():
    completed_turn = _turn("turn_new", status="completed", usage=_usage()).model_dump()
    recovery = {
        "id": "sess_fixture",
        "status": "idle",
        "required_actions": [],
        "turns": [completed_turn],
        "items": [
            {
                "id": "item_assistant",
                "type": "message",
                "role": "assistant",
                "status": "completed",
                "turn_id": "turn_new",
                "content": [{"type": "output_text", "text": "El factor fue 87.1%."}],
            }
        ],
    }
    fake = FakeSessions(
        event_stream=FakeStream(
            [
                _turn_created("turn_new"),
                _text_delta("turn_new", "El factor fue"),
                AgentSessionIdleEvent.model_construct(
                    type="agent.session.idle", session={"id": "sess_fixture"}
                ),
            ]
        ),
        prior_turns=[_turn("turn_old", status="completed")],
        recovery=recovery,
    )
    result, _, _ = _run(_provider(FakeClient(fake)), session_id="sess_fixture")
    assert result.content == "El factor fue 87.1%."


def test_provider_error_recovers_only_exact_completed_turn_without_resending_input():
    completed_turn = _turn("turn_new", status="completed", usage=_usage(120, 7)).model_dump()
    recovery = {
        "id": "sess_fixture",
        "status": "idle",
        "required_actions": [],
        "turns": [completed_turn],
        "items": [
            {
                "id": "item_assistant",
                "type": "message",
                "role": "assistant",
                "status": "completed",
                "turn_id": "turn_new",
                "content": [{"type": "output_text", "text": "Respuesta recuperada."}],
            }
        ],
    }
    fake = FakeSessions(
        event_stream=FakeStream(
            [_turn_created("turn_new"), OpenAIProviderError("stream interrupted")]
        ),
        prior_turns=[_turn("turn_old", status="completed")],
        recovery=recovery,
    )

    result, _, _ = _run(_provider(FakeClient(fake)), session_id="sess_fixture")

    assert result.content == "Respuesta recuperada."
    assert (result.input_tokens, result.output_tokens, result.usage_complete) == (120, 7, True)
    assert len(fake.events.created) == 1
    assert fake.events.created[0]["events"][0]["type"] == "agent.session.input.message"


def test_recovery_uses_final_answer_items_in_chronological_part_order():
    completed_turn = _turn("turn_new", status="completed", usage=_usage()).model_dump()
    def final_part(item_id, text):
        return {
            "id": item_id,
            "type": "message",
            "role": "assistant",
            "status": "completed",
            "phase": "final_answer",
            "turn_id": "turn_new",
            "content": [{"type": "output_text", "text": text}],
        }
    recovery = {
        "id": "sess_fixture",
        "status": "idle",
        "required_actions": [],
        "turns": [completed_turn],
        # The API lists newest items first; content parts within each message
        # remain in their natural order.
        "items": [
            final_part("final-2", " mundo"),
            {
                "id": "commentary",
                "type": "message",
                "role": "assistant",
                "status": "completed",
                "phase": "commentary",
                "turn_id": "turn_new",
                "content": [{"type": "output_text", "text": "comentario"}],
            },
            {
                "id": "reasoning",
                "type": "message",
                "role": "assistant",
                "status": "completed",
                "phase": "analysis",
                "turn_id": "turn_new",
                "content": [{"type": "output_text", "text": "razonamiento"}],
            },
            {
                **final_part("final-1", ""),
                "content": [
                    {"type": "output_text", "text": "Hola"},
                    {"type": "output_text", "text": " "},
                    {"type": "output_text", "text": "bienvenido"},
                ],
            },
        ],
    }
    fake = FakeSessions(
        event_stream=FakeStream(
            [_turn_created("turn_new"), OpenAIProviderError("stream interrupted")]
        ),
        prior_turns=[_turn("turn_old", status="completed")],
        recovery=recovery,
    )

    result, _, _ = _run(_provider(FakeClient(fake)), session_id="sess_fixture")

    assert result.content == "Hola bienvenido mundo"


def test_recovery_rejects_partial_item_page_instead_of_returning_partial_text():
    completed_turn = _turn("turn_new", status="completed", usage=_usage()).model_dump()
    recovery = {
        "id": "sess_fixture",
        "status": "idle",
        "required_actions": [],
        "turns": [completed_turn],
        "items_has_more": True,
        "items": [
            {
                "id": "final",
                "type": "message",
                "role": "assistant",
                "status": "completed",
                "phase": "final_answer",
                "turn_id": "turn_new",
                "content": [{"type": "output_text", "text": "parcial"}],
            }
        ],
    }
    fake = FakeSessions(
        event_stream=FakeStream(
            [_turn_created("turn_new"), OpenAIProviderError("stream interrupted")]
        ),
        prior_turns=[_turn("turn_old", status="completed")],
        recovery=recovery,
    )

    with pytest.raises(OpenAIProviderError, match="stream interrupted"):
        _run(_provider(FakeClient(fake)), session_id="sess_fixture")

    assert len(fake.events.created) == 1


def test_recovery_paginates_past_more_than_one_page_of_exact_turn_items():
    class PagedItems:
        def __init__(self, items):
            self.items = items
            self.calls = []

        def list(self, session_id, *, limit, order, timeout, after=None):
            assert session_id == "sess_fixture"
            assert order == "desc" and timeout > 0
            self.calls.append(after)
            start = next(
                (index + 1 for index, item in enumerate(self.items) if item["id"] == after), 0
            )
            page_items = self.items[start : start + limit]
            return SimpleNamespace(
                data=page_items,
                has_more=start + len(page_items) < len(self.items),
            )

    current_turn = [
        {
            "id": "final-answer",
            "type": "message",
            "role": "assistant",
            "status": "completed",
            "phase": "final_answer",
            "turn_id": "turn_new",
            "content": [{"type": "output_text", "text": "Turno recuperado."}],
        },
        *[
            {"id": f"current-{index}", "type": "function_call", "turn_id": "turn_new"}
            for index in range(1, 150)
        ],
    ]
    older_turns = [
        {"id": f"old-{index}", "type": "function_call", "turn_id": "turn_old"}
        for index in range(200)
    ]
    items = PagedItems(current_turn + older_turns)
    client = SimpleNamespace(
        beta=SimpleNamespace(
            agents=SimpleNamespace(sessions=SimpleNamespace(items=items))
        )
    )

    assert retrieve_completed_turn_output(client, "sess_fixture", "turn_new") == "Turno recuperado."
    assert len(items.calls) == 2
    assert items.calls[0] is None
    assert items.calls[1] == "current-99"


def test_recovery_rejects_overlapping_cursor_pages():
    final_item = {
        "id": "final-answer",
        "type": "message",
        "role": "assistant",
        "status": "completed",
        "phase": "final_answer",
        "turn_id": "turn_new",
        "content": [{"type": "output_text", "text": "No duplicar."}],
    }

    class OverlappingItems:
        calls = 0

        def list(self, session_id, *, limit, order, timeout, after=None):
            assert session_id == "sess_fixture"
            self.calls += 1
            if after is None:
                return SimpleNamespace(data=[final_item], has_more=True)
            assert after == "final-answer"
            return SimpleNamespace(
                data=[final_item, {"id": "old", "turn_id": "turn_old"}],
                has_more=False,
            )

    items = OverlappingItems()
    client = SimpleNamespace(
        beta=SimpleNamespace(
            agents=SimpleNamespace(sessions=SimpleNamespace(items=items))
        )
    )

    assert retrieve_completed_turn_output(client, "sess_fixture", "turn_new") == ""
    assert items.calls == 2


@pytest.mark.parametrize(
    "item",
    [
        {
            "id": "final",
            "type": "message",
            "role": "assistant",
            "status": "in_progress",
            "phase": "final_answer",
            "turn_id": "turn_new",
            "content": [{"type": "output_text", "text": "aún no terminó"}],
        },
        {
            "id": "legacy",
            "type": "message",
            "role": "assistant",
            "status": "completed",
            "turn_id": "turn_new",
            "content": [{"type": "output_text", "text": "respuesta antigua"}],
        },
    ],
)
def test_recovery_does_not_accept_incomplete_or_shadowed_legacy_final_item(item):
    items = [item]
    if item["id"] == "legacy":
        items.insert(
            0,
            {
                "id": "later-commentary",
                "type": "message",
                "role": "assistant",
                "status": "completed",
                "phase": "commentary",
                "turn_id": "turn_new",
                "content": [{"type": "output_text", "text": "comentario posterior"}],
            },
        )
    fake = FakeSessions(
        recovery={"items": items},
    )

    assert retrieve_completed_turn_output(FakeClient(fake), "sess_fixture", "turn_new") == ""


@pytest.mark.parametrize(
    ("recovery_turn_id", "recovery_session_id"),
    [("turn_old", "sess_fixture"), ("turn_other", "sess_fixture"), ("turn_new", "sess_other")],
)
def test_provider_error_does_not_recover_a_prior_or_different_turn(
    recovery_turn_id, recovery_session_id
):
    recovery = {
        "id": "sess_fixture",
        "status": "idle",
        "required_actions": [],
        "turns": [
            {
                **_turn(recovery_turn_id, status="completed", usage=_usage()).model_dump(),
                "session_id": recovery_session_id,
            }
        ],
        "items": [
            {
                "id": "item_assistant",
                "type": "message",
                "role": "assistant",
                "turn_id": recovery_turn_id,
                "content": [{"type": "output_text", "text": "No corresponde."}],
            }
        ],
    }
    fake = FakeSessions(
        event_stream=FakeStream(
            [_turn_created("turn_new"), OpenAIProviderError("stream interrupted")]
        ),
        prior_turns=[_turn("turn_old", status="completed")],
        recovery=recovery,
    )

    with pytest.raises(OpenAIProviderError, match="stream interrupted"):
        _run(_provider(FakeClient(fake)), session_id="sess_fixture")

    assert len(fake.events.created) == 1


def test_hardguard_provider_error_still_bypasses_success_recovery():
    completed_turn = _turn("turn_new", status="completed", usage=_usage()).model_dump()
    recovery = {
        "id": "sess_fixture",
        "status": "idle",
        "required_actions": [],
        "turns": [completed_turn],
        "items": [
            {
                "id": "item_assistant",
                "type": "message",
                "role": "assistant",
                "turn_id": "turn_new",
                "content": [{"type": "output_text", "text": "No debe aceptarse."}],
            }
        ],
    }
    error = OpenAIProviderError(
        "hardguard", reason_code="tool_call_limit", session_id="sess_fixture", turn_id="turn_new"
    )
    fake = FakeSessions(
        event_stream=FakeStream([_turn_created("turn_new"), error]),
        prior_turns=[_turn("turn_old", status="completed")],
        recovery=recovery,
    )

    with pytest.raises(OpenAIProviderError, match="hardguard") as raised:
        _run(_provider(FakeClient(fake)), session_id="sess_fixture")

    assert raised.value.reason_code == "tool_call_limit"
    assert fake.retrieve_calls == 1
