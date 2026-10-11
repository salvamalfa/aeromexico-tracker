from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from src.conversational_analytics.storage import ChatStore


def _failed_turn(path: Path, *, pin_settings: bool = True):
    store = ChatStore(path)
    settings = (
        {
            "model": "gpt-6-luna",
            "reasoning_effort": "high",
            "text_verbosity": "high",
            "provider": "openai",
        }
        if pin_settings
        else {}
    )
    conversation = store.create_conversation(
        "alice", "snapshot-v1", "semantic-v1", **settings
    )
    turn, _ = store.submit_turn(
        "alice", conversation["id"], "private question", "client-1", {}, **settings
    )
    assert store.claim_turn()
    store.set_provider_session(conversation["id"], "session-existing")
    store.set_provider_turn(turn["id"], "provider-turn-existing")
    store.fail_turn(turn["id"], "provider_error", "provider stream ended")
    return store, conversation, turn


def _apply_args(turn: dict, conversation: dict) -> list[str]:
    return [
        "--turn-id", turn["id"],
        "--owner-id", "alice",
        "--apply",
        "--conversation-id", conversation["id"],
        "--provider-session-id", "session-existing",
        "--provider-turn-id", "provider-turn-existing",
        "--snapshot-version", "snapshot-v1",
        "--semantic-version", "semantic-v1",
    ]


def _set_current_sol_environment(monkeypatch, state_path: Path) -> None:
    monkeypatch.setenv("CHAT_STATE_PATH", str(state_path))
    monkeypatch.setenv("CHAT_PROVIDER", "openai")
    monkeypatch.setenv("CHAT_OPENAI_ENABLED", "true")
    monkeypatch.setenv("CHAT_ALLOW_LOCAL_OPENAI", "true")
    monkeypatch.setenv("CHAT_AUTH_MODE", "local")
    monkeypatch.setenv("CHAT_MODEL", "gpt-6.1-sol")
    monkeypatch.setenv("CHAT_REASONING_EFFORT", "low")
    monkeypatch.setenv("CHAT_TEXT_VERBOSITY", "low")
    monkeypatch.delenv("CHAT_INPUT_COST_PER_MILLION", raising=False)
    monkeypatch.delenv("CHAT_OUTPUT_COST_PER_MILLION", raising=False)


def test_recovery_uses_turn_model_prices_and_keeps_usage_ledger_under_new_sol_env(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    import scripts.chat.reconcile_failed_turn as reconcile
    import src.conversational_analytics.providers.openai as openai_module

    store, conversation, turn = _failed_turn(tmp_path / "chat.sqlite3")
    _set_current_sol_environment(monkeypatch, store.path)
    provider_configs = []

    class FakeProvider:
        def __init__(self, config):
            provider_configs.append(config)
            self.client = SimpleNamespace(
                beta=SimpleNamespace(
                    agents=SimpleNamespace(
                        sessions=SimpleNamespace(
                            turns=SimpleNamespace(retrieve=lambda *args, **kwargs: None),
                            items=SimpleNamespace(list=lambda *args, **kwargs: None),
                        )
                    )
                )
            )

    monkeypatch.setattr(openai_module, "OpenAIProvider", FakeProvider)
    monkeypatch.setattr(
        reconcile,
        "_recover_exact",
        lambda provider, session_id, turn_id: ("Recovered answer", 1_000, 100, []),
    )

    assert reconcile.run(["--turn-id", turn["id"], "--owner-id", "alice"]) == 0
    dry_run = json.loads(capsys.readouterr().out)
    assert dry_run["eligible_by_local_metadata"] is True
    assert dry_run["model"] == "gpt-6-luna"
    assert dry_run["reasoning_effort"] == "high"
    assert dry_run["text_verbosity"] == "high"
    assert dry_run["pricing_model"] == "gpt-6-luna"
    assert dry_run["pricing_source"] == "config/chat/models.json"
    assert dry_run["pricing_as_of"] == "2026-10-09"
    assert dry_run["provider_calls"] == 0

    assert reconcile.run(_apply_args(turn, conversation)) == 0
    assert capsys.readouterr().out
    recovery_config = provider_configs[0]
    assert recovery_config.model == "gpt-6-luna"
    assert recovery_config.reasoning_effort == "high"
    assert recovery_config.text_verbosity == "high"
    assert recovery_config.estimated_input_cost_per_million == 0.1
    assert recovery_config.estimated_output_cost_per_million == 0.5

    expected_luna_cost = (1_000 * 0.1 * 1.25 + 100 * 0.5) / 1_000_000
    sol_environment_cost = (1_000 * 2.0 * 1.25 + 100 * 10.0) / 1_000_000
    assert expected_luna_cost == 0.000175
    assert sol_environment_cost == 0.0035
    recovered = store.get_turn("alice", turn["id"])
    usage = store.usage("alice")
    assert recovered["model"] == "gpt-6-luna"
    assert recovered["reasoning_effort"] == "high"
    assert recovered["text_verbosity"] == "high"
    assert recovered["estimated_cost_usd"] == expected_luna_cost
    assert usage["input_tokens"] == 1_000
    assert usage["output_tokens"] == 100
    assert usage["estimated_cost_usd"] == expected_luna_cost
    assert usage["turn_count"] == 1


def test_legacy_turn_without_model_settings_requires_explicit_reconciliation(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    import scripts.chat.reconcile_failed_turn as reconcile

    store, conversation, turn = _failed_turn(tmp_path / "legacy.sqlite3", pin_settings=False)
    monkeypatch.setenv("CHAT_STATE_PATH", str(store.path))

    assert reconcile.run(["--turn-id", turn["id"], "--owner-id", "alice"]) == 0
    plan = json.loads(capsys.readouterr().out)
    assert plan["eligible_by_local_metadata"] is False
    assert plan["model_settings_pinned"] is False
    assert plan["model_settings_reconciliation_required"] is True
    assert plan["pricing_model"] is None
    assert plan["provider_calls"] == 0

    assert reconcile.run(_apply_args(turn, conversation)) == 2
    assert "explicit model-settings reconciliation required" in capsys.readouterr().err
    assert store.get_turn("alice", turn["id"])["status"] == "failed"
    assert store.usage("alice")["turn_count"] == 0
