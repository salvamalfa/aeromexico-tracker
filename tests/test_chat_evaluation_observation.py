from __future__ import annotations

from pathlib import Path

import pytest

from src.conversational_analytics.data.snapshot import Snapshot
from src.conversational_analytics.evaluation import load_fixture, verify_observation
from src.conversational_analytics.evaluation_observation import observation_from_tool_calls
from src.conversational_analytics.tools.registry import ToolRegistry

_TEST_VERSIONS = {"data_version": "fixture-data-v1", "semantic_version": "fixture-semantic-v1"}
_TEST_METRIC_DIMENSIONS = {
    "metric_a": [],
    "metric_b": [],
    "metric_c": [],
    "ask_km": [],
    "load_factor": [],
}


def _load_factor_case():
    return next(case for case in load_fixture()["cases"] if case["id"] == "es_am_lf_q2")


def _successful_call(name: str, arguments: dict, result: dict) -> dict:
    return {
        "name": name,
        "arguments": arguments,
        "scope": {},
        "result": {**result, "data_version": result.get("data_version", _TEST_VERSIONS["data_version"]),
                   "semantic_version": result.get("semantic_version", _TEST_VERSIONS["semantic_version"])},
    }


def _observe(
    calls: list[dict],
    response: str = "",
    *,
    expected_versions: dict | None = None,
    metric_dimensions: dict[str, list[str]] | None = None,
    scope: dict | None = None,
) -> dict:
    versions = expected_versions or (
        {key: calls[0]["result"][key] for key in ("data_version", "semantic_version")}
        if calls
        else _TEST_VERSIONS
    )
    return observation_from_tool_calls(
        calls,
        response,
        expected_versions=versions,
        scope=scope or {},
        metric_dimensions=metric_dimensions or _TEST_METRIC_DIMENSIONS,
    )


def _row(metric: str, period: str, *, entity: str = "AEROMEXICO", value: float = 0.5) -> dict:
    return {
        "metric_id": metric,
        "entity_id": entity,
        "period": period,
        "value": value,
        "unit": "fraction",
        "availability": "available",
        "source_references": [{"label": "public", "url": "https://example.test/source"}],
    }


def _call(name: str, arguments: dict, rows: list[dict], **result_fields) -> dict:
    result = {**_TEST_VERSIONS, "rows": rows, **result_fields}
    return {"name": name, "arguments": arguments, "result": result, "scope": {}}


def test_comparison_preserves_all_actual_periods_and_rows():
    snapshot = Snapshot(Path("site"))
    registry = ToolRegistry(snapshot)
    args = {
        "metric_id": "load_factor",
        "entity_id": "AEROMEXICO",
        "periods": ["2026Q1", "2026Q2"],
    }
    result = registry.invoke("compare_metrics", args)
    observation = _observe([_successful_call("compare_metrics", args, result)])

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
    observation = _observe([_successful_call("get_time_series", args, result)])

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
    observation = _observe([_successful_call("query_metrics", args, result)])

    graded = verify_observation(_load_factor_case(), observation, check_response=False)
    assert observation["status"] == "supported"
    assert not graded.passed
    assert any("plan" in failure or "fila ausente" in failure for failure in graded.failures)


def test_tool_errors_are_not_treated_as_numeric_observations():
    error_call = _successful_call("query_metrics", {}, {"error": {"code": "tool_rejected"}})
    observation = _observe([error_call])
    assert observation["status"] == "ungraded"
    assert observation["not_scored_reason"] == "no_successful_row_evidence"


def test_query_and_series_union_keeps_every_row_and_exact_duplicate_once():
    rows = [_row("metric_a", "2026Q2"), _row("metric_b", "2026Q2"), _row("metric_c", "2026Q2")]
    calls = [
        _call(
            "query_metrics",
            {"metric_ids": ["metric_a", "metric_b", "metric_c"], "entity_ids": ["AEROMEXICO"],
             "periods": ["2026Q2"]},
            rows,
        ),
        _call(
            "get_time_series",
            {"metric_id": "metric_a", "entity_id": "AEROMEXICO", "start_period": "2026Q2",
             "end_period": "2026Q2"},
            [rows[0]],
        ),
    ]

    observation = _observe(calls)

    assert observation["status"] == "supported"
    assert observation["plan"]["metric_ids"] == ["metric_a", "metric_b", "metric_c"]
    assert len(observation["rows"]) == 3
    assert observation["rows"][0]["source_references"] == rows[0]["source_references"]
    assert observation["evidence_tools"] == ["query_metrics", "get_time_series"]


@pytest.mark.parametrize(
    "field,changed",
    [
        ("value", 0.75),
        ("availability", "missing"),
        ("unit", "percent"),
        ("source_references", [{"label": "other", "url": "https://example.test/other"}]),
    ],
)
def test_conflicting_duplicate_rows_are_unscored(field: str, changed):
    first = _row("metric_a", "2026Q2")
    second = {**first, field: changed}
    query = _call(
        "query_metrics",
        {"metric_ids": ["metric_a"], "entity_ids": ["AEROMEXICO"], "periods": ["2026Q2"]},
        [first],
    )
    series = _call(
        "get_time_series",
        {"metric_id": "metric_a", "entity_id": "AEROMEXICO", "start_period": "2026Q2",
         "end_period": "2026Q2"},
        [second],
    )

    observation = _observe([query, series])

    assert observation["status"] == "ungraded"
    assert observation["not_scored_reason"] == "conflicting_duplicate_evidence"


def test_mixed_segment_scope_extra_rows_and_version_mismatch_fail_closed():
    base_args = {"metric_ids": ["metric_a"], "entity_ids": ["AEROMEXICO"], "periods": ["2026Q2"]}
    total = _row("metric_a", "2026Q2")
    domestic = {**total, "segment": "domestic"}
    mixed = [
        _call("query_metrics", {**base_args, "segment": "total"}, [{**total, "segment": "total"}]),
        _call("query_metrics", {**base_args, "segment": "domestic"}, [domestic]),
    ]
    segment_dimensions = {**_TEST_METRIC_DIMENSIONS, "metric_a": ["segment"]}
    assert _observe(mixed, metric_dimensions=segment_dimensions)["not_scored_reason"] == "mixed_segment_scope"

    extra = _call("query_metrics", base_args, [{**total, "metric_id": "metric_b"}])
    assert _observe([extra])["not_scored_reason"] == "evidence_row_outside_scope"

    malformed_segment = _call("query_metrics", {**base_args, "segment": 123}, [total])
    assert _observe([malformed_segment])["not_scored_reason"] == "invalid_evidence_arguments"

    mismatch = _call("query_metrics", base_args, [total])
    mismatch["result"]["semantic_version"] = "another-catalog"
    observed_mismatch = _observe([mismatch], expected_versions=_TEST_VERSIONS)
    assert observed_mismatch["not_scored_reason"] == "evidence_version_mismatch"

    compare = _call(
        "compare_metrics",
        {"metric_id": "metric_a", "entity_id": "AEROMEXICO", "periods": ["2026Q1", "2026Q2"],
         "data_version": "another-snapshot"},
        [_row("metric_a", "2026Q1"), _row("metric_a", "2026Q2")],
    )
    assert _observe([compare])["not_scored_reason"] == "evidence_version_mismatch"


def test_segment_inherited_from_pinned_context_is_kept_in_scope():
    scope = {"filters": {"segment": "domestic"}}
    args = {"metric_ids": ["metric_a"], "entity_ids": ["AEROMEXICO"], "periods": ["2026Q2"]}
    segment_dimensions = {**_TEST_METRIC_DIMENSIONS, "metric_a": ["segment"]}
    call = _call("query_metrics", args, [{**_row("metric_a", "2026Q2"), "segment": "domestic"}])
    call["scope"] = scope

    observation = observation_from_tool_calls(
        [call],
        "respuesta",
        expected_versions=_TEST_VERSIONS,
        scope=scope,
        metric_dimensions=segment_dimensions,
    )

    assert observation["status"] == "supported"
    assert observation["plan"]["filters"] == {"segment": "domestic"}
    assert observation["rows"][0]["segment"] == "domestic"

    missing_segment = _call("query_metrics", args, [_row("metric_a", "2026Q2")])
    missing_segment["scope"] = scope
    rejected = observation_from_tool_calls(
        [missing_segment],
        "respuesta",
        expected_versions=_TEST_VERSIONS,
        scope=scope,
        metric_dimensions=segment_dimensions,
    )
    assert rejected["not_scored_reason"] == "evidence_row_outside_scope"

    missing_required_segment = _call("query_metrics", args, [_row("metric_a", "2026Q2")])
    rejected_without_context = observation_from_tool_calls(
        [missing_required_segment],
        "respuesta",
        expected_versions=_TEST_VERSIONS,
        scope={},
        metric_dimensions=segment_dimensions,
    )
    assert rejected_without_context["not_scored_reason"] == "invalid_evidence_arguments"

    explicit_override = _call(
        "query_metrics",
        {**args, "segment": "international"},
        [{**_row("metric_a", "2026Q2"), "segment": "international"}],
    )
    explicit_override["scope"] = scope
    accepted_override = observation_from_tool_calls(
        [explicit_override],
        "respuesta",
        expected_versions=_TEST_VERSIONS,
        scope=scope,
        metric_dimensions=segment_dimensions,
    )
    assert accepted_override["status"] == "supported"
    assert accepted_override["plan"]["filters"] == {"segment": "international"}


def test_context_segment_is_ignored_for_metric_without_segment_dimension():
    scope = {"filters": {"segment": "domestic"}}
    args = {"metric_ids": ["load_factor"], "entity_ids": ["AEROMEXICO"], "periods": ["2026Q2"]}
    call = _call("query_metrics", args, [_row("load_factor", "2026Q2")])
    call["scope"] = scope

    observation = observation_from_tool_calls(
        [call],
        "respuesta",
        expected_versions=_TEST_VERSIONS,
        scope=scope,
        metric_dimensions=_TEST_METRIC_DIMENSIONS,
    )

    assert observation["status"] == "supported"
    assert observation["plan"] == {
        "metric_ids": ["load_factor"],
        "entity_ids": ["AEROMEXICO"],
        "periods": ["2026Q2"],
        "operation": "query",
    }

    invalid_explicit = _call(
        "query_metrics",
        {**args, "segment": "domestic"},
        [{**_row("load_factor", "2026Q2"), "segment": "domestic"}],
    )
    assert _observe([invalid_explicit])["not_scored_reason"] == "invalid_evidence_arguments"

    mixed_dimensions = {**_TEST_METRIC_DIMENSIONS, "metric_a": ["segment"]}
    invalid_mixed_query = _call(
        "query_metrics",
        {"metric_ids": ["metric_a", "load_factor"], "entity_ids": ["AEROMEXICO"],
         "periods": ["2026Q2"]},
        [_row("metric_a", "2026Q2"), _row("load_factor", "2026Q2")],
    )
    invalid_mixed_query["scope"] = scope
    assert _observe(
        [invalid_mixed_query], metric_dimensions=mixed_dimensions, scope=scope
    )["not_scored_reason"] == "invalid_evidence_arguments"


def test_successful_query_with_missing_requested_cells_is_unscored():
    args = {
        "metric_ids": ["metric_a", "metric_b"],
        "entity_ids": ["AEROMEXICO"],
        "periods": ["2026Q2"],
    }
    call = _call("query_metrics", args, [_row("metric_a", "2026Q2")])

    assert _observe([call])["not_scored_reason"] == "incomplete_successful_evidence"


def test_truncated_series_is_ungraded_and_missing_actual_period_fails_fixture():
    row = _row("metric_a", "2026Q2")
    series = _call(
        "get_time_series",
        {"metric_id": "metric_a", "entity_id": "AEROMEXICO", "start_period": "2026Q1",
         "end_period": "2026Q2"},
        [row],
    )
    case = {
        "id": "synthetic-series",
        "expected": {
            "status": "supported",
            "plan": {"metric_ids": ["metric_a"], "entity_ids": ["AEROMEXICO"],
                     "periods": ["2026Q1", "2026Q2"], "operation": "query"},
            "rows": [
                {**_row("metric_a", "2026Q1"), "source_references": row["source_references"]},
                row,
            ],
        },
    }
    observation = _observe([series])
    result = verify_observation(case, observation, check_response=False)
    assert observation["status"] == "supported"
    assert not result.passed
    assert any("periods" in failure for failure in result.failures)
    assert any("fila ausente" in failure for failure in result.failures)

    series["result"]["truncated"] = True
    assert _observe([series])["not_scored_reason"] == "truncated_evidence"
