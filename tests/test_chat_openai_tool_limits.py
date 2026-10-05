"""Production-default tool-call bounds across multi-action turns."""

# The optional dependency must be gated before its generated types are imported.
# ruff: noqa: E402,I001

from __future__ import annotations

import pytest

openai = pytest.importorskip("openai")

from types import SimpleNamespace
from openai.types.beta.agent_session import RequiredActionSessionRequiredActionResourceFunctionCall
from test_chat_openai_usage import _limited_provider_run, _usage

from src.conversational_analytics.config import ChatConfig
from src.conversational_analytics.providers import _openai_helpers as helpers
from src.conversational_analytics.providers.openai import OpenAIProviderError


@pytest.mark.parametrize(
    "overrides",
    [
        {"id": "other-turn"},
        {"session_id": "other-session"},
        {"subagent_id": "child"},
        {"status": "in_progress"},
    ],
)
def test_usage_poll_rejects_nonmatching_or_nonterminal_turns(overrides):
    value = {"id": "turn-root", "session_id": "session-root", "subagent_id": None, "status": "completed",
             "usage": {"input_tokens": 31, "output_tokens": 19}}
    value.update(overrides)
    calls = []

    def retrieve(*_args, **_kwargs):
        calls.append(True)
        return value

    client = SimpleNamespace(
        beta=SimpleNamespace(agents=SimpleNamespace(sessions=SimpleNamespace(
            turns=SimpleNamespace(retrieve=retrieve)
        )))
    )

    assert helpers.poll_turn_usage(
        client,
        "session-root",
        "turn-root",
        cancel_event=SimpleNamespace(is_set=lambda: False),
        deadline=helpers.time.monotonic() + 100,
        max_attempts=1,
    ) is None
    assert calls == [True]


def test_completed_usage_poll_reaches_delayed_usage_within_thirty_second_window(monkeypatch):
    clock = [0.0]
    monkeypatch.setattr(helpers.time, "monotonic", lambda: clock[0])
    count = [0]

    class CancelEvent:
        def is_set(self):
            return False

        def wait(self, seconds):
            clock[0] += seconds
            return False

    class Turns:
        def retrieve(self, turn_id, *, session_id, timeout):
            count[0] += 1
            assert timeout > 0
            if count[0] < 12:
                return {"id": turn_id, "session_id": session_id, "subagent_id": None,
                        "status": "completed", "usage": None}
            return {"id": turn_id, "session_id": session_id, "subagent_id": None,
                    "status": "completed", "usage": {"input_tokens": 31, "output_tokens": 19}}

    sessions = SimpleNamespace(turns=Turns())
    client = SimpleNamespace(beta=SimpleNamespace(agents=SimpleNamespace(sessions=sessions)))
    usage = helpers.read_completed_turn_usage(
        client,
        "session-root",
        "turn-root",
        cancel_event=CancelEvent(),
        deadline=180,
        close_stream=lambda: None,
        wait_seconds=2,
    )

    assert usage == (31, 19)
    assert count[0] == 12
    assert 20 <= clock[0] < 30


def _function_actions(count):
    return [
        RequiredActionSessionRequiredActionResourceFunctionCall.model_validate(
            {
                "type": "function_call",
                "turn_id": "turn_provider",
                "call_id": f"call_{index}",
                "name": "get_metric_definition",
                "arguments": {"metric_id": "load_factor"},
            }
        )
        for index in range(count)
    ]


def _action_turn_events(actions):
    return [
        {"type": "agent.session.created", "session": {"id": "sess_fixture"}},
        {"type": "agent.session.turn.created", "turn_id": "turn_provider"},
        {
            "type": "agent.session.requires_action",
            "event_id": "evt_many_actions",
            "turn_id": "turn_provider",
            "session": {"id": "sess_fixture", "required_actions": actions},
        },
        {
            "type": "agent.session.turn.output_text.done",
            "turn_id": "turn_provider",
            "item_id": "answer",
            "output_index": 0,
            "content_index": 0,
            "text": "Respuesta completa con seis herramientas.",
        },
        {
            "type": "agent.session.turn.completed",
            "turn_id": "turn_provider",
            "turn": {"id": "turn_provider", "status": "completed", "usage": _usage()},
        },
    ]


def test_default_openai_limit_allows_six_tools_and_final_answer():
    assert ChatConfig().max_tool_calls == 8
    invoked = []
    tool_events, run = _limited_provider_run(
        _action_turn_events(_function_actions(6)),
        config={"max_tool_calls": ChatConfig().max_tool_calls},
        call_tool=lambda turn, call, name, args: (
            invoked.append((turn, call, name, args)) or {"definition": name}
        ),
    )

    result = run()

    assert result.content == "Respuesta completa con seis herramientas."
    assert len(invoked) == len(tool_events) == 6
    assert result.usage_complete is True


def test_default_openai_limit_still_rejects_ninth_tool_action():
    tool_events, run = _limited_provider_run(
        _action_turn_events(_function_actions(9)),
        config={"max_tool_calls": ChatConfig().max_tool_calls},
    )

    with pytest.raises(OpenAIProviderError) as caught:
        run()

    assert caught.value.reason_code == "tool_call_limit"
    assert len(tool_events) == 8
