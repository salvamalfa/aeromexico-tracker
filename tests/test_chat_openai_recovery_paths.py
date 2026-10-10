"""Recovery paths that accept a completed provider turn after a broken stream."""

from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path

import pytest
from test_chat_openai import (
    FakeClient,
    FakeSessions,
    FakeStream,
    _provider,
    _run,
    _session_created,
    _specs,
    _text_delta,
    _turn,
    _turn_created,
    _usage,
)
from test_chat_worker import Registry, Snapshot

from src.conversational_analytics.config import ChatConfig
from src.conversational_analytics.evaluation_live_support import _error_metadata
from src.conversational_analytics.providers.base import ProviderResult
from src.conversational_analytics.providers.openai import OpenAIProviderError
from src.conversational_analytics.storage import ChatStore
from src.conversational_analytics.worker import TurnWorker

FINAL_ITEM = {
    "id": "item_final",
    "turn_id": "turn_provider",
    "type": "message",
    "role": "assistant",
    "phase": "final_answer",
    "status": "completed",
    "content": [{"type": "output_text", "text": "La ocupación fue de 87.1%."}],
}


def _recovery(turn, items):
    return {"id": "sess_fixture", "status": "idle", "required_actions": [], "turns": [turn], "items": items}


def test_truncated_stream_is_not_promoted_when_recovery_finds_no_final_text():
    completed = _turn("turn_provider", status="completed", usage=_usage(500, 300))
    fake = FakeSessions(
        create_stream=FakeStream(
            [_session_created(), _turn_created(), _text_delta(delta="La ocupación fue de 8")]
        ),
        recovery=_recovery(completed, []),
        prior_turns=[completed],
    )

    with pytest.raises(OpenAIProviderError, match="sin texto") as raised:
        _run(_provider(FakeClient(fake)))

    # The partial delta never becomes the answer, and the known usage is kept.
    assert raised.value.usage == (500, 300)
    assert (raised.value.reason_code, raised.value.session_id, raised.value.turn_id) == (
        "provider_terminal_failed",
        "sess_fixture",
        "turn_provider",
    )


def test_stream_eof_keeps_exact_session_turn_identity_for_usage_reconciliation():
    fake = FakeSessions(create_stream=FakeStream([_session_created(), _turn_created()]))

    with pytest.raises(OpenAIProviderError, match="cerró sin resultado terminal") as raised:
        _run(_provider(FakeClient(fake)))

    assert (raised.value.reason_code, raised.value.session_id, raised.value.turn_id) == (
        "provider_terminal_failed",
        "sess_fixture",
        "turn_provider",
    )


def test_api_500_error_metadata_is_allowlisted_and_keeps_exact_turn_context():
    class InternalServerError(Exception):
        status_code = 500
        code = "server_error"
        body = {"error": {"code": "server_error", "message": "secret-response-body"}}

    fake = FakeSessions(
        create_stream=FakeStream([_session_created(), _turn_created(), InternalServerError("secret-message")])
    )

    with pytest.raises(OpenAIProviderError) as raised:
        _run(_provider(FakeClient(fake)))

    error = raised.value
    metadata = _error_metadata(error)
    assert (error.reason_code, error.session_id, error.turn_id) == (
        "provider_terminal_failed",
        "sess_fixture",
        "turn_provider",
    )
    assert metadata == {
        "exception_types": ["OpenAIProviderError", "InternalServerError"],
        "http_status": 500,
        "reason_code": "provider_terminal_failed",
        "provider_turn_id": "turn_provider",
        "upstream_exception_type": "InternalServerError",
        "upstream_http_status": 500,
        "upstream_error_code": "server_error",
    }
    assert "secret" not in json.dumps(metadata)


def test_dropped_connection_recovery_reads_missing_usage():
    without_usage = _turn("turn_provider", status="completed", usage=None)
    with_usage = _turn("turn_provider", status="completed", usage=_usage(500, 300))
    fake = FakeSessions(
        create_stream=FakeStream(
            [_session_created(), _turn_created(), _text_delta(delta="La"), ConnectionResetError("drop")]
        ),
        recovery=_recovery(without_usage, [FINAL_ITEM]),
        prior_turns=[without_usage],
        retrieved_turn=with_usage,
    )

    result, _, _ = _run(_provider(FakeClient(fake)))

    assert result.content == "La ocupación fue de 87.1%."
    assert (result.input_tokens, result.output_tokens, result.usage_complete) == (500, 300, True)
    assert fake.turn_retrieve_calls


def test_provider_error_recovery_signals_completion_before_polling_usage():
    without_usage = _turn("turn_provider", status="completed", usage=None)
    with_usage = _turn("turn_provider", status="completed", usage=_usage(500, 300))
    order: list = []

    class Sessions(FakeSessions):
        def _retrieve_turn(self, turn_id, *, session_id, timeout):
            order.append("usage_poll")
            return super()._retrieve_turn(turn_id, session_id=session_id, timeout=timeout)

    fake = Sessions(
        create_stream=FakeStream(
            [_session_created(), _turn_created(), OpenAIProviderError("stream interrupted")]
        ),
        recovery=_recovery(without_usage, [FINAL_ITEM]),
        prior_turns=[without_usage],
        retrieved_turn=with_usage,
    )

    result = _provider(FakeClient(fake)).run_turn(
        session_id=None,
        messages=[{"role": "user", "content": "¿Ocupación?", "turn_id": "app-turn-1"}],
        context={"tab": "executive", "period": "2026Q1", "entity": "AEROMEXICO"},
        tool_specs=_specs(),
        call_tool=lambda *_: {},
        emit=lambda *_: None,
        persist_session=lambda _: None,
        cancel_event=threading.Event(),
        mark_terminal_completed=lambda usage=None: order.append("mark_completed"),
    )

    assert order[0] == "mark_completed" and "usage_poll" in order
    assert (result.input_tokens, result.output_tokens, result.usage_complete) == (500, 300, True)


class MetadataProvider:
    def run_turn(self, **kwargs):
        kwargs["emit"]("provider.metadata", {"provider_turn_id": None, "provider_event_type": "x"})
        return ProviderResult("84.9", input_tokens=4, output_tokens=2, usage_complete=True)

    def cancel(self, session_id):
        pass

    def delete(self, session_id):
        pass


def test_missing_provider_turn_id_is_not_stored_as_the_string_none(tmp_path: Path):
    path = tmp_path / "chat.sqlite3"
    store = ChatStore(path)
    conv = store.create_conversation("alice", "snapshot-v1", "semantic-v1")
    turn, _ = store.submit_turn(
        "alice", conv["id"], "ask", "client-1", {}, reserved_tokens=100, reserved_cost_usd=0.01
    )
    worker = TurnWorker(store, ChatConfig(state_path=path), MetadataProvider(), Snapshot())
    worker._registry = Registry()
    worker._execute_turn(store.claim_turn())

    with sqlite3.connect(path) as db:
        (stored,) = db.execute("SELECT provider_turn_id FROM turns WHERE id=?", (turn["id"],)).fetchone()
    assert stored is None


class LimitProvider:
    """Stops a turn on a local limit, as OpenAIProvider does at the 9th tool call."""

    def __init__(self, sessions):
        self.client = FakeClient(sessions)
        self.cancelled: list[str] = []

    def run_turn(self, **kwargs):
        raise OpenAIProviderError(
            "El turno alcanzó el máximo de llamadas de herramientas",
            reason_code="tool_call_limit",
            session_id="sess_fixture",
            turn_id="turn_provider",
        )

    def cancel(self, session_id):
        self.cancelled.append(session_id)

    def delete(self, session_id):
        pass


def _run_limited_turn(tmp_path: Path, retrieved_turn):
    path = tmp_path / "chat.sqlite3"
    store = ChatStore(path)
    conv = store.create_conversation("alice", "snapshot-v1", "semantic-v1", "gpt-6.1-sol", "medium", "medium")
    turn, _ = store.submit_turn(
        "alice",
        conv["id"],
        "ask",
        "client-1",
        {},
        reserved_tokens=100,
        reserved_cost_usd=0.01,
        model="gpt-6.1-sol",
        reasoning_effort="medium",
        text_verbosity="medium",
    )
    config = ChatConfig(
        state_path=path,
        provider="openai",
        model="gpt-6.1-sol",
        reasoning_effort="medium",
        text_verbosity="medium",
        estimated_input_cost_per_million=2.0,
        estimated_output_cost_per_million=10.0,
    )
    provider = LimitProvider(FakeSessions(retrieved_turn=retrieved_turn))
    worker = TurnWorker(store, config, provider, Snapshot())
    worker._registry = Registry()
    worker._execute_turn(store.claim_turn())
    with sqlite3.connect(path) as db:
        row = db.execute(
            "SELECT status,usage_complete,reserved_cost_usd,estimated_cost_usd FROM turns WHERE id=?",
            (turn["id"],),
        ).fetchone()
    return provider, row


def test_tool_limit_failure_cancels_the_provider_turn_and_books_its_usage(tmp_path: Path):
    cancelled = _turn("turn_provider", status="cancelled", usage=_usage(500, 300))

    provider, (status, usage_complete, reserved, cost) = _run_limited_turn(tmp_path, cancelled)

    assert provider.cancelled == ["sess_fixture"]
    assert (status, usage_complete, reserved) == ("failed", 1, 0)
    assert cost == pytest.approx((500 * 2.0 * 1.25 + 300 * 10.0) / 1_000_000)


def test_tool_limit_failure_keeps_the_hold_when_usage_stays_unknown(tmp_path: Path, monkeypatch):
    from src.conversational_analytics.providers import _openai_helpers

    monkeypatch.setattr(_openai_helpers, "POST_CANCEL_USAGE_ATTEMPTS", 1)
    still_running = _turn("turn_provider", status="in_progress", usage=None)

    provider, (status, usage_complete, reserved, _) = _run_limited_turn(tmp_path, still_running)

    assert provider.cancelled == ["sess_fixture"]
    # Unknown never becomes zero: the reservation stays held.
    assert (status, usage_complete, reserved) == ("failed", 0, 0.01)
