"""Stage 3 must not score current answers against historical business gold."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.conversational_analytics import evaluation_live_scoring as scoring
from src.conversational_analytics.evaluation_live_support import _numeric_gold_summary
from src.conversational_analytics.evaluation_stage3_cases import current_stage3_cases
from src.conversational_analytics.evaluation_live_turns import run_conversation
from src.conversational_analytics.providers.base import ProviderResult


@pytest.mark.parametrize("case_id", ["N04", "N24", "N26"])
def test_current_cases_preserve_model_inputs_and_leave_grades_pending(case_id, monkeypatch):
    fixture = json.loads(Path("tests/fixtures/chat_evals/business_proposed.json").read_text())
    original = next(case for case in fixture["cases"] if case["id"] == case_id)
    before = copy.deepcopy(original)
    evidence = {
        "case_id": case_id,
        "status": "supported",
        "derived_expectations": [{"value": 123, "availability": "available"}],
        "private_test_marker": "GOLD_ONLY_MARKER",
    }
    coverage = {"campaign_sha256": "current-pinned-coverage", "cases": [evidence]}
    adapted = current_stage3_cases([original], coverage)[0]
    assert original == before
    assert {key: value for key, value in adapted.items() if key not in {"expected", "grading_mode"}} == {
        key: value for key, value in original.items() if key != "expected"
    }
    assert adapted["expected"]["status"] == "supported"
    assert adapted["expected"]["current_coverage"] == evidence
    assert "turns" not in adapted["expected"]
    if case_id == "N04":
        assert original["expected"]["status"] == "unsupported"

    provider_inputs = []
    provider = SimpleNamespace(
        max_turn_seconds=1,
        run_turn=lambda **kwargs: provider_inputs.append(kwargs) or ProviderResult("123", usage_complete=True),
    )
    run_conversation(
        provider, adapted, context=adapted.get("context", {}), tool_specs=[],
        call_tool=lambda *_args: {}, emit=lambda *_args: None,
        persist_session=lambda *_args: None, session=[], current_turn_index=[0], calls_by_turn=[],
    )
    assert [turn["messages"][0]["content"] for turn in provider_inputs] == original["turns"]
    assert all(turn["context"] == original.get("context", {}) for turn in provider_inputs)
    assert "GOLD_ONLY_MARKER" not in json.dumps([
        {key: turn[key] for key in ("messages", "context", "tool_specs")} for turn in provider_inputs
    ])

    observed = {"status": "supported", "plan": None, "rows": [], "response": "123"}
    monkeypatch.setattr(scoring, "observation_from_tool_calls", lambda *_args, **_kwargs: observed)
    monkeypatch.setattr(
        scoring, "verify_observation",
        lambda *_args, **_kwargs: pytest.fail("historical numeric gold must not be evaluated"),
    )
    observation, grade = scoring.score_live_case(
        adapted, [], "123", expected_versions={}, scope={}, metric_dimensions={},
        turn_responses=["123"], turn_tool_calls=[[]],
    )
    assert observation == observed
    assert grade["scored"] is False
    assert "passed" not in grade
    assert grade["human_rubric_status"] == "pending_owner_approval"
    assert grade["requires_blinded_human_rubric"] is True
    assert grade["coverage_campaign_sha256"] == coverage["campaign_sha256"]
    assert _numeric_gold_summary([adapted], [{"case_id": case_id, "quality": grade}])["numeric_gold_accuracy"] is None


def test_current_case_adapter_rejects_unmatched_coverage():
    with pytest.raises(ValueError, match="casos congelados"):
        current_stage3_cases([{"id": "N04"}], {"cases": [{"case_id": "N05"}]})
