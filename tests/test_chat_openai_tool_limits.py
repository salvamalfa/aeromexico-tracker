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
from src.conversational_analytics.providers import openai as openai_provider_module
from src.conversational_analytics.providers.openai import OpenAIProvider, OpenAIProviderError


def test_provider_like_config_uses_production_default_limits():
    provider = OpenAIProvider(SimpleNamespace(openai_enabled=True, model="fake"), client=object())

    assert provider.max_tool_calls == 8
    assert provider.max_turn_seconds == 180


def test_eof_recovery_after_execution_deadline_is_rejected_with_known_usage(monkeypatch):
    clock = [0.0]
    monkeypatch.setattr(openai_provider_module.time, "monotonic", lambda: clock[0])

    def recover(self, *_args, deadline):
        assert deadline == 180.0
        clock[0] = 181.0
        return "Recovered answer", "completed", "turn_provider", {
            "input_tokens": 31,
            "output_tokens": 19,
        }

    monkeypatch.setattr(OpenAIProvider, "_recover", recover)
    _, run = _limited_provider_run(
        [
            {"type": "agent.session.created", "session": {"id": "sess_fixture"}},
            {"type": "agent.session.turn.created", "turn_id": "turn_provider"},
        ],
        config={"max_turn_seconds": 180},
    )

    with pytest.raises(OpenAIProviderError) as caught:
        run()

    assert caught.value.reason_code == "turn_timeout"
    assert getattr(caught.value, "usage", None) == (31, 19)


def test_late_completed_event_timeout_keeps_event_usage_without_answer(monkeypatch):
    ticks = iter([0.0, 0.0, 0.0, 181.0])
    monkeypatch.setattr(openai_provider_module.time, "monotonic", lambda: next(ticks))
    _, run = _limited_provider_run(
        [
            {"type": "agent.session.created", "session": {"id": "sess_fixture"}},
            {"type": "agent.session.turn.created", "turn_id": "turn_provider"},
            {
                "type": "agent.session.turn.completed",
                "turn_id": "turn_provider",
                "turn": {
                    "id": "turn_provider",
                    "status": "completed",
                    "usage": {"input_tokens": 31, "output_tokens": 19},
                },
            },
        ],
        config={"max_turn_seconds": 180},
    )

    with pytest.raises(OpenAIProviderError) as caught:
        run()

    assert caught.value.reason_code == "turn_timeout"
    assert getattr(caught.value, "usage", None) == (31, 19)


def test_completed_usage_survives_missing_final_text_after_recovery_timeout(monkeypatch):
    clock = [0.0]
    recoveries = []
    monkeypatch.setattr(openai_provider_module.time, "monotonic", lambda: clock[0])

    def recover(self, *_args, deadline):
        recoveries.append(deadline)
        clock[0] = 6.0
        return None

    monkeypatch.setattr(OpenAIProvider, "_recover", recover)
    _, run = _limited_provider_run(
        [
            {"type": "agent.session.created", "session": {"id": "sess_fixture"}},
            {"type": "agent.session.turn.created", "turn_id": "turn_provider"},
            {
                "type": "agent.session.turn.completed",
                "turn_id": "turn_provider",
                "turn": {
                    "id": "turn_provider",
                    "status": "completed",
                    "usage": _usage(),
                },
            },
        ]
    )

    with pytest.raises(OpenAIProviderError) as caught:
        run()

    assert caught.value.usage == (31, 19)
    assert recoveries == [5.0, 5.0]


@pytest.mark.parametrize("error_type", [RuntimeError, InterruptedError])
def test_local_error_after_completed_usage_keeps_usage(monkeypatch, error_type):
    monkeypatch.setattr(
        OpenAIProvider,
        "_recover",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        openai_provider_module,
        "references_from_results",
        lambda _results: (_ for _ in ()).throw(error_type("local formatter error")),
    )
    _, run = _limited_provider_run(
        [
            {"type": "agent.session.created", "session": {"id": "sess_fixture"}},
            {"type": "agent.session.turn.created", "turn_id": "turn_provider"},
            {
                "type": "agent.session.turn.output_text.done",
                "turn_id": "turn_provider",
                "text": "respuesta completa",
            },
            {
                "type": "agent.session.turn.completed",
                "turn_id": "turn_provider",
                "turn": {
                    "id": "turn_provider",
                    "status": "completed",
                    "usage": _usage(),
                },
            },
        ]
    )

    with pytest.raises(OpenAIProviderError if error_type is RuntimeError else InterruptedError) as caught:
        run()

    assert caught.value.usage == (31, 19)


@pytest.mark.parametrize("error_type", [RuntimeError, OpenAIProviderError])
def test_formatter_cancellation_after_completed_usage_skips_recovery(monkeypatch, error_type):
    cancel_event = {}
    recovery_calls = []
    original_guards = openai_provider_module.completion_guards

    def capture_cancel_event(event, *args, **kwargs):
        cancel_event["event"] = event
        return original_guards(event, *args, **kwargs)

    monkeypatch.setattr(openai_provider_module, "completion_guards", capture_cancel_event)
    monkeypatch.setattr(
        OpenAIProvider,
        "_recover",
        lambda *_args, **_kwargs: recovery_calls.append(True),
    )

    def cancel_then_fail(_results):
        cancel_event["event"].set()
        raise error_type("local formatter error")

    monkeypatch.setattr(openai_provider_module, "references_from_results", cancel_then_fail)
    _, run = _limited_provider_run(
        [
            {"type": "agent.session.created", "session": {"id": "sess_fixture"}},
            {"type": "agent.session.turn.created", "turn_id": "turn_provider"},
            {
                "type": "agent.session.turn.output_text.done",
                "turn_id": "turn_provider",
                "text": "respuesta completa",
            },
            {
                "type": "agent.session.turn.completed",
                "turn_id": "turn_provider",
                "turn": {
                    "id": "turn_provider",
                    "status": "completed",
                    "usage": _usage(),
                },
            },
        ]
    )

    with pytest.raises(OpenAIProviderError) as caught:
        run()

    assert caught.value.usage == (31, 19)
    assert recovery_calls == []


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
