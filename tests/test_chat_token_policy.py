from __future__ import annotations

from pathlib import Path

import pytest

from src.conversational_analytics.config import ChatConfig
from src.conversational_analytics.service import ChatService
from src.conversational_analytics.storage import AdmissionDenied, ChatStore


class Snapshot:
    version = "snapshot-v1"
    semantic_version = "semantic-v1"

    def catalog(self):
        return {"metrics": {}}


class FakeOpenAIProvider:
    """Identifies the paid-provider policy without making external calls."""


def _service(tmp_path: Path, **overrides) -> tuple[ChatService, ChatStore]:
    store = ChatStore(tmp_path / "chat.sqlite3")
    overrides.setdefault("daily_cost_budget_user_usd", 100)
    overrides.setdefault("daily_cost_budget_global_usd", 100)
    config = ChatConfig(
        state_path=tmp_path / "chat.sqlite3",
        provider="openai",
        **overrides,
    )
    return ChatService(store, config, Snapshot(), provider=FakeOpenAIProvider()), store


def _submit(service: ChatService, owner: str, conversation_id: str, message_id: str) -> dict:
    return service.submit(owner, conversation_id, "ask", message_id, {})


def test_pilot_defaults_set_owner_and_global_daily_tokens_and_reservation_floor():
    config = ChatConfig()
    assert config.daily_token_budget_user == 200_000
    assert config.daily_token_budget_global == 200_000
    assert config.minimum_turn_reservation_tokens == 150_000


def test_paid_turn_reserves_at_least_floor_and_keeps_price_based_cost_reservation(tmp_path: Path):
    service, store = _service(tmp_path)
    conversation = service.create_conversation("owner")

    submitted = _submit(service, "owner", conversation["id"], "paid-floor")
    turn = store.get_turn("owner", submitted["turn_id"])

    assert turn["reserved_tokens"] == 150_000
    assert turn["reserved_cost_usd"] == pytest.approx(2.25)


def test_paid_turn_keeps_dynamic_reservation_when_it_exceeds_floor(tmp_path: Path):
    service, store = _service(
        tmp_path,
        max_tool_result_bytes=400_000,
        daily_token_budget_user=2_000_000,
        daily_token_budget_global=2_000_000,
        daily_cost_budget_user_usd=100,
        daily_cost_budget_global_usd=100,
    )
    conversation = service.create_conversation("owner")

    submitted = _submit(service, "owner", conversation["id"], "large-dynamic-window")

    assert store.get_turn("owner", submitted["turn_id"])["reserved_tokens"] > 150_000


def test_confirmed_usage_plus_pending_hold_rejects_next_paid_floor_over_daily_limit(tmp_path: Path):
    service, store = _service(tmp_path, max_active_per_user=3, max_concurrent_global=3)
    first = service.create_conversation("owner")
    known, _ = store.submit_turn(
        "owner", first["id"], "first", "known", {}, reserved_tokens=60_000, reserved_cost_usd=0.1
    )
    store.claim_turn()
    store.complete_turn(known["id"], "done", {}, 50_000, 10_000, 0.1, usage_complete=True)

    pending_conversation = service.create_conversation("owner")
    held, _ = store.submit_turn(
        "owner",
        pending_conversation["id"],
        "held",
        "held",
        {},
        reserved_tokens=60_000,
        reserved_cost_usd=0.1,
        user_token_budget=200_000,
        global_token_budget=200_000,
        max_active_per_user=3,
        max_active_global=3,
    )

    next_conversation = service.create_conversation("owner")
    with pytest.raises(AdmissionDenied, match="daily token budget"):
        _submit(service, "owner", next_conversation["id"], "would-exceed-200k")

    assert store.get_turn("owner", held["id"])["reserved_tokens"] == 60_000


def test_reservation_floor_environment_setting_requires_positive_integer(monkeypatch):
    monkeypatch.setenv("CHAT_MINIMUM_TURN_RESERVATION_TOKENS", "123456")
    assert ChatConfig.from_env().minimum_turn_reservation_tokens == 123_456

    for invalid in ("0", "-1", "1.5", "not-an-int"):
        monkeypatch.setenv("CHAT_MINIMUM_TURN_RESERVATION_TOKENS", invalid)
        with pytest.raises(ValueError):
            ChatConfig.from_env()
