"""A missing boundary flag stays distinct from an explicit failed flag."""

from __future__ import annotations

import json
from pathlib import Path

from src.conversational_analytics.evaluation_live_reconciliation import _terminal_boundary_rejection


def test_missing_boundary_flag_is_accepted_but_explicit_false_is_blocked() -> None:
    cases = json.loads(Path("tests/fixtures/chat_evals/safety_current.json").read_text())["cases"]
    expected_ids = {"es_card_conflicting_context", "en_private_context_override"}
    boundary_cases = [case for case in cases if case["id"] in expected_ids]
    assert {case["id"] for case in boundary_cases} == expected_ids

    for case in boundary_cases:
        row = {
            "case_id": case["id"],
            "status": "application_context_rejected",
            "provider_calls": 0,
            "provider_turn_started": False,
            "model_turn_completed": False,
            "quality": {"scored": False, "not_scored_reason": "application_context_rejected"},
        }
        assert "application_boundary_test_completed" not in row
        assert row["quality"]["scored"] is False and "passed" not in row["quality"]
        assert _terminal_boundary_rejection(row, case)

        row["application_boundary_test_completed"] = False
        assert not _terminal_boundary_rejection(row, case)
