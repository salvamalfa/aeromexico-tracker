"""Normalize successful semantic-tool evidence for the fixture verifier.

The canonical plan describes actual rows returned by the tool. Compare and
time-series plans retain every observed period, so overbroad requests remain
visible to strict grading. The raw operation and arguments remain in the
private tool trace. No expected values or rows are synthesized.
"""

from __future__ import annotations

from typing import Any

_SUPPORTED_TOOLS = {"query_metrics", "compare_metrics", "get_time_series"}
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


def observation_from_tool_calls(tool_calls: list[dict[str, Any]], response: str) -> dict[str, Any]:
    """Build verifier input using successful query, compare, or series rows.

    Query plans are taken from call arguments so incorrect plans remain
    detectable. Compare and series plans use their actual returned periods.
    The caller retains the full raw trace separately.
    """
    candidate = next(
        (
            call
            for call in reversed(tool_calls)
            if call.get("name") in _SUPPORTED_TOOLS
            and isinstance(call.get("result"), dict)
            and "error" not in call["result"]
            and isinstance(call["result"].get("rows"), list)
        ),
        None,
    )
    if candidate is None:
        return {"status": "ungraded", "plan": None, "rows": [], "response": response}

    name = candidate["name"]
    arguments = candidate.get("arguments")
    result = candidate["result"]
    if not isinstance(arguments, dict):
        return {"status": "ungraded", "plan": None, "rows": [], "response": response}
    rows = [_canonical_row(row) for row in result["rows"] if isinstance(row, dict)]
    rows = [row for row in rows if row is not None]
    if not rows:
        return {"status": "ungraded", "plan": None, "rows": [], "response": response}

    plan = _actual_plan(name, arguments, rows)
    return {"status": "supported", "plan": plan, "rows": rows, "response": response}


def _canonical_row(row: dict[str, Any]) -> dict[str, Any] | None:
    """Copy only verifier fields from one actual registry row."""
    if not all(key in row for key in ("metric_id", "entity_id", "period")):
        return None
    return {key: row[key] for key in _ROW_FIELDS if key in row}


def _actual_plan(name: str, arguments: dict[str, Any], rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Normalize tool arguments into the shared base-query plan vocabulary."""
    if name == "query_metrics":
        metric_ids = arguments.get("metric_ids")
        entity_ids = arguments.get("entity_ids")
        periods = arguments.get("periods")
    elif name == "compare_metrics":
        metric_ids = [arguments.get("metric_id")]
        entity_ids = [arguments.get("entity_id")]
        periods = arguments.get("periods")
    else:
        metric_ids = [arguments.get("metric_id")]
        entity_ids = [arguments.get("entity_id")]
        periods = [row["period"] for row in rows]

    plan = {
        "metric_ids": _string_list(metric_ids),
        "entity_ids": _string_list(entity_ids),
        "periods": _string_list(periods),
        "operation": "query",
    }
    segment = arguments.get("segment")
    if segment is None:
        row_segments = {row.get("segment") for row in rows if row.get("segment") is not None}
        if len(row_segments) == 1:
            segment = next(iter(row_segments))
    if isinstance(segment, str):
        plan.update({"dimensions": ["segment"], "filters": {"segment": segment}})
    return plan


def _string_list(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [item for item in value if isinstance(item, str)]
    return []


__all__ = ["observation_from_tool_calls"]
