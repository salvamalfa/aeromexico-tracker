"""Quality grading for one completed live evaluation turn."""

from __future__ import annotations

import re
from typing import Any

from .evaluation import _response_term_present, verify_observation
from .evaluation_observation import observation_from_tool_calls


def _has_non_context_numeric_claim(response: str) -> bool:
    """Catch result-like numbers while allowing a requested year as context."""
    without_period_labels = re.sub(
        r"\b(?:[1-4]\s*[tq]\s*(?:20)?\d{2}|(?:19|20)\d{2}\s*q\s*[1-4]|q\s*[1-4]\s*(?:19|20)\d{2})\b",
        " ",
        response,
        flags=re.IGNORECASE,
    )
    pattern = r"(?<![\w])\d[\d.,]*(?:\s*(?:%|pasajeros?|vuelos?|usd|mxn|d[oó]lares?))?"
    for match in re.finditer(pattern, without_period_labels, re.IGNORECASE):
        token = match.group(0).strip()
        if token.endswith("%") or re.search(r"[a-záéíóúüñ]", token, re.IGNORECASE):
            return True
        try:
            value = float(token.replace(",", ""))
        except ValueError:
            return True
        if not (1900 <= value <= 2100 and value.is_integer()):
            return True
    return False


def _has_clarification_request(response: str) -> bool:
    """Recognize direct questions and concise imperative/contextual requests."""
    if re.search(r"[?¿]", response):
        return True
    if re.search(
        r"\b(?:please\s+)?(?:clarify|specify|indicate|tell\s+me|confirm|choose|provide)\b"
        r"|\b(?:por\s+favor\s+)?(?:aclara|aclare|especifica|especifique|indica|indique|"
        r"precisa|precise|dime|dígame|confirma|confirme|elige|elija)\b",
        response,
        re.IGNORECASE,
    ):
        return True
    return bool(re.search(
        r"\b(?:I\s+need|we\s+need|necesito|hace\s+falta)\b.{0,100}\b"
        r"(?:period|quarter|metric|measure|segment|criterio|periodo|trimestre|métrica|medida|segmento)\b",
        response,
        re.IGNORECASE,
    ))


def score_live_case(
    case: dict[str, Any],
    tool_calls: list[dict[str, Any]],
    response: str,
    *,
    expected_versions: dict[str, str],
    scope: dict[str, Any],
    metric_dimensions: dict[str, list[str]],
    turn_responses: list[str] | None = None,
    turn_tool_calls: list[list[dict[str, Any]]] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Build the evidence observation and its automatic quality grade."""
    expected_turns = case.get("expected", {}).get("turns")
    if isinstance(expected_turns, list):
        responses = turn_responses or []
        calls_by_turn = turn_tool_calls or [[] for _ in responses]
        turn_grades = []
        for index, expected in enumerate(expected_turns):
            response_for_turn = responses[index] if index < len(responses) else ""
            calls_for_turn = calls_by_turn[index] if index < len(calls_by_turn) else []
            status = expected.get("status")
            if status == "supported":
                if not expected.get("plan") or not expected.get("rows"):
                    turn_grades.append({"scored": False, "not_scored_reason": "missing_numeric_gold"})
                    continue
                per_turn_case = {"id": f"{case['id']}-turn-{index+1}", "expected": expected}
                per_turn_observation = observation_from_tool_calls(
                    calls_for_turn,
                    response_for_turn,
                    expected_versions=expected_versions,
                    scope=scope,
                    metric_dimensions=metric_dimensions,
                )
                result = verify_observation(per_turn_case, per_turn_observation)
                turn_grades.append({"scored": True, "passed": result.passed, "checks": result.checks, "failures": result.failures})
            elif status == "clarify":
                forbidden = [
                    phrase for phrase in expected.get("must_not_contain", [])
                    if phrase.casefold() in response_for_turn.casefold()
                ]
                numeric_claim = (
                    _has_non_context_numeric_claim(response_for_turn)
                    if expected.get("forbid_numeric_claims")
                    else False
                )
                clarify_requested = _has_clarification_request(response_for_turn)
                failed = not clarify_requested or numeric_claim or bool(forbidden)
                failures = []
                if not clarify_requested:
                    failures.append("missing_clarification_request")
                if numeric_claim:
                    failures.append("provisional_numeric_claim_before_clarification")
                if forbidden:
                    failures.append("forbidden_winner_claim_before_clarification")
                turn_grades.append({
                    "scored": True, "passed": not failed,
                    "checks": ["clarifies_without_provisional_claim"] if not failed else [],
                    "failures": failures,
                })
            elif status in {"rephrase", "translate_en"}:
                prior = responses[index-1] if index > 0 and index-1 < len(responses) else ""
                required_terms = expected.get("preserve_response_terms", [])
                alias_groups = expected.get("preserve_any_terms", [])
                prior_percentages = sorted(re.findall(r"(?<![\w.])\d+(?:[.,]\d+)?\s*%", prior))
                current_percentages = sorted(re.findall(r"(?<![\w.])\d+(?:[.,]\d+)?\s*%", response_for_turn))
                no_requery = not calls_for_turn
                preserves_value = bool(prior_percentages) and prior_percentages == current_percentages
                preserves_terms = bool(required_terms) and all(
                    _response_term_present(term, response_for_turn) for term in required_terms
                )
                preserves_aliases = all(
                    isinstance(group, list) and group
                    and any(_response_term_present(term, response_for_turn) for term in group)
                    for group in alias_groups
                )
                if status == "translate_en":
                    words = set(re.findall(r"[a-záéíóúüñ]+", response_for_turn.casefold()))
                    spanish_markers = {
                        "ocupó", "ocupacion", "ocupación", "pasajeros", "aerolínea", "periodo",
                        "trimestre", "fue", "es", "del", "con", "y", "que", "los", "las",
                    }
                    language_ok = bool(words & {"the", "was", "in", "of", "is", "seats", "occupied", "load", "factor"}) and not bool(words & spanish_markers)
                else:
                    language_ok = True
                passed = no_requery and preserves_value and preserves_terms and preserves_aliases and language_ok
                failures = []
                if not no_requery: failures.append("followup_made_tool_call")
                if not preserves_value: failures.append("followup_changed_or_omitted_numeric_value")
                if not preserves_terms: failures.append("followup_changed_or_omitted_period_or_unit")
                if not preserves_aliases: failures.append("followup_changed_or_omitted_entity_or_metric")
                if not language_ok: failures.append("translation_not_detectably_english")
                turn_grades.append({"scored": True, "passed": passed, "checks": ["no_requery", "numeric_value_preserved", "period_and_unit_preserved", "entity_and_metric_preserved", "target_language"] if passed else [], "failures": failures})
            else:
                turn_grades.append({"scored": False, "not_scored_reason": "unknown_turn_expectation"})
        all_scored = bool(turn_grades) and all(item.get("scored") for item in turn_grades)
        passed = all_scored and all(item.get("passed") for item in turn_grades)
        observation = {"status": "multi_turn", "plan": None, "rows": [], "response": "\n\n".join(responses)}
        return observation, {"scored": all_scored, "passed": passed, "turn_grades": turn_grades,
                             "automatic_grade_type": "multi_turn_tripwires",
                             "checks": ["all_turn_expectations"] if passed else [],
                             "failures": [failure for item in turn_grades for failure in item.get("failures", [])],
                             "requires_blinded_human_rubric": True,
                             "human_rubric_status": "pending_owner_approval"}

    if case.get("expected", {}).get("status") == "supported" and (
        not case["expected"].get("plan") or not case["expected"].get("rows")
    ):
        return {"status": "ungraded", "plan": None, "rows": [], "response": response}, {
            "scored": False, "not_scored_reason": "missing_numeric_gold"
        }
    observation = observation_from_tool_calls(
        tool_calls,
        response,
        expected_versions=expected_versions,
        scope=scope,
        metric_dimensions=metric_dimensions,
    )
    if case["expected"]["status"] == "supported" and observation["status"] == "supported":
        scored = verify_observation(case, observation)
        grade = {
            "scored": True,
            "passed": scored.passed,
            "automatic_grade_type": "numeric_gold",
            "checks": scored.checks,
            "failures": scored.failures,
            "requires_blinded_human_rubric": True,
            "human_rubric_status": "pending_owner_approval",
        }
    elif case["expected"]["status"] == "supported":
        grade = {
            "scored": True,
            "passed": False,
            "automatic_grade_type": "numeric_gold",
            "checks": [],
            "failures": ["supported_answer_not_observed"],
            "not_scored_reason": observation["not_scored_reason"],
            "requires_blinded_human_rubric": True,
            "human_rubric_status": "pending_owner_approval",
        }
    else:
        expected = case["expected"]["status"]
        checks: list[str] = []
        failures: list[str] = []
        # Outcome checks are tripwires, not substitutes for the owner's rubric.
        if expected == "clarify":
            if not _has_clarification_request(response):
                failures.append("clarification_without_request")
            else:
                checks.append("clarification_request_present")
            if _has_non_context_numeric_claim(response):
                failures.append("numeric_answer_given_when_clarification_expected")
        elif expected in {"unsupported", "refused"}:
            if re.search(r"(?<!\w)\d+(?:[.,]\d+)?\s*%", response):
                failures.append("unsupported_numeric_percentage")
            else:
                checks.append("no_percentage_claim")
            if case["expected"].get("forbid_numeric_claims") and _has_non_context_numeric_claim(response):
                failures.append("unsupported_absolute_numeric_claim")
            for forbidden in case["expected"].get("must_not_contain", []):
                if forbidden.casefold() in response.casefold():
                    failures.append(f"forbidden_claim:{forbidden}")
        if re.search(r"\d,\d+\s*%", response):
            failures.append("decimal_comma_format")
        else:
            checks.append("decimal_point_format")
        if len(re.findall(r"https://\S+", response)) != len(set(re.findall(r"https://\S+", response))):
            failures.append("duplicate_source_url_in_response")
        else:
            checks.append("no_duplicate_inline_source_url")
        grade = {
            "scored": True,
            "passed": not failures,
            "automatic_grade_type": "tripwire",
            "checks": checks,
            "failures": failures,
            "requires_blinded_human_rubric": True,
            "expected_outcome_for_grader": case["expected"]["status"],
            "human_rubric_status": "pending_owner_approval",
        }
    return observation, grade


__all__ = ["score_live_case"]
