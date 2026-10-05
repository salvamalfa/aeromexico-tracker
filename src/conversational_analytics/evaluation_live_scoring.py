"""Quality grading for one completed live evaluation turn."""

from __future__ import annotations

from typing import Any

from .evaluation import verify_observation
from .evaluation_observation import observation_from_tool_calls


def score_live_case(
    case: dict[str, Any],
    tool_calls: list[dict[str, Any]],
    response: str,
    *,
    expected_versions: dict[str, str],
    scope: dict[str, Any],
    metric_dimensions: dict[str, list[str]],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Build the evidence observation and its automatic quality grade."""
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
            "checks": scored.checks,
            "failures": scored.failures,
        }
    elif case["expected"]["status"] == "supported":
        grade = {"scored": False, "not_scored_reason": observation["not_scored_reason"]}
    else:
        grade = {
            "scored": False,
            "requires_blinded_human_rubric": True,
            "expected_outcome_for_grader": case["expected"]["status"],
        }
    return observation, grade


__all__ = ["score_live_case"]
