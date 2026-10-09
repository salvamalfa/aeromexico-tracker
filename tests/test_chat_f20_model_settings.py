from __future__ import annotations

import sqlite3

import pytest

from src.conversational_analytics.config import ChatConfig, model_catalog
from src.conversational_analytics.service import ChatService
from src.conversational_analytics.storage import ChatStore, Conflict
from src.conversational_analytics.worker import TurnWorker


class Snapshot:
    version = "snapshot-v1"
    semantic_version = "semantic-v1"

    def catalog(self):
        return {"metrics": {}}


def _clear_chat_env(monkeypatch):
    for name in list(__import__("os").environ):
        if name.startswith("CHAT_"):
            monkeypatch.delenv(name)


def test_model_catalog_defaults_validate_settings_and_prices(monkeypatch):
    _clear_chat_env(monkeypatch)
    monkeypatch.setenv("CHAT_PROVIDER", "openai")
    monkeypatch.setenv("CHAT_OPENAI_ENABLED", "true")
    monkeypatch.setenv("CHAT_ALLOW_LOCAL_OPENAI", "true")
    monkeypatch.setenv("CHAT_MODEL", "gpt-6-luna")

    config = ChatConfig.from_env()

    assert (config.reasoning_effort, config.text_verbosity) == ("medium", "medium")
    assert (config.estimated_input_cost_per_million, config.estimated_output_cost_per_million) == (
        0.10,
        0.50,
    )
    assert config.reservation_cost_usd(150_000) == pytest.approx(0.1125)
    assert model_catalog()["gpt-6-luna"]["cached_input_usd_per_million"] == 0.01
    assert model_catalog()["gpt-6-luna"]["cache_write_usd_per_million"] == 0.125
    assert model_catalog()["gpt-6.1-sol"]["cached_input_usd_per_million"] == 0.10
    assert model_catalog()["gpt-6.1-sol"]["cache_write_usd_per_million"] == 2.50


@pytest.mark.parametrize(
    ("model", "effort", "verbosity", "message"),
    [
        ("gpt-6.1-sol", "none", "medium", "CHAT_REASONING_EFFORT"),
        ("gpt-6-luna", "minimal", "medium", "CHAT_REASONING_EFFORT"),
        ("gpt-6-luna", "medium", "verbose", "CHAT_TEXT_VERBOSITY"),
        ("unlisted-model", "medium", "medium", "models.json"),
    ],
)
def test_model_catalog_rejects_unknown_combinations(monkeypatch, model, effort, verbosity, message):
    _clear_chat_env(monkeypatch)
    monkeypatch.setenv("CHAT_PROVIDER", "openai")
    monkeypatch.setenv("CHAT_OPENAI_ENABLED", "true")
    monkeypatch.setenv("CHAT_ALLOW_LOCAL_OPENAI", "true")
    monkeypatch.setenv("CHAT_MODEL", model)
    monkeypatch.setenv("CHAT_REASONING_EFFORT", effort)
    monkeypatch.setenv("CHAT_TEXT_VERBOSITY", verbosity)

    with pytest.raises(ValueError, match=message):
        ChatConfig.from_env()


def test_model_specific_price_override_must_match_catalog(monkeypatch):
    _clear_chat_env(monkeypatch)
    monkeypatch.setenv("CHAT_PROVIDER", "openai")
    monkeypatch.setenv("CHAT_OPENAI_ENABLED", "true")
    monkeypatch.setenv("CHAT_ALLOW_LOCAL_OPENAI", "true")
    monkeypatch.setenv("CHAT_MODEL", "gpt-6.1-sol")
    monkeypatch.setenv("CHAT_INPUT_COST_PER_MILLION", "0.10")

    with pytest.raises(ValueError, match="must match the versioned price"):
        ChatConfig.from_env()


def test_confirmed_usage_pricing_applies_long_context_and_cache_write_premiums():
    luna = ChatConfig(
        provider="openai",
        model="gpt-6-luna",
        estimated_input_cost_per_million=0.10,
        estimated_output_cost_per_million=0.50,
    )

    assert luna.usage_cost_usd(272_000, 1_000) == pytest.approx(0.0345)
    assert luna.usage_cost_usd(272_001, 1_000) == pytest.approx(0.06875025)


def test_conversation_and_each_turn_pin_settings_and_expose_them(tmp_path):
    store = ChatStore(tmp_path / "chat.sqlite3")
    config = ChatConfig(
        state_path=tmp_path / "chat.sqlite3",
        provider="openai",
        model="gpt-6-luna",
        reasoning_effort="max",
        text_verbosity="low",
        openai_enabled=True,
        estimated_input_cost_per_million=0.10,
        estimated_output_cost_per_million=0.50,
        daily_cost_budget_user_usd=5,
        daily_cost_budget_global_usd=5,
    )
    service = ChatService(store, config, Snapshot())
    conversation = service.create_conversation("owner")
    submitted = service.submit("owner", conversation["id"], "ask", "message-1", {})

    record = store.get_turn("owner", submitted["turn_id"])
    visible = store.get_conversation("owner", conversation["id"])
    assert (record["model"], record["reasoning_effort"], record["text_verbosity"]) == (
        "gpt-6-luna",
        "max",
        "low",
    )
    assert visible["turns"][0]["reasoning_effort"] == "max"
    assert visible["provider"] == "openai"
    assert service.health()["minimum_reservation_turns_per_day"] == 13


def test_legacy_conversation_cannot_send_with_new_settings_and_dedup_stays_idempotent(tmp_path):
    store = ChatStore(tmp_path / "chat.sqlite3")
    legacy = store.create_conversation("owner", "snapshot-v1", "semantic-v1")
    config = ChatConfig(
        state_path=tmp_path / "chat.sqlite3",
        provider="openai",
        model="gpt-6.1-sol",
        reasoning_effort="low",
        text_verbosity="medium",
        openai_enabled=True,
        estimated_input_cost_per_million=2,
        estimated_output_cost_per_million=10,
        daily_cost_budget_user_usd=5,
        daily_cost_budget_global_usd=5,
    )
    service = ChatService(store, config, Snapshot())

    with pytest.raises(Conflict, match="model_configuration_changed"):
        service.submit("owner", legacy["id"], "ask", "fresh-id", {})
    assert store.get_conversation("owner", legacy["id"])["turns"] == []

    current = service.create_conversation("owner")
    original = service.submit("owner", current["id"], "ask", "same-id", {})
    config2 = ChatConfig(
        **{
            **config.__dict__,
            "reasoning_effort": "medium",
        }
    )
    service2 = ChatService(store, config2, Snapshot())
    repeated = service2.submit("owner", current["id"], "ask", "same-id", {})
    assert repeated["turn_id"] == original["turn_id"]
    assert store.get_conversation("owner", current["id"])["turns"][0]["reasoning_effort"] == "low"


def test_upgrade_adds_nullable_settings_to_existing_database(tmp_path):
    path = tmp_path / "legacy.sqlite3"
    with sqlite3.connect(path) as db:
        db.executescript(
            "CREATE TABLE conversations (id TEXT PRIMARY KEY, owner_id TEXT NOT NULL, "
            "snapshot_version TEXT NOT NULL, semantic_version TEXT NOT NULL DEFAULT '', "
            "provider_session_id TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL);"
        )

    ChatStore(path)

    with sqlite3.connect(path) as db:
        columns = {row[1] for row in db.execute("PRAGMA table_info(conversations)")}
    assert {"model", "reasoning_effort", "text_verbosity", "provider"} <= columns


def test_provider_change_requires_new_conversation_to_avoid_stale_remote_session(tmp_path):
    store = ChatStore(tmp_path / "chat.sqlite3")
    openai_config = ChatConfig(
        provider="openai",
        model="gpt-6-luna",
        reasoning_effort="medium",
        text_verbosity="medium",
        estimated_input_cost_per_million=0.10,
        estimated_output_cost_per_million=0.50,
    )
    conversation = ChatService(store, openai_config, Snapshot()).create_conversation("owner")
    mock_config = ChatConfig(provider="mock")
    mock_service = ChatService(store, mock_config, Snapshot())

    with pytest.raises(Conflict, match="provider_changed"):
        mock_service.submit("owner", conversation["id"], "mock message", "mock-1", {})

    mock_conversation = mock_service.create_conversation("owner")
    resumed = ChatService(store, openai_config, Snapshot())
    with pytest.raises(Conflict, match="provider_changed"):
        resumed.submit("owner", mock_conversation["id"], "resume remote", "resume-1", {})
    assert store.get_conversation("owner", conversation["id"])["turns"] == []
    assert store.get_conversation("owner", mock_conversation["id"])["turns"] == []


def test_legacy_remote_session_is_inferred_as_openai_for_mock_rejection(tmp_path):
    store = ChatStore(tmp_path / "chat.sqlite3")
    legacy = store.create_conversation("owner", "snapshot-v1", "semantic-v1")
    with store._connect() as db:
        db.execute(
            "UPDATE conversations SET provider_session_id='sess_existing' WHERE id=?", (legacy["id"],)
        )

    with pytest.raises(Conflict, match="provider_changed"):
        ChatService(store, ChatConfig(provider="mock"), Snapshot()).submit(
            "owner", legacy["id"], "ask", "legacy-mock", {}
        )


def test_queued_turn_rejects_changed_runtime_settings_and_releases_known_zero(tmp_path):
    path = tmp_path / "chat.sqlite3"
    store = ChatStore(path)
    old_config = ChatConfig(
        state_path=path,
        provider="openai",
        model="gpt-6-luna",
        reasoning_effort="medium",
        text_verbosity="medium",
        estimated_input_cost_per_million=0.10,
        estimated_output_cost_per_million=0.50,
        daily_cost_budget_user_usd=5,
        daily_cost_budget_global_usd=5,
    )
    old_service = ChatService(store, old_config, Snapshot())
    conversation = old_service.create_conversation("owner")
    submitted = old_service.submit("owner", conversation["id"], "ask", "queued", {})
    current_config = ChatConfig(**{**old_config.__dict__, "reasoning_effort": "max"})

    class NoCallProvider:
        def run_turn(self, **_kwargs):
            pytest.fail("a turn pinned to old settings must not reach the provider")

    worker = TurnWorker(store, current_config, NoCallProvider(), Snapshot())
    worker._execute_turn(store.claim_turn())
    record = store.get_turn("owner", submitted["turn_id"])

    assert (record["status"], record["usage_complete"]) == ("failed", 1)
    assert (record["estimated_input_tokens"], record["estimated_output_tokens"]) == (0, 0)
    assert record["reserved_tokens"] == 0
    assert record["reserved_cost_usd"] == 0
