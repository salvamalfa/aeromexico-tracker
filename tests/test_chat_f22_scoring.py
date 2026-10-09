"""Focused safeguards for F2.2 gold and multi-turn scoring."""

import copy
import json

from src.conversational_analytics.evaluation import BUSINESS_FIXTURE_PATH, verify_observation
from src.conversational_analytics.evaluation_live import _numeric_gold_summary
from src.conversational_analytics.evaluation_live_scoring import score_live_case


def _case(case_id: str) -> dict:
    payload = json.loads(BUSINESS_FIXTURE_PATH.read_text(encoding="utf-8"))
    return copy.deepcopy(next(case for case in payload["cases"] if case["id"] == case_id))


def test_supported_query_with_empty_gold_cannot_pass():
    case = {
        "id": "empty-gold",
        "expected": {"status": "supported", "plan": {"metric_ids": ["x"]}, "rows": []},
    }
    result = verify_observation(case, {"status": "supported", "plan": {"metric_ids": ["x"]}, "rows": []})
    assert not result.passed
    assert "gold incompleto" in result.failures[0]


def test_n24_provisional_winner_does_not_pass_its_clarification_turn():
    case = _case("N24")
    _, grade = score_live_case(
        case, [], "", expected_versions={}, scope={}, metric_dimensions={},
        turn_responses=["Aeroméxico: 84.9%", "Volaris: 84.8%", "Volaris creció más. ¿En pasajeros o en ocupación?"],
        turn_tool_calls=[[], [], []],
    )
    assert not grade["turn_grades"][2]["passed"]
    assert "forbidden_winner_claim_before_clarification" in grade["turn_grades"][2]["failures"]


def test_clarification_can_repeat_period_label_without_numeric_answer():
    case = _case("N24")
    _, grade = score_live_case(
        case, [], "", expected_versions={}, scope={}, metric_dimensions={},
        turn_responses=["¿Cuál métrica quieres comparar?", "Volaris y Viva tienen valores distintos.", "¿Qué métrica quieres comparar en 2T26?"],
        turn_tool_calls=[[], [], []],
    )
    assert grade["turn_grades"][2]["passed"]


def test_numeric_tripwire_still_rejects_claims_with_separators_or_suffixes():
    case = _case("N20")
    for answer in (
        "Aeroméxico tendrá 1,200 pasajeros adicionales en 2027.",
        "Aeroméxico tendrá 1.2m pasajeros en 2027.",
    ):
        _, grade = score_live_case(
            case, [], answer, expected_versions={}, scope={}, metric_dimensions={},
        )
        assert not grade["passed"]
        assert "unsupported_absolute_numeric_claim" in grade["failures"]


def test_followup_requires_period_and_english_translation_rejects_mixed_language():
    case = _case("N26")
    _, grade = score_live_case(
        case, [], "", expected_versions={}, scope={}, metric_dimensions={},
        turn_responses=["El factor de ocupación de Aeroméxico fue 84.9% en 2T26.", "Aeroméxico is ocupó 84.9% in 2T26."],
        turn_tool_calls=[[], []],
    )
    followup = grade["turn_grades"][1]
    assert not followup["passed"]
    assert "translation_not_detectably_english" in followup["failures"]


def test_followup_preserves_period_value_and_english_language():
    case = _case("N26")
    _, grade = score_live_case(
        case, [], "", expected_versions={}, scope={}, metric_dimensions={},
        turn_responses=["El factor de ocupación de Aeroméxico fue 84.9% en 2T26.", "The load factor for Aeroméxico was 84.9% in 2T26."],
        turn_tool_calls=[[], []],
    )
    assert grade["turn_grades"][1]["passed"]


def test_english_followup_cannot_drop_metric_or_entity():
    case = _case("N26")
    _, grade = score_live_case(
        case, [], "", expected_versions={}, scope={}, metric_dimensions={},
        turn_responses=["El factor de ocupación de Aeroméxico fue 84.9% en 2T26.", "Aeroméxico recorded 84.9% in 2T26."],
        turn_tool_calls=[[], []],
    )
    assert not grade["turn_grades"][1]["passed"]
    assert "followup_changed_or_omitted_entity_or_metric" in grade["turn_grades"][1]["failures"]


def test_unsupported_business_total_rejects_invented_absolute_number():
    case = _case("N01")
    _, grade = score_live_case(
        case, [], "Fueron 7,200,000 pasajeros.",
        expected_versions={}, scope={}, metric_dimensions={},
    )
    assert not grade["passed"]
    assert "unsupported_absolute_numeric_claim" in grade["failures"]


def test_forecast_refusal_can_repeat_requested_year_without_numeric_claim():
    case = _case("N20")
    _, grade = score_live_case(
        case, [], "No puedo pronosticar pasajeros para 2027; puedo mostrarte datos históricos.",
        expected_versions={}, scope={}, metric_dimensions={},
    )
    assert grade["passed"]
    assert "unsupported_absolute_numeric_claim" not in grade["failures"]


def test_forecast_refusal_rejects_invented_passenger_total():
    case = _case("N20")
    _, grade = score_live_case(
        case, [], "Aeroméxico tendrá 8,000,000 pasajeros en 2027.",
        expected_versions={}, scope={}, metric_dimensions={},
    )
    assert not grade["passed"]
    assert "unsupported_absolute_numeric_claim" in grade["failures"]


def test_supported_gold_refusal_without_tool_evidence_is_a_failed_grade():
    case = _case("N02")
    observation, grade = score_live_case(
        case, [], "No tengo una cifra disponible; puedo revisarla.",
        expected_versions={}, scope={}, metric_dimensions={},
    )
    assert observation["status"] == "ungraded"
    assert grade["automatic_grade_type"] == "numeric_gold"
    assert grade["scored"] and not grade["passed"]


def test_numeric_gold_accuracy_keeps_refusals_and_unattempted_cases_in_denominator():
    base = _case("N02")
    selected = [dict(base, id=f"N02-{index}") for index in range(8)]
    case_records = [{
        "case_id": selected[0]["id"],
        "model_turn_completed": True,
        "quality": {"automatic_grade_type": "numeric_gold", "scored": True, "passed": True},
    }]
    summary = _numeric_gold_summary(selected, case_records)
    assert summary["numeric_gold_case_count"] == 8
    assert summary["numeric_gold_case_passed"] == 1
    assert summary["numeric_gold_accuracy"] == 0.125
    assert summary["numeric_gold_coverage"] == 0.125
