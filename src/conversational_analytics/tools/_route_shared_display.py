"""Presentation metadata for shared-route tool tables."""

from __future__ import annotations

import copy
from typing import Any


def build_shared_display(
    rows: list[dict[str, Any]], entity_ids: list[str], labels: dict[str, str], unit: str
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
            "carrier_coverage": copy.deepcopy(row["coverage"]),
            "coverage_summary": "; ".join(
                f"{labels[entity_id]}: "
                f"{len(row['coverage'][entity_id]['observed_months'])}/"
                f"{len(row['coverage'][entity_id]['expected_months'])} meses"
                for entity_id in entity_ids
            ),
        }
        for entity_id, carrier in row["carriers"].items():
            display_row[f"{entity_id}_value"] = carrier["value"]
            display_row[f"{entity_id}_value_kind"] = carrier["value_kind"]
            display_row[f"{entity_id}_source_label"] = carrier["source_label"]
        display_rows.append(display_row)
    return columns, display_rows
