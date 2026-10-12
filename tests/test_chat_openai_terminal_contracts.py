"""Terminal lifecycle and tool allowlist checks split from the core SDK tests."""

from __future__ import annotations

import pytest
import test_chat_openai as sdk_tests

OpenAIProviderError = sdk_tests.OpenAIProviderError
AgentSessionIdleEvent = sdk_tests.AgentSessionIdleEvent
FakeClient = sdk_tests.FakeClient
FakeSessions = sdk_tests.FakeSessions
FakeStream = sdk_tests.FakeStream
_failed = sdk_tests._failed
_cancelled = sdk_tests._cancelled
_provider = sdk_tests._provider
_run = sdk_tests._run
_turn = sdk_tests._turn
_turn_created = sdk_tests._turn_created
_usage = sdk_tests._usage
_specs = sdk_tests._specs
validate_tool_specs = sdk_tests.validate_tool_specs


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
    assert fake.retrieve_calls == 2  # session-version check plus terminal recovery read
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
    assert len(validate_tool_specs(specs)) == 7
    with pytest.raises(OpenAIProviderError, match="herramienta desconocida"):
        validate_tool_specs(specs + [{"type": "function", "name": "shell", "parameters": {}}])
