from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from scripts.chat.prepare_final_campaign import DEFAULT_PROFILE, build_plan

ROOT = Path(__file__).resolve().parents[1]
MATRIX = ROOT / "docs/chat/revision-fase-2/F2.9-matriz-cobertura-final.md"


def test_profile_dry_run_selects_all_business_cases_without_live_side_effects():
    plan = build_plan(profile_path=DEFAULT_PROFILE)

    assert plan["candidate"] == "gpt-6.1-sol@low"
    assert plan["case_count"] == 30
    assert plan["messages_per_candidate"] == 34
    assert plan["prompt_injection_cases_added"] == 0
    assert plan["provider_calls_now"] == 0
    assert plan["credentials_read"] is False
    assert plan["live_execution_available"] is False
    assert plan["projection"]["proposed_reserve_usd"] == 6.58
    assert plan["projection"]["owner_approval_required"] is True
    assert plan["gates"]["f23_f24_f25_f26_f27_f28_integrated_and_reviewed"] is False
    assert plan["gates"]["30_case_gold_and_support_expectations_revalidated"] is False
    assert plan["gates"]["snapshot_and_semantic_versions_pinned_after_integration"] is False
    assert plan["gates"]["new_stage3_budget_approved_and_funded"] is False


def test_preflight_allows_only_the_candidate_supported_by_measured_usage():
    with pytest.raises(ValueError, match="no coincide con la muestra medida"):
        build_plan(profile_path=DEFAULT_PROFILE, candidate_override="gpt-6.1-sol@medium")

    plan = build_plan(profile_path=DEFAULT_PROFILE, candidate_override="gpt-6.1-sol@low")
    assert plan["candidate"] == "gpt-6.1-sol@low"


def test_preflight_rejects_changed_fixture_and_cached_input_credit(tmp_path: Path):
    profile = json.loads(DEFAULT_PROFILE.read_text(encoding="utf-8"))
    profile["estimate"]["input_rate_basis"] = "cached input discount"
    tampered = tmp_path / "profile.json"
    tampered.write_text(json.dumps(profile), encoding="utf-8")
    with pytest.raises(ValueError, match="excluir créditos por caché"):
        build_plan(profile_path=tampered)


def test_matrix_covers_each_frozen_business_case_and_future_gates():
    fixture = json.loads((ROOT / "tests/fixtures/chat_evals/business_proposed.json").read_text())
    matrix = MATRIX.read_text(encoding="utf-8")
    rows = re.findall(r"^\| (N\d{2}) \|", matrix, flags=re.MULTILINE)

    assert len(rows) == 30
    assert len(set(rows)) == 30
    assert set(rows) == {case["id"] for case in fixture["cases"]}
    for required in (
        "query_business_metrics",
        "get_business_metric_definition",
        "query_routes",
        "find_shared_routes",
        "search_reports",
        "search_news",
        "f2_7_attributed_causes.v1.md",
        "presentation.py",
        "recibo del dueño",
        "snapshot y versión semántica",
    ):
        assert required in matrix
