import json

import pytest

from src.conversational_analytics.evaluation import (
    BUSINESS_FIXTURE_PATH,
    FIXTURE_PATH,
    SAFETY_CURRENT_FIXTURE_PATH,
    phase_cases,
    render_dry_run,
)
from src.conversational_analytics.evaluation_business import estimate_phase2, validate_business_fixture


def test_business_proposal_is_separate_pinned_and_approved_only_for_stage_one():
    business = json.loads(BUSINESS_FIXTURE_PATH.read_text(encoding="utf-8"))
    holdout_before = FIXTURE_PATH.read_bytes()
    validate_business_fixture(business)
    assert business["status"] == "OWNER_APPROVED"
    approval = business["owner_approval"]
    assert approval["approved_live_stages"] == [1]
    assert approval["business_questions_and_rubrics_approved"] is True
    assert approval["case_ratings_approved"] is False
    assert approval["model_answer_ratings_status"] == "not_started"
    assert len(business["cases"]) == 30
    safety = json.loads(SAFETY_CURRENT_FIXTURE_PATH.read_text(encoding="utf-8"))
    assert len(safety["cases"]) == 40
    selected = phase_cases(business["cases"], safety["cases"], 1)
    assert len(selected) == 58
    assert sum(case["id"].startswith("N") for case in selected) == 18
    assert len(approval["approved_scope"]["future_dependency_case_ids"]) == 12
    assert FIXTURE_PATH.read_bytes() == holdout_before


def test_draft_business_fixture_is_rejected_before_provider_campaign(monkeypatch, tmp_path):
    from src.conversational_analytics import evaluation, evaluation_live_campaign

    draft = json.loads(BUSINESS_FIXTURE_PATH.read_text(encoding="utf-8"))
    draft["status"] = "DRAFT_PENDING_OWNER_APPROVAL"
    fixture = tmp_path / "business-draft.json"
    fixture.write_text(json.dumps(draft), encoding="utf-8")
    monkeypatch.setattr(
        evaluation_live_campaign,
        "_live_provider_run",
        lambda **kwargs: pytest.fail("provider boundary must not run for a draft fixture"),
    )

    with pytest.raises(SystemExit) as error:
        evaluation.main(
            [
                "--run",
                "--opt-in",
                "--budget-usd",
                "3",
                "--fixture",
                str(fixture),
                "--stage",
                "1",
                "--output-dir",
                str(tmp_path / "reports"),
                "--campaign-state",
                str(tmp_path / "campaign.json"),
            ]
        )

    assert error.value.code == 2
    assert not (tmp_path / "campaign.json").exists()


def test_business_live_stage_without_owner_authorization_stops_before_provider(monkeypatch, tmp_path):
    from src.conversational_analytics import evaluation, evaluation_live_campaign

    monkeypatch.setattr(
        evaluation_live_campaign,
        "_live_provider_run",
        lambda **kwargs: pytest.fail("provider boundary must not run for an unauthorized stage"),
    )

    with pytest.raises(SystemExit) as error:
        evaluation.main(
            [
                "--run",
                "--opt-in",
                "--budget-usd",
                "3",
                "--fixture",
                str(BUSINESS_FIXTURE_PATH),
                "--stage",
                "2",
                "--output-dir",
                str(tmp_path / "reports"),
                "--campaign-state",
                str(tmp_path / "campaign.json"),
            ]
        )

    assert error.value.code == 2
    assert not (tmp_path / "campaign.json").exists()


def test_f29_stage_counts_include_multiturns_and_repeated_luna_runs():
    report = estimate_phase2()
    stage1, stage2, stage3 = report["stages"]
    assert stage1["candidate_run_count"] == 116  # two prompts × 58 cases
    assert stage1["candidate_estimates"][0]["estimated_input_tokens_range"] == [7_440_000, 12_400_000]
    assert stage2["candidate_run_count"] == 60
    assert stage3["candidate_run_count"] == 420  # 4 × 70 + 2 repeated Luna × 70
    luna = [row for row in stage3["candidate_estimates"] if "luna" in row["candidate"]]
    assert all(row["estimated_input_tokens_range"][0] == 8_880_000 for row in luna)


def test_dry_run_models_all_turns_and_does_not_select_a_winner():
    cases = [
        {
            "id": "N24",
            "question": "first",
            "turns": ["first", "second", "third"],
            "expected": {"status": "supported"},
        }
    ]
    report = render_dry_run(cases, models=["gpt-6-luna@medium"], prices={"gpt-6-luna@medium": (0.1, 0.5)})
    assert report["provider_calls"] == 0
    assert report["planned_provider_calls_total"] == 3
    assert report["candidate_runs"][0]["estimated_input_tokens"] == 120_000
    assert report["candidate_runs"][0]["reasoning_effort"] == "medium"
    assert report["destinations"]["writes_now"] == []


def test_cache_scenario_does_not_add_cached_tokens_twice():
    standard = estimate_phase2(cache_hit_rate=0)["stages"][0]["candidate_estimates"][0]["cost_usd_range"]
    cached = estimate_phase2(cache_hit_rate=0.8)["stages"][0]["candidate_estimates"][0]["cost_usd_range"]
    assert cached[0] < standard[0]
    assert cached[1] < standard[1]
