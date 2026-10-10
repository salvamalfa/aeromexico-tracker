"""Offline tests for prompt-versioned persisted OpenAI sessions."""

import hashlib
import json
import threading

import pytest
from test_chat_openai import (
    FakeClient,
    FakeSessions,
    FakeStream,
    _completed,
    _provider,
    _run,
    _session_created,
    _specs,
    _text_done,
    _turn,
    _turn_created,
)

from src.conversational_analytics.providers._openai_helpers import SYSTEM_INSTRUCTIONS, OpenAIProviderError
from src.conversational_analytics.providers._openai_session_version import INSTRUCTIONS_FINGERPRINT_KEY


@pytest.mark.parametrize(
    "session_metadata",
    [{}, {INSTRUCTIONS_FINGERPRINT_KEY: "old"}],
    ids=["legacy", "stale"],
)
def test_old_prompt_session_rotates_once_with_history_and_current_context(session_metadata):
    fake = FakeSessions(
        create_stream=FakeStream(
            [
                _session_created("sess_new"),
                _turn_created(session_id="sess_new"),
                _text_done(text="Respuesta con instrucciones vigentes.", session_id="sess_new"),
                _completed(session_id="sess_new"),
            ]
        ),
        session_metadata=session_metadata,
    )
    provider = _provider(FakeClient(fake))
    messages = [
        {"role": "user", "content": "Consulta previa", "id": "old-user"},
        {"role": "assistant", "content": "Respuesta previa", "id": "old-assistant"},
        {"role": "user", "content": "¿Y para este periodo?", "turn_id": "app-turn-current"},
    ]
    context = {"tab": "reading", "period": "2026Q2", "entity": "AEROMEXICO"}
    retired: list[str] = []

    result, _, saved = _run(
        provider,
        session_id="sess_fixture",
        messages=messages,
        context=context,
        retire_session=retired.append,
    )

    request = fake.created[0]
    envelope = json.loads(request["input"][0]["content"][0]["text"])
    assert envelope["dashboard_context"] == context
    assert envelope["conversation_history"] == [
        {"role": "user", "content": "Consulta previa"},
        {"role": "assistant", "content": "Respuesta previa"},
    ]
    assert (
        request["metadata"][INSTRUCTIONS_FINGERPRINT_KEY]
        == hashlib.sha256(SYSTEM_INSTRUCTIONS.encode("utf-8")).hexdigest()
    )
    assert fake.events.created == []
    assert result.provider_session_id == "sess_new"
    assert saved == ["sess_new"]
    assert retired == ["sess_fixture"]


def test_cannot_verify_reused_session_prompt_without_sending_input():
    fake = FakeSessions(retrieve_error=RuntimeError("private provider detail"))
    provider = _provider(FakeClient(fake))
    saved: list[str] = []

    with pytest.raises(OpenAIProviderError, match="verificar la versión de instrucciones"):
        provider.run_turn(
            session_id="sess_fixture",
            messages=[{"role": "user", "content": "¿Y para este periodo?", "turn_id": "app-turn-current"}],
            context={"tab": "reading", "period": "2026Q2", "entity": "AEROMEXICO"},
            tool_specs=_specs(),
            call_tool=lambda *_: {},
            emit=lambda *_: None,
            persist_session=saved.append,
            cancel_event=threading.Event(),
        )

    assert fake.retrieve_calls == 1
    assert fake.created == []
    assert fake.events.created == []
    assert fake.deleted == []
    assert saved == []


def test_reused_session_identity_mismatch_fails_closed_without_input():
    fake = FakeSessions(retrieved_session_id="sess_other")
    provider = _provider(FakeClient(fake))

    with pytest.raises(OpenAIProviderError, match="identidad de la sesión"):
        _run(provider, session_id="sess_fixture")

    assert fake.retrieve_calls == 1
    assert fake.created == []
    assert fake.events.created == []
    assert fake.deleted == []


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
    assert fake.created == []
    assert fake.retrieve_calls == 1
    assert fake.events.created[0]["idempotency_key"] == "airline-tracker-turn-app-turn-1"
    envelope = json.loads(fake.events.created[0]["events"][0]["input"][0]["content"][0]["text"])
    assert envelope["dashboard_context"] == new_context
    assert "conversation_history" not in envelope
    assert result.content == "Respuesta al periodo actual."
    assert result.provider_session_id == "sess_fixture"
    assert saved == ["sess_fixture"]
    assert event_stream.closed
