from pathlib import Path

import pytest

from src.conversational_analytics.evaluation_live import _live_provider_run


@pytest.mark.parametrize(
    (
        "runtime_model",
        "candidate",
        "expected_effort",
        "expected_input_rate",
        "expected_output_rate",
        "expected_cost",
    ),
    [
        ("gpt-6-luna", "gpt-6.1-sol@low", "low", 2.0, 10.0, 0.0125),
        ("gpt-6.1-sol", "gpt-6-luna@medium", "medium", 0.1, 0.5, 0.000625),
    ],
)
def test_live_settlement_uses_candidate_catalog_rates_not_runtime_model(
    monkeypatch, tmp_path, mock_live_holdout_current_versions,
    runtime_model, candidate, expected_effort, expected_input_rate, expected_output_rate, expected_cost,
):
    from src.conversational_analytics.config import ChatConfig
    from src.conversational_analytics.providers.base import ProviderResult

    captured = {}

    class UsageProvider:
        def __init__(self, config):
            captured["config"] = config

        def run_turn(self, **kwargs):
            return ProviderResult(content="respuesta", input_tokens=1_000, output_tokens=1_000, usage_complete=True)

        def delete(self, _session_id):
            return None

    monkeypatch.setattr(
        "src.conversational_analytics.config.ChatConfig.from_env",
        classmethod(lambda cls: ChatConfig(provider="openai", model=runtime_model, openai_enabled=True)),
    )
    monkeypatch.setattr("src.conversational_analytics.providers.openai.OpenAIProvider", UsageProvider)
    report = _live_provider_run(
        cases=mock_live_holdout_current_versions["cases"],
        models=[candidate],
        budget_usd=10.0,
        snapshot_root=Path("site"),
        prices={candidate: (expected_input_rate, expected_output_rate)},
        probe_only=True,
        output_dir=tmp_path / f"settlement-{candidate}",
    )

    model = report["models"][0]
    case = model["cases"][0]
    assert captured["config"].estimated_input_cost_per_million == expected_input_rate
    assert captured["config"].estimated_output_cost_per_million == expected_output_rate
    assert captured["config"].model == candidate.split("@", 1)[0]
    assert captured["config"].reasoning_effort == expected_effort
    assert model["input_price_usd_per_million"] == expected_input_rate
    assert model["output_price_usd_per_million"] == expected_output_rate
    assert model["reasoning_effort"] == expected_effort
    assert model["pricing_as_of"] == "2026-10-09"
    assert case["estimated_cost_usd"] == pytest.approx(expected_cost)
    assert case["model_turn_completed"] is True


def test_multi_turn_provider_error_preserves_known_usage_from_prior_turns(
    monkeypatch, tmp_path, mock_live_holdout_current_versions
):
    from src.conversational_analytics.providers.base import ProviderResult
    from src.conversational_analytics.providers.openai import OpenAIProviderError

    class PartialConversationProvider:
        calls = 0

        def __init__(self, config):
            self.config = config

        def run_turn(self, **kwargs):
            type(self).calls += 1
            if type(self).calls == 1:
                return ProviderResult(
                    content="Primer turno.", input_tokens=123, output_tokens=45, usage_complete=True,
                )
            raise OpenAIProviderError("usage unavailable")

    monkeypatch.setattr("src.conversational_analytics.providers.openai.OpenAIProvider", PartialConversationProvider)
    case = dict(mock_live_holdout_current_versions["cases"][0], turns=["Primero", "Seguimiento"])
    report = _live_provider_run(
        cases=[case],
        models=["gpt-6-luna"],
        budget_usd=10.0,
        snapshot_root=Path("site"),
        prices={"gpt-6-luna": (0.1, 0.5)},
        probe_only=False,
        output_dir=tmp_path / "partial-usage",
    )

    record = report["models"][0]["cases"][0]
    assert PartialConversationProvider.calls == 2
    assert record["input_tokens"] == 123
    assert record["output_tokens"] == 45
    assert record["usage_complete"] is False
    assert report["models"][0]["spent_unknown"] is True
    assert report["models"][0]["known_estimated_cost_usd"] > 0
