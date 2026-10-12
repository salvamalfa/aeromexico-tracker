"""Bound single-entity route query results for tool transport."""

from __future__ import annotations

import json
from typing import Any

MAX_ROUTE_QUERY_RESULT_BYTES = 15_000
MAX_PRESENTED_ROUTE_QUERY_RESULT_BYTES = 15_652


def bound_route_query_result(
    result: dict[str, Any], available_count: int, requested_top_n: int
) -> dict[str, Any]:
    """Trim rows and their server display together while preserving result metadata."""
    rows = result["rows"]
    result["requested_top_n"] = requested_top_n
    result["truncation_reason"] = None
    title_base = result["display"]["title"]
    while True:
        result["row_count"] = len(rows)
        result["applied_top_n"] = len(rows)
        result["available_route_count"] = available_count
        result["truncated"] = len(rows) < available_count
        result["display"]["rows"] = [
            {
                key: row[key]
                for key in ("market_key", "value", "value_kind", "metric_source_label")
            }
            | (
                {
                    "comparison_value": row["comparison"]["value"],
                    "comparison_value_kind": row["comparison"]["value_kind"],
                    "comparison_available": "Sí" if row["comparison"]["available"] else "No",
                    "comparison_reason": row["comparison"]["reason"],
                    "absolute_change": row["comparison"]["absolute_change"],
                    "relative_change_percent": row["comparison"]["relative_change_percent"],
                }
                if row.get("comparison")
                else {}
            )
            for row in rows
        ]
        result["display"]["title"] = f"{title_base} · {len(rows)} de {available_count} mostradas"
        encoded = json.dumps(result, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
        presented = {**result, "displays": [result["display"]]}
        presented_encoded = json.dumps(
            presented, ensure_ascii=False, allow_nan=False, separators=(",", ":")
        )
        if (
            len(encoded.encode("utf-8")) <= MAX_ROUTE_QUERY_RESULT_BYTES
            and len(presented_encoded.encode("utf-8")) <= MAX_PRESENTED_ROUTE_QUERY_RESULT_BYTES
        ):
            return result
        if not rows:
            raise ValueError("route-query metadata exceeds the tool result budget")
        rows.pop()
        result["truncation_reason"] = "tool_result_size_limit"
