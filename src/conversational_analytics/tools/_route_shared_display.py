"""Presentation metadata for shared-route tool tables."""

from __future__ import annotations

import json
from typing import Any

MAX_SHARED_ROUTE_RESULT_BYTES = 15_000


def build_shared_display(
    rows: list[dict[str, Any]],
    entity_ids: list[str],
    labels: dict[str, str],
    unit: str,
    coverage: dict[str, dict[str, Any]],
    carrier_metadata: dict[str, dict[str, Any]],
) -> tuple[list[dict[str, str]], list[dict[str, Any]]]:
    """Keep comparability and each carrier's provenance beside displayed values."""
    columns = [
        {"key": "market_key", "label": "Ruta"},
        {"key": "combined_value", "label": "Total combinado", "unit": unit},
        {"key": "value_kind", "label": "Tipo de valor"},
    ]
    for entity_id in entity_ids:
        columns.extend(
            [
                {"key": f"{entity_id}_value", "label": labels[entity_id], "unit": unit},
                {"key": f"{entity_id}_value_kind", "label": f"Tipo · {labels[entity_id]}"},
                {"key": f"{entity_id}_source_label", "label": f"Fuente · {labels[entity_id]}"},
            ]
        )
    columns.extend(
        [
            {"key": "comparable", "label": "Comparable"},
            {"key": "comparability_reason", "label": "Motivo"},
            {"key": "coverage_summary", "label": "Cobertura por aerolínea"},
        ]
    )
    display_rows = []
    for row in rows:
        display_row = {
            "market_key": row["market_key"],
            "combined_value": row["combined_value"],
            "value_kind": row["value_kind"],
            "comparable": row["comparable"],
            "comparability_reason": "; ".join(row["comparability_reason"]) or None,
            "coverage_summary": "; ".join(
                f"{_coverage_label(entity_id)} "
                f"{len(coverage[entity_id]['observed_months'])}/"
                f"{len(coverage[entity_id]['expected_months'])}"
                for entity_id in entity_ids
            ),
        }
        for entity_id, carrier in row["carriers"].items():
            display_row[f"{entity_id}_value"] = carrier["value"]
            display_row[f"{entity_id}_value_kind"] = carrier["value_kind"]
            label = carrier_metadata[entity_id]["source_labels"].get(carrier.get("source_ref"), "")
            display_row[f"{entity_id}_source_label"] = _compact_source_label(label)
        display_rows.append(display_row)
    return columns, display_rows


def bound_shared_result(
    result: dict[str, Any],
    entity_ids: list[str],
    labels: dict[str, str],
    unit: str,
    available_count: int,
) -> dict[str, Any]:
    """Keep the advertised route query within the provider's result budget."""
    rows = result["rows"]
    result["truncation_reason"] = None
    title_base = result["display"]["title"]
    while True:
        columns, display_rows = build_shared_display(
            rows, entity_ids, labels, unit, result["coverage"], result["carrier_metadata"]
        )
        result["display"]["columns"] = columns
        result["display"]["rows"] = display_rows
        kinds = {row["value_kind"] for row in rows}
        result["display"]["value_kind"] = (
            next(iter(kinds)) if len(kinds) == 1 else "mixed" if kinds else "missing"
        )
        result["row_count"] = len(rows)
        result["applied_top_n"] = len(rows)
        result["available_route_count"] = available_count
        result["truncated"] = len(rows) < available_count
        result["display"]["title"] = f"{title_base} · {len(rows)} de {available_count} mostradas"
        encoded = json.dumps(result, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
        if len(encoded.encode("utf-8")) <= MAX_SHARED_ROUTE_RESULT_BYTES:
            return result
        if not rows:
            raise ValueError("shared-route metadata exceeds the tool result budget")
        rows.pop()
        result["truncation_reason"] = "tool_result_size_limit"


def _coverage_label(entity_id: str) -> str:
    return {
        "AEROMEXICO_GROUP": "AM",
        "VOLARIS": "Volaris",
        "VIVA_AEROBUS": "Viva",
    }.get(entity_id, "Industria")


def _compact_source_label(label: str) -> str:
    if label.startswith("Estados Unidos · "):
        return label.removeprefix("Estados Unidos · ")
    if label.startswith("AFAC + AeroDataBox"):
        return "AFAC + AeroDataBox"
    if label.startswith("AICM"):
        return "AICM · programado"
    if label.startswith("OMA"):
        return "OMA · rutas"
    return label
