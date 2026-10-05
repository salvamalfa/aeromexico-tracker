"""Normalize and validate all successful semantic-tool evidence for the fixture verifier."""

from __future__ import annotations

from itertools import product
from typing import Any

_SUPPORTED_TOOLS = {"query_metrics", "compare_metrics", "get_time_series"}
_SEGMENTS = {"total", "domestic", "international"}
_ROW_FIELDS = (
    "metric_id",
    "entity_id",
    "period",
    "value",
    "unit",
    "availability",
    "source_references",
    "segment",
)


def observation_from_tool_calls(
    tool_calls: list[dict[str, Any]],
    response: str,
    *,
    expected_versions: dict[str, str],
    scope: dict[str, Any],
) -> dict[str, Any]:
    """Union successful query evidence or fail closed when its scope is ambiguous."""
    evidence: list[tuple[dict[str, Any], list[dict[str, Any]], str]] = []
    for call in tool_calls:
        name = call.get("name")
        if name not in _SUPPORTED_TOOLS:
            continue
        result = call.get("result")
        if isinstance(result, dict) and "error" in result:
            continue
        if not isinstance(result, dict) or not isinstance(result.get("rows"), list):
            return _ungraded(response, "invalid_successful_evidence")
        if result.get("truncated") is True:
            return _ungraded(response, "truncated_evidence")
        if any(result.get(key) != expected_versions.get(key) for key in ("data_version", "semantic_version")):
            return _ungraded(response, "evidence_version_mismatch")
        if call.get("scope") != scope:
            return _ungraded(response, "evidence_scope_mismatch")
        arguments = call.get("arguments")
        if not isinstance(arguments, dict):
            return _ungraded(response, "invalid_evidence_arguments")
        if not _segment_scope_is_valid(arguments, scope):
            return _ungraded(response, "invalid_evidence_arguments")
        if name == "compare_metrics" and any(
            arguments.get(key) not in (None, expected_versions.get(key))
            for key in ("data_version", "semantic_version")
        ):
            return _ungraded(response, "evidence_version_mismatch")
        rows = []
        for raw_row in result["rows"]:
            if not isinstance(raw_row, dict):
                return _ungraded(response, "invalid_evidence_row")
            row = _canonical_row(raw_row)
            if row is None or not _row_matches_call(row, name, arguments, scope):
                return _ungraded(response, "evidence_row_outside_scope")
            rows.append(row)
        if not _call_rows_are_complete(name, arguments, rows, scope):
            return _ungraded(response, "incomplete_successful_evidence")
        plan = _actual_plan(name, arguments, rows, scope)
        if not all(plan.get(key) for key in ("metric_ids", "entity_ids", "periods")):
            return _ungraded(response, "invalid_evidence_plan")
        evidence.append((plan, rows, name))

    if not evidence or not any(rows for _, rows, _ in evidence):
        return _ungraded(response, "no_successful_row_evidence")

    segments = {plan.get("filters", {}).get("segment") for plan, _, _ in evidence}
    if len(segments) > 1:
        return _ungraded(response, "mixed_segment_scope")
    plan = {
        "metric_ids": _ordered_union(item[0]["metric_ids"] for item in evidence),
        "entity_ids": _ordered_union(item[0]["entity_ids"] for item in evidence),
        "periods": _ordered_union(item[0]["periods"] for item in evidence),
        "operation": "query",
    }
    segment = next(iter(segments))
    if segment is not None:
        plan.update({"dimensions": ["segment"], "filters": {"segment": segment}})

    unique: dict[tuple[Any, ...], dict[str, Any]] = {}
    for _, rows, _ in evidence:
        for row in rows:
            key = (row["metric_id"], row["entity_id"], row["period"], row.get("segment"))
            prior = unique.get(key)
            if prior is not None and prior != row:
                return _ungraded(response, "conflicting_duplicate_evidence")
            unique[key] = row
    if any((row["availability"] == "missing") != (row["value"] is None) for row in unique.values()):
        return _ungraded(response, "invalid_successful_evidence")
    # A single fixture plan cannot describe disjoint query rectangles. Series
    # contribute only periods actually returned, so this never invents bounds.
    expected_keys = set(product(plan["metric_ids"], plan["entity_ids"], plan["periods"], [segment]))
    if set(unique) != expected_keys:
        return _ungraded(response, "irreconcilable_evidence_scope")
    return {
        "status": "supported",
        "plan": plan,
        "rows": list(unique.values()),
        "response": response,
        "data_version": expected_versions["data_version"],
        "semantic_version": expected_versions["semantic_version"],
        "evidence_scope": scope,
        "evidence_tools": [name for _, _, name in evidence],
    }


def _ungraded(response: str, reason: str) -> dict[str, Any]:
    return {"status": "ungraded", "plan": None, "rows": [], "response": response, "not_scored_reason": reason}


def _canonical_row(row: dict[str, Any]) -> dict[str, Any] | None:
    required = ("metric_id", "entity_id", "period", "value", "unit", "availability", "source_references")
    if not all(key in row for key in required):
        return None
    if not isinstance(row["source_references"], list) or not row["source_references"]:
        return None
    if not isinstance(row["unit"], str) or not row["unit"]:
        return None
    if row["availability"] not in {"available", "missing"}:
        return None
    if not all(isinstance(row[key], str) and row[key] for key in ("metric_id", "entity_id", "period")):
        return None
    value = row["value"]
    if value is not None and (isinstance(value, bool) or not isinstance(value, (int, float))):
        return None
    if any(
        not isinstance(ref, dict)
        or not isinstance(ref.get("url"), str)
        or not ref["url"].startswith("https://")
        or not isinstance(ref.get("label"), str)
        or not ref["label"]
        for ref in row["source_references"]
    ):
        return None
    if "segment" in row and (not isinstance(row["segment"], str) or not row["segment"]):
        return None
    return {key: row[key] for key in _ROW_FIELDS if key in row}


def _resolved_segment(arguments: dict[str, Any], scope: dict[str, Any]) -> str | None:
    explicit = arguments.get("segment")
    if explicit is not None:
        return explicit if isinstance(explicit, str) else None
    filters = scope.get("filters")
    if isinstance(filters, dict) and isinstance(filters.get("segment"), str):
        return filters["segment"]
    return None


def _segment_scope_is_valid(arguments: dict[str, Any], scope: dict[str, Any]) -> bool:
    explicit = arguments.get("segment")
    if explicit is not None and (not isinstance(explicit, str) or explicit not in _SEGMENTS):
        return False
    filters = scope.get("filters")
    if isinstance(filters, dict) and filters.get("segment") is not None:
        segment = filters["segment"]
        return isinstance(segment, str) and segment in _SEGMENTS
    return True


def _row_matches_call(
    row: dict[str, Any], name: str, arguments: dict[str, Any], scope: dict[str, Any]
) -> bool:
    if name == "query_metrics":
        metrics, entities, periods = (
            arguments.get("metric_ids"), arguments.get("entity_ids"), arguments.get("periods")
        )
    else:
        metrics, entities = [arguments.get("metric_id")], [arguments.get("entity_id")]
        periods = arguments.get("periods") if name == "compare_metrics" else None
    if not all(isinstance(items, list) and row[field] in items for items, field in (
        (metrics, "metric_id"), (entities, "entity_id")
    )):
        return False
    if periods is not None and (not isinstance(periods, list) or row["period"] not in periods):
        return False
    if name == "get_time_series":
        start, end = arguments.get("start_period"), arguments.get("end_period")
        if not isinstance(start, str) or not isinstance(end, str) or not start <= row["period"] <= end:
            return False
    segment = _resolved_segment(arguments, scope)
    return row.get("segment") == segment


def _actual_plan(
    name: str, arguments: dict[str, Any], rows: list[dict[str, Any]], scope: dict[str, Any]
) -> dict[str, Any]:
    if name == "query_metrics":
        metric_ids, entity_ids, periods = (
            arguments.get("metric_ids"), arguments.get("entity_ids"), arguments.get("periods")
        )
    elif name == "compare_metrics":
        metric_ids, entity_ids, periods = (
            [arguments.get("metric_id")], [arguments.get("entity_id")], arguments.get("periods")
        )
    else:
        metric_ids, entity_ids = [arguments.get("metric_id")], [arguments.get("entity_id")]
        periods = [row["period"] for row in rows]
    plan = {
        "metric_ids": _string_list(metric_ids),
        "entity_ids": _string_list(entity_ids),
        "periods": _string_list(periods),
        "operation": "query",
    }
    segment = _resolved_segment(arguments, scope)
    if isinstance(segment, str):
        plan.update({"dimensions": ["segment"], "filters": {"segment": segment}})
    return plan


def _call_rows_are_complete(
    name: str, arguments: dict[str, Any], rows: list[dict[str, Any]], scope: dict[str, Any]
) -> bool:
    if name == "get_time_series":
        # The selected periods come from the returned public series. An empty
        # success cannot establish what the range contained.
        return bool(rows)
    if name == "query_metrics":
        metrics, entities, periods = (
            arguments.get("metric_ids"), arguments.get("entity_ids"), arguments.get("periods")
        )
    else:
        metrics, entities, periods = (
            [arguments.get("metric_id")], [arguments.get("entity_id")], arguments.get("periods")
        )
    if not all(isinstance(values, list) and values and all(isinstance(v, str) for v in values)
               for values in (metrics, entities, periods)):
        return False
    segment = _resolved_segment(arguments, scope)
    expected = {
        (metric, entity, period, segment)
        for metric in metrics
        for entity in entities
        for period in periods
    }
    actual = {
        (row["metric_id"], row["entity_id"], row["period"], row.get("segment"))
        for row in rows
    }
    return actual == expected


def _ordered_union(values: Any) -> list[str]:
    result: list[str] = []
    for group in values:
        for value in group:
            if value not in result:
                result.append(value)
    return result


def _string_list(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [item for item in value if isinstance(item, str)]
    return []


__all__ = ["observation_from_tool_calls"]
