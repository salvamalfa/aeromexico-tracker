"""Offline tests for derived prompts and prompt-versioned provider sessions."""

import hashlib
import json

import pytest
from test_chat_openai import (
    FakeClient,
    FakeSessions,
    FakeStream,
    _completed,
    _provider,
    _run,
    _session_created,
    _text_done,
    _turn_created,
)

from src.conversational_analytics.providers._openai_helpers import SYSTEM_INSTRUCTIONS, OpenAIProviderError
from src.conversational_analytics.providers._openai_prompt import (
    PERIOD_SELECTION_POLICY,
    PERIOD_SELECTION_POLICY_VERSION,
    prompt_sha256,
    with_dashboard_period_policy,
)
from src.conversational_analytics.providers._openai_session_version import (
    INSTRUCTIONS_DERIVATION_KEY,
    INSTRUCTIONS_FINGERPRINT_KEY,
    PROMPT_INPUT_FINGERPRINT_KEY,
)


def test_f21_override_is_preserved_and_derived_prompt_gets_period_policy_and_distinct_hash():
    approved_prompt = "Prompt F2.1 aprobado con sus ejemplos originales."
    provider = _provider(FakeClient(FakeSessions()), system_instructions_override=approved_prompt)

    effective = provider._instructions()

    assert effective.startswith(approved_prompt)
    assert "(1) el periodo explícito de la" in effective
    assert "(2) el periodo anterior solo si" in effective
    assert "(3) el periodo seleccionado en el" in effective
    assert "pregunta cuál periodo necesita el usuario" in effective
    assert "esta gráfica" in effective
    assert "tarjeta activa" in effective
    assert "el contexto validado puede completar lo que omita la pregunta" in effective
    assert "no infieras la métrica, entidad" not in effective
    assert effective == with_dashboard_period_policy(effective)
    assert prompt_sha256(approved_prompt) != prompt_sha256(effective)
    assert PERIOD_SELECTION_POLICY_VERSION in SYSTEM_INSTRUCTIONS


def test_quoted_policy_before_later_instruction_is_appended_and_then_idempotent():
    source = f"{PERIOD_SELECTION_POLICY}\nINSTRUCCIÓN POSTERIOR"

    effective = with_dashboard_period_policy(source)

    assert effective.startswith(source)
    assert effective.endswith(PERIOD_SELECTION_POLICY)
    assert with_dashboard_period_policy(effective) == effective
    assert effective.count(PERIOD_SELECTION_POLICY) == 2
    assert prompt_sha256(with_dashboard_period_policy(effective)) == prompt_sha256(effective)


def test_terminal_policy_and_trailing_whitespace_keep_exact_text_and_hash():
    source = f"Prompt origen\n\n{PERIOD_SELECTION_POLICY}\n  "

    effective = with_dashboard_period_policy(source)

    assert effective == source
    assert prompt_sha256(effective) == prompt_sha256(source)


def test_new_session_records_hashes_of_effective_override_and_derivation():
    source = "Prompt aprobado de F2.1: estilo, criterios y ejemplos completos."
    runner_prompt = with_dashboard_period_policy(source)
    fake = FakeSessions(
        create_stream=FakeStream(
            [
                _session_created(),
                _turn_created(),
                _text_done(text="Respuesta."),
                _completed(),
            ]
        )
    )
    provider = _provider(FakeClient(fake), system_instructions_override=runner_prompt)
    assert provider._instructions() == runner_prompt

    _run(provider)

    metadata = fake.created[0]["metadata"]
    assert metadata[INSTRUCTIONS_FINGERPRINT_KEY] == prompt_sha256(runner_prompt)
    assert (
        metadata[INSTRUCTIONS_FINGERPRINT_KEY]
        == hashlib.sha256(provider._instructions().encode("utf-8")).hexdigest()
    )
    assert metadata[PROMPT_INPUT_FINGERPRINT_KEY] == prompt_sha256(runner_prompt)
    assert metadata[INSTRUCTIONS_DERIVATION_KEY] == PERIOD_SELECTION_POLICY_VERSION


def test_legacy_or_stale_session_rotates_with_history_then_queues_old_session_for_deletion():
    fake = FakeSessions(
        create_stream=FakeStream(
            [
                _session_created("sess_new"),
                _turn_created(session_id="sess_new"),
                _text_done(text="Respuesta actualizada.", session_id="sess_new"),
                _completed(session_id="sess_new"),
            ]
        ),
        session_metadata={},
    )
    provider = _provider(FakeClient(fake), system_instructions_override="F2.1 aprobado")
    messages = [
        {"role": "user", "content": "Pregunta anterior"},
        {"role": "assistant", "content": "Respuesta anterior"},
        {"role": "user", "content": "¿Y el actual?", "turn_id": "app-turn-current"},
    ]
    current_context = {"tab": "reading", "period": "2026Q2", "entity": "AEROMEXICO"}
    retired = []

    result, _, saved = _run(
        provider,
        session_id="sess_fixture",
        messages=messages,
        context=current_context,
        retire_session=retired.append,
    )

    envelope = json.loads(fake.created[0]["input"][0]["content"][0]["text"])
    assert envelope["dashboard_context"] == current_context
    assert envelope["conversation_history"] == messages[:-1]
    assert fake.events.created == []
    assert result.provider_session_id == "sess_new"
    assert saved == ["sess_new"]
    assert retired == ["sess_fixture"]


@pytest.mark.parametrize(
    ("retrieve_error", "retrieved_session_id", "message"),
    [
        (RuntimeError("provider detail"), None, "verificar la versión de instrucciones"),
        (None, "sess_other", "identidad de la sesión"),
    ],
)
def test_unverifiable_session_fails_closed_before_input(retrieve_error, retrieved_session_id, message):
    fake = FakeSessions(retrieve_error=retrieve_error, retrieved_session_id=retrieved_session_id)
    provider = _provider(FakeClient(fake))

    with pytest.raises(OpenAIProviderError, match=message):
        _run(provider, session_id="sess_fixture")

    assert fake.retrieve_calls == 1
    assert fake.created == []
    assert fake.events.created == []
    assert fake.deleted == []


def test_prompt_mismatch_without_retirement_queue_fails_closed_before_input():
    fake = FakeSessions(session_metadata={})
    provider = _provider(FakeClient(fake))

    with pytest.raises(OpenAIProviderError, match="encolar la sesión anterior"):
        _run(provider, session_id="sess_fixture")

    assert fake.created == []
    assert fake.events.created == []
