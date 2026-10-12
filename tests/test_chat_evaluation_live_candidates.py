from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.conversational_analytics.evaluation_live import _live_provider_run


def test_live_candidates_pin_and_report_all_provider_settings(
    monkeypatch, tmp_path, mock_live_holdout_current_versions
) -> None:
    from src.conversational_analytics.providers.base import ProviderResult

    seen_configs = []

    class OfflineProvider:
        def __init__(self, config):
            self.config = config
            seen_configs.append(config)

        def run_turn(self, **_kwargs):
            return ProviderResult(
                content="fixture response", input_tokens=10, output_tokens=2, usage_complete=True
            )

    monkeypatch.setattr("src.conversational_analytics.providers.openai.OpenAIProvider", OfflineProvider)
    cases = mock_live_holdout_current_versions["cases"]
    rates = {candidate: (0.000001, 0.000001) for candidate in ("Luna-M", "Luna-X", "Sol-B", "Sol-M")}
    output_dir = tmp_path / "four-candidates"
    report = _live_provider_run(
        cases=cases,
        models=["Luna-M", "Luna-X", "Sol-B", "Sol-M"],
        budget_usd=10.0,
        snapshot_root=Path("site"),
        prices=rates,
        probe_only=True,
        output_dir=output_dir,
    )

    expected = [
        ("Luna-M", "gpt-6-luna", "medium", "medium"),
        ("Luna-X", "gpt-6-luna", "max", "medium"),
        ("Sol-B", "gpt-6.1-sol", "low", "medium"),
        ("Sol-M", "gpt-6.1-sol", "medium", "medium"),
    ]
    actual = [(config.model, config.reasoning_effort, config.text_verbosity) for config in seen_configs]
    assert actual == [(model, effort, verbosity) for _, model, effort, verbosity in expected]
    assert report["candidate_ids"] == [candidate for candidate, *_ in expected]
    assert [
        (item["candidate_id"], item["model"], item["reasoning_effort"], item["text_verbosity"])
        for item in report["candidate_configs"]
    ] == expected
    assert [
        (item["candidate_id"], item["model"], item["reasoning_effort"], item["text_verbosity"])
        for item in report["models"]
    ] == expected
    for item in report["models"]:
        case = item["cases"][0]
        assert (case["candidate_id"], case["model"], case["reasoning_effort"], case["text_verbosity"]) == (
            item["candidate_id"],
            item["model"],
            item["reasoning_effort"],
            item["text_verbosity"],
        )
    progress = json.loads(next(output_dir.glob("*.progress.json")).read_text(encoding="utf-8"))
    assert [item["candidate_id"] for item in progress["models"]] == report["candidate_ids"]


def test_legacy_model_string_uses_env_defaults_and_keeps_old_price_key(
    monkeypatch, tmp_path, mock_live_holdout_current_versions
) -> None:
    from src.conversational_analytics.providers.base import ProviderResult

    seen = []

    class OfflineProvider:
        def __init__(self, config):
            seen.append(config)

        def run_turn(self, **_kwargs):
            return ProviderResult(
                content="fixture response", input_tokens=1, output_tokens=1, usage_complete=True
            )

    monkeypatch.setenv("CHAT_REASONING_EFFORT", "high")
    monkeypatch.setenv("CHAT_TEXT_VERBOSITY", "low")
    monkeypatch.setattr("src.conversational_analytics.providers.openai.OpenAIProvider", OfflineProvider)
    report = _live_provider_run(
        cases=mock_live_holdout_current_versions["cases"],
        models=["gpt-6-luna"],
        budget_usd=10.0,
        snapshot_root=Path("site"),
        prices={"gpt-6-luna": (0.000001, 0.000001)},
        probe_only=True,
        output_dir=tmp_path / "legacy-string",
    )

    assert len(seen) == 1
    assert (seen[0].model, seen[0].reasoning_effort, seen[0].text_verbosity) == ("gpt-6-luna", "high", "low")
    candidate = report["candidate_configs"][0]
    assert candidate == {
        "candidate_id": "gpt-6-luna@high@low",
        "model": "gpt-6-luna",
        "reasoning_effort": "high",
        "text_verbosity": "low",
    }
    assert report["models"][0]["cases"][0]["candidate_id"] == candidate["candidate_id"]


def test_invalid_candidate_settings_fail_before_provider_or_output(
    monkeypatch, tmp_path, mock_live_holdout_current_versions
) -> None:
    class UnexpectedProvider:
        def __init__(self, _config):
            pytest.fail("provider should not be constructed for invalid candidate settings")

    monkeypatch.setattr("src.conversational_analytics.providers.openai.OpenAIProvider", UnexpectedProvider)
    output_dir = tmp_path / "invalid-candidate"
    with pytest.raises(ValueError, match="no permitido"):
        _live_provider_run(
            cases=mock_live_holdout_current_versions["cases"],
            models=[
                {
                    "candidate_id": "bad-effort",
                    "model": "gpt-6-luna",
                    "reasoning_effort": "invented",
                    "text_verbosity": "medium",
                }
            ],
            budget_usd=10.0,
            snapshot_root=Path("site"),
            prices={"bad-effort": (0.1, 0.5)},
            probe_only=True,
            output_dir=output_dir,
        )
    assert not output_dir.exists()
