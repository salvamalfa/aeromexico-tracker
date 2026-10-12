from __future__ import annotations

import html
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
    assert plan["projection"]["projected_input_tokens_range"] == [2_055_140, 2_103_667]
    assert plan["projection"]["projected_input_tokens"] == 2_103_667
    assert plan["projection"]["projected_output_tokens"] == 9_423
    assert plan["projection"]["cost_before_margin_usd_range"] == [5.232075, 5.353393]
    assert plan["projection"]["historical_scaled_baseline_cost_before_margin_usd"] == 4.86812
    assert plan["projection"]["context_delta_input_cost_before_margin_usd_range"] == [0.363955, 0.485272]
    assert plan["projection"]["safety_margin_fraction"] == 0.35
    assert plan["projection"]["cost_after_margin_usd_range"] == [7.0633, 7.2271]
    assert plan["projection"]["proposed_reserve_usd"] == 8.0
    context = plan["projection"]["context_delta"]
    assert context["prompt_r1_effective_utf8_bytes"] == 8_937
    assert context["prompt_r2_proposed_utf8_bytes"] == 11_166
    assert context["prompt_delta_utf8_bytes_per_request"] == 2_229
    assert context["historical_tool_schema_utf8_bytes"] == 3_306
    assert context["historical_tool_schema_sha256"] == (
        "1ff0d3a35647f7a0c2fc956884a4d267b0148065ccd3e2469139463f859bea19"
    )
    assert context["current_tool_schema_utf8_bytes"] == 7_620
    assert context["tool_schema_delta_utf8_bytes_per_request"] == 4_314
    assert context["total_delta_utf8_bytes_per_request"] == 6_543
    assert context["modeled_provider_requests"] == 89
    assert context["modeled_provider_request_hypothesis_range"] == [85, 89]
    assert context["tool_calls"] == 55
    assert context["tool_result_serialized_utf8_bytes"] == 95_232
    assert context["largest_tool_result_utf8_bytes"] == 15_652
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
    assert plan["projection"]["proposed_reserve_usd"] == 8.0
    assert plan["projection"]["owner_approval_required"] is True
    assert plan["gates"]["f23_f24_f25_f26_f27_f28_integrated_and_reviewed"] is False
    assert plan["gates"]["30_case_gold_and_support_expectations_revalidated"] is False
    assert plan["gates"]["snapshot_and_semantic_versions_pinned_after_integration"] is False
    assert plan["gates"]["new_stage3_budget_approved_and_funded"] is False


def test_stage3_empirical_reservation_admits_all_34_messages_under_eight_dollars():
    from src.conversational_analytics.config import ChatConfig
    from src.conversational_analytics.evaluation_live_reservation import (
        case_reservation_cost,
        reservation_assumption,
    )

    plan = build_plan(profile_path=DEFAULT_PROFILE)
    config = ChatConfig(
        provider="openai",
        model="gpt-6.1-sol",
        estimated_input_cost_per_million=2.0,
        estimated_output_cost_per_million=10.0,
        cache_write_input_multiplier=1.25,
        long_context_input_multiplier=2.0,
        long_context_output_multiplier=1.5,
        long_context_threshold_input_tokens=272_000,
    )
    assumption = reservation_assumption(config, plan["reservation_assumption_override"])
    assert assumption["campaign_sha256"] == plan["campaign_sha256"]
    assert assumption["planned_request_count"] == 34
    assert assumption["input_tokens_per_turn"] < 100_000
    assert assumption["output_tokens_per_turn"] < 1_000
    fixture = json.loads((ROOT / "tests/fixtures/chat_evals/business_proposed.json").read_text())
    reserved = sum(
        case_reservation_cost(config, assumption, len(case.get("turns", [case["question"]])))
        for case in fixture["cases"]
    )
    assert reserved <= 8.0


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
    ("field", "value"),
    [
        ("new_stage3_budget_approved_and_funded", True),
        ("f23_f24_f25_f26_f27_f28_integrated_and_reviewed", True),
        ("30_case_gold_and_support_expectations_revalidated", True),
        ("snapshot_and_semantic_versions_pinned_after_integration", True),
    ],
)
def test_preflight_rejects_custom_profiles_that_claim_pending_gates_are_complete(
    tmp_path: Path, field: str, value: bool
):
    profile = json.loads(DEFAULT_PROFILE.read_text(encoding="utf-8"))
    profile["gates"][field] = value
    tampered = tmp_path / "profile.json"
    tampered.write_text(json.dumps(profile), encoding="utf-8")

    with pytest.raises(ValueError, match="puertas pendientes fijadas"):
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


def test_matrix_preserves_the_complete_frozen_expected_contract_for_every_case():
    fixture = json.loads((ROOT / "tests/fixtures/chat_evals/business_proposed.json").read_text())
    matrix = render_matrix(fixture)

    for case in fixture["cases"]:
        expected = json.dumps(
            case["expected"], ensure_ascii=False, sort_keys=True, separators=(",", ":")
        )
        assert f"<pre>{html.escape(expected)}</pre>" in matrix

    n07 = next(case for case in fixture["cases"] if case["id"] == "N07")["expected"]
    n11 = next(case for case in fixture["cases"] if case["id"] == "N11")["expected"]
    n21 = next(case for case in fixture["cases"] if case["id"] == "N21")["expected"]
    assert n07["derived_gold"]["kind"] == "percentage_point_change"
    assert set(n07["derived_gold"]["values_pp"]) == {"VOLARIS", "AEROMEXICO"}
    assert "does not establish" in n07["derived_gold"]["interpretation"]
    assert n11["derived_gold"]["winner"] == "VOLARIS"
    assert set(n11["derived_gold"]["values_pp"]) == {"AEROMEXICO", "VOLARIS", "VIVA_AEROBUS"}
    assert n21["derived_gold"]["value"] == 74.4
    assert n21["derived_gold"]["raw_fraction_sum"] == 0.7444707301790031
    assert n21["derived_gold"]["formula"] == "round(sum(row.value) * 100, 1)"


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
