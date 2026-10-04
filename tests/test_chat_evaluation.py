from __future__ import annotations

import json
from pathlib import Path

import yaml

from src.conversational_analytics.evaluation import (
    FIXTURE_PATH,
    approximately_equal,
    load_cases,
    render_dry_run,
    verify_observation,
)


def test_holdout_is_independent_and_covers_required_risks() -> None:
    cases = load_cases()
    raw = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    assert len(cases) == 40
    assert len({case["id"] for case in cases}) == len(cases)
    questions = [case["question"].casefold() for case in cases]
    assert len(set(questions)) == len(questions)
    prompt_examples = yaml.safe_load(Path("config/chat/question_examples.yaml").read_text())
    example_questions = {item["question"].casefold() for item in prompt_examples["examples"]}
    assert not (set(questions) & example_questions)
    expected_text = " ".join(questions)
    assert "ruta" in expected_text and "privado" in expected_text
    assert "percentage" in expected_text or "porcentaje" in expected_text
    assert "percentage points" in expected_text or "puntos porcentuales" in expected_text
    assert {case["expected"]["status"] for case in cases} == {
        "supported",
        "clarify",
        "unsupported",
        "refused",
    }
    # Explicitly protect the fixture source from accidental leakage from the
    # semantic prompt examples used to guide a model.
    assert raw["dataset"] == "site/data/v1 snapshot"
    assert "question_examples.yaml" in raw["description"]


def test_numeric_comparison_does_not_coerce_missing_to_zero() -> None:
    assert approximately_equal(0.849, 0.8490000000001)
    assert not approximately_equal(0.0, 0.849)


def test_supported_observation_checks_plan_values_and_references() -> None:
    case = next(case for case in load_cases() if case["id"] == "es_am_lf_q2")
    plan = case["expected"]["plan"]
    row = {
        **case["expected"]["rows"][0],
        "availability": "available",
        "source_references": [{"label": "SEC", "url": "https://www.sec.gov/example"}],
    }
    result = verify_observation(
        case, {"status": "supported", "plan": plan, "rows": [row], "response": "84.9% en 2026Q2"}
    )
    assert result.passed, result.failures

    bad_row = {**row, "value": 0.0, "source_references": []}
    failed = verify_observation(
        case, {"status": "supported", "plan": plan, "rows": [bad_row], "response": "84.9% en 2026Q2"}
    )
    assert not failed.passed
    assert any("valor incorrecto" in failure for failure in failed.failures)
    assert any("sin referencias" in failure for failure in failed.failures)


def test_dry_run_never_calls_provider_and_exposes_estimates_and_destinations() -> None:
    result = render_dry_run(
        load_cases(), models=["candidate-a", "candidate-b"], prices={"candidate-a": (2.0, 8.0)}
    )
    assert result["provider_calls"] == 0
    assert result["question_count"] == 40
    assert result["candidate_runs"][0]["windows"] == 4
    assert result["candidate_runs"][0]["estimated_input_tokens"] > 0
    assert result["candidate_runs"][0]["estimated_cost_usd"] > 0
    assert result["candidate_runs"][1]["estimated_cost_usd"] is None
    assert result["destinations"]["writes_now"] == []
    assert "chat-eval-" in result["destinations"]["live_report_if_authorized"]
