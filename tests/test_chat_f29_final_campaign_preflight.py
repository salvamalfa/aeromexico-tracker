from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from scripts.chat.prepare_final_campaign import DEFAULT_PROFILE, build_plan
from scripts.chat.render_f29_coverage_matrix import render_matrix

ROOT = Path(__file__).resolve().parents[1]
MATRIX = ROOT / "docs/chat/revision-fase-2/F2.9-matriz-cobertura-final.md"


def test_profile_dry_run_selects_all_business_cases_without_live_side_effects():
    plan = build_plan(profile_path=DEFAULT_PROFILE)

    assert plan["candidate"] == "gpt-6.1-sol@low"
    assert plan["campaign_id"] == "f2-9-stage-3-business-partial-v1"
    assert plan["cohort"] == "business_only_partial_stage3"
    assert "excluded_by_explicit_owner_direction" in plan["safety_scope"]
    assert plan["case_count"] == 30
    assert plan["messages_per_candidate"] == 34
    assert plan["repetitions"] == 1
    assert plan["projection"]["projected_input_tokens"] == 1_909_558
    assert plan["projection"]["projected_output_tokens"] == 9_423
    assert plan["projection"]["cost_before_margin_usd"] == 4.86812
    assert plan["projection"]["safety_margin_fraction"] == 0.35
    assert plan["projection"]["proposed_reserve_usd"] == 6.58
    assert plan["source_hashes"]["model_catalog"] == (
        "9744c985f051c898a8af6e8d3c8766c6885e77d8a13d55b72e30427b15468d4c"
    )
    assert plan["source_hashes"]["public_stage2_closeout"] == (
        "bf03c82e52fcff3b89fbcf18794218300149ae6859950199a6fd90c56fdd522d"
    )
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


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("final_report", "0" * 64, "no coincide con el cierre fijado"),
        ("terminal_recovery", "f" * 64, "no coincide con el cierre fijado"),
    ],
)
def test_preflight_rejects_custom_profile_source_hashes_not_bound_to_public_closeout(
    tmp_path: Path, field: str, value: str, message: str
):
    profile = json.loads(DEFAULT_PROFILE.read_text(encoding="utf-8"))
    profile["measured_reference"]["source_hashes"][field] = value
    tampered = tmp_path / "profile.json"
    tampered.write_text(json.dumps(profile), encoding="utf-8")

    with pytest.raises(ValueError, match=message):
        build_plan(profile_path=tampered)


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("completed_input_tokens", 1, "no coincide con el total del cierre F2.9 fijado"),
        ("completed_output_tokens", 0, "debe ser un total entero positivo"),
    ],
)
def test_preflight_rejects_custom_profile_token_totals_below_pinned_closeout(
    tmp_path: Path, field: str, value: int, message: str
):
    profile = json.loads(DEFAULT_PROFILE.read_text(encoding="utf-8"))
    profile["measured_reference"][field] = value
    tampered = tmp_path / "profile.json"
    tampered.write_text(json.dumps(profile), encoding="utf-8")

    with pytest.raises(ValueError, match=message):
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


def test_matrix_is_generated_from_exact_frozen_questions_and_expectations():
    fixture = json.loads((ROOT / "tests/fixtures/chat_evals/business_proposed.json").read_text())
    assert MATRIX.read_text(encoding="utf-8") == render_matrix(fixture)
    for case in fixture["cases"]:
        assert f"| {case['id']} |" in MATRIX.read_text(encoding="utf-8")
        assert f"`{case['expected']['status']}` · `{case['expected']['behavior']}`" in MATRIX.read_text(
            encoding="utf-8"
        )
    assert "2027" in MATRIX.read_text(encoding="utf-8")
    assert "1T26 + 2T26" in MATRIX.read_text(encoding="utf-8")
    assert "gasto total/participación del combustible" in MATRIX.read_text(encoding="utf-8")


def test_matrix_keeps_turn_level_gold_sources_and_constraints_for_n24_to_n26():
    fixture = json.loads((ROOT / "tests/fixtures/chat_evals/business_proposed.json").read_text())
    matrix = render_matrix(fixture)
    rows = {
        case_id: next(line for line in matrix.splitlines() if line.startswith(f"| {case_id} |"))
        for case_id in ("N24", "N25", "N26")
    }

    assert "6014000.0 passengers (2T26)" in rows["N24"]
    assert "8064000.0 passengers (2T26)" in rows["N24"]
    assert "executive.json" in rows["N24"]
    assert "turno 3" in rows["N24"]
    assert "prohibir afirmaciones numéricas" in rows["N24"]
    assert "no provisional growth winner" in rows["N24"]
    assert "Volaris creció" in rows["N24"]

    for case_id in ("N25", "N26"):
        assert "84.9" in rows[case_id]
        assert "2T26" in rows[case_id]
        assert "executive.json" in rows[case_id]
    assert "preservar" in rows["N25"]
    assert "preservar" in rows["N26"]


def test_matrix_renderer_rejects_any_unfrozen_fixture_change():
    from scripts.chat.render_f29_coverage_matrix import render_matrix

    fixture = json.loads((ROOT / "tests/fixtures/chat_evals/business_proposed.json").read_text())
    fixture["cases"][19]["turns"][0] = "invented question"
    with pytest.raises(ValueError, match="fixture congelado"):
        render_matrix(fixture)


@pytest.mark.parametrize("repetitions", [0, -1, 2, True, 1.0, "1"])
def test_final_preflight_rejects_unfunded_or_invalid_repetition_counts(
    tmp_path: Path, repetitions
):
    profile = json.loads(DEFAULT_PROFILE.read_text(encoding="utf-8"))
    profile["run_repetitions"] = repetitions
    changed_profile = tmp_path / "profile.json"
    changed_profile.write_text(json.dumps(profile), encoding="utf-8")

    with pytest.raises(ValueError, match="run_repetitions|única repetición presupuestada"):
        build_plan(profile_path=changed_profile)
