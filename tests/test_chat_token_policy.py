from __future__ import annotations

from pathlib import Path

import pytest

from src.conversational_analytics.api import create_app
from src.conversational_analytics.auth import hash_password
from src.conversational_analytics.config import ChatConfig
from src.conversational_analytics.providers import openai as openai_provider_module
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
    overrides.setdefault("estimated_input_cost_per_million", 0.1)
    overrides.setdefault("estimated_output_cost_per_million", 0.5)
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
    assert config.max_tool_calls == 8
    assert config.max_turn_seconds == 180
    # The MVP caps spend in dollars; token caps are only a runaway brake.
    assert config.daily_cost_budget_user_usd == 1.0
    assert config.daily_cost_budget_global_usd == 1.0
    assert config.daily_token_budget_user == 2_000_000
    assert config.daily_token_budget_global == 2_000_000
    assert config.minimum_turn_reservation_tokens == 150_000


def test_environment_defaults_match_shared_production_tool_and_turn_limits(monkeypatch):
    monkeypatch.setenv("CHAT_PROVIDER", "mock")
    monkeypatch.setenv("CHAT_AUTH_MODE", "local")
    monkeypatch.delenv("CHAT_PASSWORDS_JSON", raising=False)
    monkeypatch.delenv("CHAT_TRUSTED_PROXY", raising=False)
    monkeypatch.delenv("CHAT_MAX_TOOL_CALLS", raising=False)
    monkeypatch.delenv("CHAT_MAX_TURN_SECONDS", raising=False)

    config = ChatConfig.from_env()

    assert config.max_tool_calls == ChatConfig().max_tool_calls == 8
    assert config.max_turn_seconds == ChatConfig().max_turn_seconds == 180


def test_paid_turn_reservation_fits_default_cost_quotas_at_explicit_luna_prices(tmp_path: Path):
    service, store = _service(tmp_path)
    conversation = service.create_conversation("owner")

    submitted = _submit(service, "owner", conversation["id"], "paid-floor")
    turn = store.get_turn("owner", submitted["turn_id"])

    assert turn["reserved_tokens"] == 150_000
    # The whole floor is priced at the output rate (US$0.50/M): no output cap exists.
    assert turn["reserved_cost_usd"] == pytest.approx(0.075)


@pytest.mark.parametrize(
    ("user_budget", "global_budget", "expected_setting"),
    # Default prices (US$5/US$15 per million) reserve US$2.25 for one floor turn.
    [(2.0, 10.0, "CHAT_DAILY_COST_BUDGET_USER_USD"), (100.0, 2.0, "CHAT_DAILY_COST_BUDGET_GLOBAL_USD")],
)
def test_app_rejects_openai_reservation_cost_before_provider_creation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    user_budget: float,
    global_budget: float,
    expected_setting: str,
):
    monkeypatch.setattr(
        openai_provider_module,
        "OpenAIProvider",
        lambda _: pytest.fail("provider construction must follow cost-quota validation"),
    )
    config = ChatConfig(
        state_path=tmp_path / "chat.sqlite3",
        provider="openai",
        model="test-model",
        openai_enabled=True,
        auth_mode="password",
        password_users={"owner": hash_password("runtime-only-strong-password")},
        allowed_origins=("https://dashboard.example",),
        daily_cost_budget_user_usd=user_budget,
        daily_cost_budget_global_usd=global_budget,
    )

    with pytest.raises(ValueError, match=expected_setting):
        create_app(config, snapshot=Snapshot(), start_worker=False)
    assert not config.state_path.exists()


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
    # Exercises the token-cap mechanics with an explicit cap (defaults are dollar-led).
    service, store = _service(
        tmp_path,
        max_active_per_user=3,
        max_concurrent_global=3,
        daily_token_budget_user=200_000,
        daily_token_budget_global=200_000,
    )
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


@pytest.mark.parametrize(
    ("input_price", "output_price", "reservation_usd", "admissible_at_one_dollar"),
    [
        # Luna: US$0.075 hold; at ~US$0.004 per measured question US$1 admits ~215 a day.
        (0.10, 0.50, 0.075, True),
        # Sol 6.1 and Astra: one floor hold exceeds US$1, so startup is refused.
        (2.0, 10.0, 1.5, False),
        (10.0, 50.0, 7.5, False),
    ],
)
def test_dollar_cap_reservation_prices_every_token_at_the_output_rate(
    input_price, output_price, reservation_usd, admissible_at_one_dollar
):
    config = ChatConfig(
        provider="openai",
        estimated_input_cost_per_million=input_price,
        estimated_output_cost_per_million=output_price,
    )
    assert config.reservation_cost_usd(150_000) == pytest.approx(reservation_usd)
    if admissible_at_one_dollar:
        config.validate_admission_budgets()
    else:
        with pytest.raises(ValueError, match="CHAT_DAILY_COST_BUDGET_USER_USD"):
            config.validate_admission_budgets()


def test_mock_reservations_hold_tokens_but_never_dollars(tmp_path: Path):
    store = ChatStore(tmp_path / "chat.sqlite3")
    # Placeholder prices would price a mock hold above US$1 if it counted.
    config = ChatConfig(state_path=tmp_path / "chat.sqlite3", provider="mock")
    service = ChatService(store, config, Snapshot())
    conversation = service.create_conversation("owner")

    turn = store.get_turn("owner", _submit(service, "owner", conversation["id"], "mock-free")["turn_id"])

    assert turn["reserved_tokens"] > 0
    assert turn["reserved_cost_usd"] == 0.0
