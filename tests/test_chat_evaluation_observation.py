from __future__ import annotations

from pathlib import Path

from src.conversational_analytics.data.snapshot import Snapshot
from src.conversational_analytics.evaluation import load_fixture, verify_observation
from src.conversational_analytics.evaluation_observation import observation_from_tool_calls
from src.conversational_analytics.tools.registry import ToolRegistry


def _load_factor_case():
    return next(case for case in load_fixture()["cases"] if case["id"] == "es_am_lf_q2")


def _successful_call(name: str, arguments: dict, result: dict) -> dict:
    return {"name": name, "arguments": arguments, "result": result}


def test_comparison_preserves_all_actual_periods_and_rows():
    snapshot = Snapshot(Path("site"))
    registry = ToolRegistry(snapshot)
    args = {
        "metric_id": "load_factor",
        "entity_id": "AEROMEXICO",
        "periods": ["2026Q1", "2026Q2"],
    }
    result = registry.invoke("compare_metrics", args)
    observation = observation_from_tool_calls([_successful_call("compare_metrics", args, result)], "")

    assert observation["status"] == "supported"
    assert observation["plan"]["periods"] == ["2026Q1", "2026Q2"]
    assert [row["period"] for row in observation["rows"]] == ["2026Q1", "2026Q2"]
    q2_row = next(row for row in observation["rows"] if row["period"] == "2026Q2")
    source_q2 = next(row for row in result["rows"] if row["period"] == "2026Q2")
    assert q2_row["value"] == source_q2["value"]
    assert q2_row["source_references"] == source_q2["source_references"]
    assert q2_row["unit"] == source_q2["unit"]
    assert not verify_observation(_load_factor_case(), observation, check_response=False).passed


def test_time_series_exact_period_matches_numeric_fixture():
    snapshot = Snapshot(Path("site"))
    registry = ToolRegistry(snapshot)
    args = {
        "metric_id": "load_factor",
        "entity_id": "AEROMEXICO",
        "start_period": "2026Q2",
        "end_period": "2026Q2",
    }
    result = registry.invoke("get_time_series", args)
    observation = observation_from_tool_calls([_successful_call("get_time_series", args, result)], "")

    assert observation["status"] == "supported"
    assert observation["plan"] == _load_factor_case()["expected"]["plan"]
    assert observation["rows"][0]["value"] == result["rows"][0]["value"]
    assert observation["rows"][0]["source_references"] == result["rows"][0]["source_references"]
    assert verify_observation(_load_factor_case(), observation, check_response=False).passed


def test_query_with_wrong_metric_remains_supported_evidence_and_fails_golden():
    snapshot = Snapshot(Path("site"))
    registry = ToolRegistry(snapshot)
    args = {"metric_ids": ["ask_km"], "entity_ids": ["AEROMEXICO"], "periods": ["2026Q2"]}
    result = registry.invoke("query_metrics", args)
    observation = observation_from_tool_calls([_successful_call("query_metrics", args, result)], "")

    graded = verify_observation(_load_factor_case(), observation, check_response=False)
    assert observation["status"] == "supported"
    assert not graded.passed
    assert any("plan" in failure or "fila ausente" in failure for failure in graded.failures)


def test_tool_errors_are_not_treated_as_numeric_observations():
    error_call = _successful_call("query_metrics", {}, {"error": {"code": "tool_rejected"}})
    observation = observation_from_tool_calls([error_call], "")
    assert observation == {"status": "ungraded", "plan": None, "rows": [], "response": ""}
