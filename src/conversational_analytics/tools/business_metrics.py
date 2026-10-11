"""Business metric aggregations over the validated public Snapshot.

Financial totals require a separately published payload and a receipt whose
hashes match the exact candidate definitions and proposal. Aggregations are
deterministic and require complete calendar quarters.
"""

from __future__ import annotations

import json
import math
import re
from typing import Any, Iterable

from src.conversational_analytics.data.snapshot import Snapshot

_PERIOD_RE = re.compile(r"^(\d{4})(?:Q([1-4])|H([12]))?$")
_PROPOSAL_IDS = {"total_revenue", "operating_costs", "fuel_expense", "operating_income"}
_ENTITY_IDS = {"AEROMEXICO", "VOLARIS", "VIVA_AEROBUS", "INDUSTRY"}
_WEIGHTED_RATIO_IDS = {"rask_cents_per_km", "cask_cents_per_km", "load_factor"}
BUSINESS_METRIC_TOOL_NAMES = ("query_business_metrics", "get_business_metric_definition")


def metric_proposals() -> dict[str, Any]:
    """Return the versioned glossary, source inventory, and closed candidates."""
    from pathlib import Path

    root = Path(__file__).resolve().parents[3]
    return json.loads((root / "config/chat/metrics-candidates.json").read_text(encoding="utf-8"))


def business_metric_tool_specs() -> list[dict[str, Any]]:
    """Return tool declarations for a registry to opt into after owner review."""
    return [
        {
            "type": "function",
            "name": "query_business_metrics",
            "description": (
                "Consulta un monto financiero candidato solo si está aprobado y publicado; "
                "también suma pasajeros reportados sobre trimestres completos."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "metric_id": {"type": "string", "minLength": 1},
                    "entity_id": {"type": "string", "enum": sorted(_ENTITY_IDS)},
                    "period": {
                        "type": "string",
                        "pattern": r"^\d{4}(?:Q[1-4]|H[12])?$",
                        "description": "Trimestre YYYYQn, semestre calendario YYYYH1/YYYH2, o año YYYY.",
                    },
                },
                "required": ["metric_id", "entity_id", "period"],
                "additionalProperties": False,
            },
        },
        {
            "type": "function",
            "name": "get_business_metric_definition",
            "description": (
                "Devuelve la propuesta de definición, unidad, cobertura y gate de un candidato F2.3."
            ),
            "parameters": {
                "type": "object",
                "properties": {"metric_id": {"type": "string", "minLength": 1}},
                "required": ["metric_id"],
                "additionalProperties": False,
            },
        },
    ]


def get_business_metric_definition(metric_id: str, snapshot: Snapshot | None = None) -> dict[str, Any]:
    """Return a candidate definition without changing its approval state."""
    catalog = metric_proposals()
    try:
        definition = next(item for item in catalog["candidate_metrics"] if item["id"] == metric_id)
    except StopIteration as exc:
        raise ValueError(f"Definición candidata desconocida: {metric_id}") from exc
    is_approved = False
    if snapshot is not None and metric_id in _PROPOSAL_IDS:
        try:
            published = snapshot.payload("data/v1/business_metrics.json")
            is_approved = metric_id in published.get("metadata", {}).get("metric_ids", [])
        except ValueError:
            pass
    result = dict(definition)
    if is_approved:
        result["approval_status"] = "owner_approved_published"
    return {
        "metric": result,
        "approval_gate": "open" if is_approved else catalog["metadata"]["activation_gate"],
        "approval_status": result["approval_status"],
        "production_enabled": is_approved,
    }


def _expected_quarters(period: str) -> list[str]:
    match = _PERIOD_RE.fullmatch(period) if isinstance(period, str) else None
    if not match:
        raise ValueError("period debe tener formato YYYYQn, YYYYH1, YYYYH2 o YYYY")
    year, quarter, half = match.groups()
    if quarter:
        return [f"{year}Q{quarter}"]
    if half:
        return [f"{year}Q{1 if half == '1' else 3}", f"{year}Q{2 if half == '1' else 4}"]
    return [f"{year}Q{q}" for q in range(1, 5)]


def aggregate_quarters(
    records: Iterable[dict[str, Any]],
    period: str,
    *,
    value_key: str = "value",
    period_key: str = "period_id",
) -> dict[str, Any]:
    """Sum a quarter-grain flow only when every constituent quarter is present.

    Rows with a missing/null value remain missing, and an explicitly reported
    zero remains a valid value. Annual and half-year aggregates never imply
    completeness from row count alone: each expected quarter ID must exist with
    a numeric value.
    """
    expected = _expected_quarters(period)
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in records:
        if isinstance(row, dict) and isinstance(row.get(period_key), str):
            grouped.setdefault(row[period_key], []).append(row)
    values: dict[str, float] = {}
    missing_periods = []
    conflicting_periods = []
    for quarter in expected:
        quarter_rows = grouped.get(quarter, [])
        valid = [
            row[value_key]
            for row in quarter_rows
            if isinstance(row.get(value_key), (int, float))
            and not isinstance(row.get(value_key), bool)
            and math.isfinite(float(row[value_key]))
        ]
        if not quarter_rows or len(valid) != len(quarter_rows):
            missing_periods.append(quarter)
        elif len({float(value) for value in valid}) > 1:
            conflicting_periods.append(quarter)
        else:
            values[quarter] = float(valid[0])
    if missing_periods:
        return {
            "period": period,
            "value": None,
            "availability": "incomplete",
            "expected_periods": expected,
            "included_periods": [q for q in expected if q in values],
            "missing_periods": missing_periods,
            "conflicting_periods": conflicting_periods,
        }
    if conflicting_periods:
        return {
            "period": period,
            "value": None,
            "availability": "source_conflict",
            "expected_periods": expected,
            "included_periods": [q for q in expected if q in values],
            "missing_periods": [],
            "conflicting_periods": conflicting_periods,
        }
    return {
        "period": period,
        "value": math.fsum(values[q] for q in expected),
        "availability": "available",
        "expected_periods": expected,
        "included_periods": expected,
        "missing_periods": [],
        "conflicting_periods": [],
    }


def aggregate_weighted_ratio(
    records: Iterable[dict[str, Any]],
    period: str,
    *,
    value_key: str = "value",
    weight_key: str = "weight",
    period_key: str = "period_id",
) -> dict[str, Any]:
    """Aggregate a ratio using its published denominator as weight.

    All expected periods need a finite ratio and positive finite denominator.
    This computes ``sum(ratio * denominator) / sum(denominator)`` and never
    takes a simple mean of percentages or unit ratios.
    """
    expected = _expected_quarters(period)
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in records:
        if isinstance(row, dict) and isinstance(row.get(period_key), str):
            grouped.setdefault(row[period_key], []).append(row)
    values: dict[str, tuple[float, float]] = {}
    missing_periods = []
    conflicting_periods = []
    for quarter in expected:
        quarter_rows = grouped.get(quarter, [])
        pairs = []
        for row in quarter_rows:
            value, weight = row.get(value_key), row.get(weight_key)
            if (
                not isinstance(value, (int, float))
                or isinstance(value, bool)
                or not math.isfinite(float(value))
                or not isinstance(weight, (int, float))
                or isinstance(weight, bool)
                or not math.isfinite(float(weight))
                or float(weight) <= 0
            ):
                continue
            pairs.append((float(value), float(weight)))
        if not quarter_rows or len(pairs) != len(quarter_rows):
            missing_periods.append(quarter)
        elif len(set(pairs)) > 1:
            conflicting_periods.append(quarter)
        else:
            values[quarter] = pairs[0]
    included = [quarter for quarter in expected if quarter in values]
    if missing_periods or conflicting_periods:
        return {
            "period": period,
            "value": None,
            "availability": "incomplete" if missing_periods else "source_conflict",
            "expected_periods": expected,
            "included_periods": included,
            "missing_periods": missing_periods,
            "conflicting_periods": conflicting_periods,
            "numerator_sum": None,
            "denominator_sum": None,
        }
    numerator_sum = math.fsum(values[quarter][0] * values[quarter][1] for quarter in expected)
    denominator_sum = math.fsum(values[quarter][1] for quarter in expected)
    return {
        "period": period,
        "value": numerator_sum / denominator_sum,
        "availability": "available",
        "expected_periods": expected,
        "included_periods": expected,
        "missing_periods": [],
        "conflicting_periods": [],
        "numerator_sum": numerator_sum,
        "denominator_sum": denominator_sum,
    }


def deterministic_query(
    snapshot: Snapshot,
    metric_id: str,
    entity_id: str,
    period: str,
) -> dict[str, Any]:
    """Query approved totals/ratios from Snapshot, or return the candidate gate closed."""
    _expected_quarters(period)  # validate even when the candidate gate is closed
    if entity_id not in _ENTITY_IDS:
        raise ValueError(f"Entidad desconocida: {entity_id}")
    if metric_id in _PROPOSAL_IDS:
        proposal = next(item for item in metric_proposals()["candidate_metrics"] if item["id"] == metric_id)
        try:
            payload = snapshot.payload("data/v1/business_metrics.json")
        except ValueError:
            payload = None
        if payload is None or metric_id not in payload.get("metadata", {}).get("metric_ids", []):
            return {
                "metric_id": metric_id,
                "entity_id": entity_id,
                "period": period,
                "value": None,
                "availability": "approval_required",
                "value_kind": "candidate_unapproved",
                "approval_gate": "closed",
                "reason": proposal["blocked_reason"],
                "source_references": [],
            }
        approved_rows = [
            {"period_id": row["period"], "value": row["value"], "availability": row["availability"]}
            for row in payload["rows"]
            if row["metric_id"] == metric_id and row["entity_id"] == entity_id
        ]
        aggregate_rows = [
            {"period_id": row["period_id"], "value": row["value"]}
            for row in approved_rows
            if row["availability"] == "available"
        ]
        aggregate = aggregate_quarters(aggregate_rows, period)
        expected = set(aggregate["expected_periods"])
        source_conflicts = sorted(
            row["period_id"]
            for row in approved_rows
            if row["period_id"] in expected and row["availability"] == "source_conflict"
        )
        if source_conflicts:
            aggregate.update(
                {"value": None, "availability": "source_conflict", "conflicting_periods": source_conflicts}
            )
        row_by_period = {
            row["period"]: row
            for row in payload["rows"]
            if row["metric_id"] == metric_id and row["entity_id"] == entity_id
        }
        used = [row_by_period[q] for q in aggregate["included_periods"] if q in row_by_period]
        cited = [row_by_period[q] for q in aggregate["expected_periods"] if q in row_by_period]
        source_refs_by_key = {}
        for row in cited:
            for ref in row["source_references"]:
                source_refs_by_key[
                    (ref["url"], ref["sha256"], ref["source_system"], ref["member"], ref["label"])
                ] = ref
        quarter_source = [source for row in used for source in row["quarter_sources"]]
        return {
            "metric_id": metric_id,
            "entity_id": entity_id,
            **aggregate,
            "unit": "USD",
            "value_kind": "owner_approved_reported_quarter_sum"
            if len(aggregate["expected_periods"]) > 1
            else "owner_approved_reported",
            "approval_gate": "open",
            "currency_as_reported": sorted(
                {currency for row in used for currency in row["currency_as_reported"]}
            ),
            "any_preliminary": any(source["is_preliminary"] for source in quarter_source),
            "fiscal_period_ids": sorted(
                {period_id for source in quarter_source for period_id in [source["fiscal_period_id"]]}
            ),
            "source_references": [
                source_refs_by_key[key]
                for key in sorted(
                    source_refs_by_key, key=lambda value: tuple(str(part or "") for part in value)
                )
            ],
            "quarter_sources": quarter_source,
        }
    if metric_id in _WEIGHTED_RATIO_IDS:
        doc = snapshot.payload("data/v1/executive.json")
        entity = doc.get("entities", {}).get(entity_id)
        rows = entity.get("records", []) if entity else []
        field = metric_id
        ratio_rows = [
            {
                "period_id": row.get("period_id"),
                "value": row.get(field),
                "weight": row.get("ask_km"),
                "basis": row.get("load_factor_basis") if metric_id == "load_factor" else "ASK-km",
            }
            for row in rows
        ]
        aggregate = aggregate_weighted_ratio(ratio_rows, period)
        expected = set(aggregate["expected_periods"])
        basis_by_period = {
            row.get("period_id"): row.get("basis") for row in ratio_rows if row.get("period_id") in expected
        }
        bases = {basis for basis in basis_by_period.values() if basis}
        if metric_id == "load_factor" and len(bases) > 1:
            aggregate.update(
                {
                    "value": None,
                    "availability": "source_conflict",
                    "conflicting_periods": sorted(basis_by_period),
                }
            )
        field_unit = "percent" if metric_id == "load_factor" else "cents_usd_per_ask_km"
        return {
            "metric_id": metric_id,
            "entity_id": entity_id,
            **aggregate,
            "unit": field_unit,
            "denominator": "ask_km",
            "aggregation": "ASK-weighted mean of published quarterly ratios; requires complete quarters",
            "ratio_basis": sorted(bases),
            "value_kind": "derived_weighted_mean_of_published_quarter_ratios",
            "source_references": [
                {
                    "label": "Datos publicados del dashboard",
                    "url": "https://salvamalfa.github.io/aeromexico-tracker/data/v1/executive.json",
                }
            ],
        }
    if metric_id != "company_passengers":
        raise ValueError(f"Métrica F2.3 no disponible en este dispatcher: {metric_id}")

    doc = snapshot.payload("data/v1/executive.json")
    entity = doc.get("entities", {}).get(entity_id)
    rows = entity.get("records", []) if entity else []
    all_quarters = [{"period_id": row.get("period_id"), "value": row.get("passengers")} for row in rows]
    aggregate = aggregate_quarters(all_quarters, period)
    references = [
        {
            "label": "Datos publicados del dashboard",
            "url": "https://salvamalfa.github.io/aeromexico-tracker/data/v1/executive.json",
        }
    ]
    return {
        "metric_id": metric_id,
        "entity_id": entity_id,
        **aggregate,
        "unit": "passengers",
        "value_kind": "reported"
        if len(aggregate["expected_periods"]) == 1
        else "derived_sum_of_reported_quarters",
        "quality": "reported_company_series; deterministic sum of published quarters",
        "source_references": references,
    }


def dispatch_business_metric_tool(
    snapshot: Snapshot,
    tool_name: str,
    arguments: dict[str, Any],
) -> dict[str, Any]:
    """Small adapter for a central registry to call F2.3 tools by name."""
    if not isinstance(arguments, dict):
        raise ValueError("arguments debe ser un objeto")
    if tool_name == "get_business_metric_definition":
        if set(arguments) != {"metric_id"}:
            raise ValueError("get_business_metric_definition requiere solo metric_id")
        return get_business_metric_definition(arguments["metric_id"], snapshot)
    if tool_name == "query_business_metrics":
        if set(arguments) != {"metric_id", "entity_id", "period"}:
            raise ValueError("query_business_metrics requiere metric_id, entity_id y period")
        return deterministic_query(
            snapshot, arguments["metric_id"], arguments["entity_id"], arguments["period"]
        )
    raise ValueError(f"Herramienta F2.3 desconocida: {tool_name}")


__all__ = [
    "BUSINESS_METRIC_TOOL_NAMES",
    "aggregate_quarters",
    "aggregate_weighted_ratio",
    "business_metric_tool_specs",
    "dispatch_business_metric_tool",
    "deterministic_query",
    "get_business_metric_definition",
    "metric_proposals",
]
