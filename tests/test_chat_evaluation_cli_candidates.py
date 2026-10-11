from __future__ import annotations

import json

import pytest

from src.conversational_analytics import evaluation, evaluation_live


def test_public_live_cli_runs_four_named_candidates_without_network(
    monkeypatch, tmp_path, capsys, mock_live_holdout_current_versions
) -> None:
    from src.conversational_analytics.providers import openai as openai_module
    from src.conversational_analytics.providers.base import ProviderResult

    fixture = mock_live_holdout_current_versions
    single_case_fixture = {**fixture, "cases": fixture["cases"][:1]}
    monkeypatch.setattr(evaluation, "load_fixture", lambda: single_case_fixture)
    monkeypatch.setattr(evaluation_live, "load_fixture", lambda: single_case_fixture)
    monkeypatch.setenv("CHAT_REASONING_EFFORT", "medium")
    monkeypatch.setenv("CHAT_TEXT_VERBOSITY", "medium")
    seen_configs = []

    class OfflineProvider:
        def __init__(self, config):
            seen_configs.append(config)

        def run_turn(self, **_kwargs):
            return ProviderResult(
                content="offline fake response", input_tokens=10, output_tokens=2, usage_complete=True
            )

    monkeypatch.setattr(openai_module, "OpenAIProvider", OfflineProvider)
    candidates = ["Luna-M", "Luna-X", "Sol-B", "Sol-M"]
    args = ["--run", "--opt-in", "--budget-usd", "1", "--models", *candidates, "--snapshot", "site"]
    for candidate in candidates:
        args.extend(["--model-price", f"{candidate}=0.000001:0.000001"])
    output_dir = tmp_path / "public-cli-four-candidates"
    args.extend(["--output-dir", str(output_dir)])

    assert evaluation.main(args) == 0
    report = json.loads(capsys.readouterr().out)
    assert [config.model for config in seen_configs] == [
        "gpt-6-luna",
        "gpt-6-luna",
        "gpt-6.1-sol",
        "gpt-6.1-sol",
    ]
    assert [(config.reasoning_effort, config.text_verbosity) for config in seen_configs] == [
        ("medium", "medium"),
        ("max", "medium"),
        ("low", "medium"),
        ("medium", "medium"),
    ]
    assert report["candidate_ids"] == candidates
    assert len(report["models"]) == 4
    assert all(len(model["cases"]) == 1 for model in report["models"])


def test_public_live_cli_accepts_full_candidate_settings_and_price_keys(
    monkeypatch, tmp_path, capsys, mock_live_holdout_current_versions
) -> None:
    from src.conversational_analytics.providers import openai as openai_module
    from src.conversational_analytics.providers.base import ProviderResult

    fixture = mock_live_holdout_current_versions
    single_case_fixture = {**fixture, "cases": fixture["cases"][:1]}
    monkeypatch.setattr(evaluation, "load_fixture", lambda: single_case_fixture)
    monkeypatch.setattr(evaluation_live, "load_fixture", lambda: single_case_fixture)
    seen_configs = []

    class OfflineProvider:
        def __init__(self, config):
            seen_configs.append(config)

        def run_turn(self, **_kwargs):
            return ProviderResult(
                content="offline fake response", input_tokens=10, output_tokens=2, usage_complete=True
            )

    monkeypatch.setattr(openai_module, "OpenAIProvider", OfflineProvider)
    candidates = ["gpt-6-luna@high@low", "gpt-6.1-sol@high@low"]
    args = ["--run", "--opt-in", "--budget-usd", "1", "--models", *candidates, "--snapshot", "site"]
    for candidate in candidates:
        args.extend(["--model-price", f"{candidate}=0.000001:0.000001"])
    output_dir = tmp_path / "public-cli-full-settings"
    args.extend(["--output-dir", str(output_dir)])

    assert evaluation.main(args) == 0
    report = json.loads(capsys.readouterr().out)
    assert [(config.model, config.reasoning_effort, config.text_verbosity) for config in seen_configs] == [
        ("gpt-6-luna", "high", "low"),
        ("gpt-6.1-sol", "high", "low"),
    ]
    assert [item["candidate_id"] for item in report["candidate_configs"]] == candidates


def test_public_live_cli_invalid_candidate_fails_before_provider_or_output(
    monkeypatch, tmp_path, mock_live_holdout_current_versions
) -> None:
    from src.conversational_analytics.providers import openai as openai_module

    fixture = mock_live_holdout_current_versions
    single_case_fixture = {**fixture, "cases": fixture["cases"][:1]}
    monkeypatch.setattr(evaluation, "load_fixture", lambda: single_case_fixture)
    monkeypatch.setattr(evaluation_live, "load_fixture", lambda: single_case_fixture)

    class UnexpectedProvider:
        def __init__(self, _config):
            pytest.fail("provider must not be constructed for an invalid candidate")

    monkeypatch.setattr(openai_module, "OpenAIProvider", UnexpectedProvider)
    candidate = "gpt-6-luna@unsupported@medium"
    output_dir = tmp_path / "public-cli-invalid-candidate"
    with pytest.raises(ValueError, match="no permitido"):
        evaluation.main(
            [
                "--run",
                "--opt-in",
                "--budget-usd",
                "1",
                "--probe-only",
                "--models",
                candidate,
                "--model-price",
                f"{candidate}=0.000001:0.000001",
                "--output-dir",
                str(output_dir),
            ]
        )
    assert not output_dir.exists()
