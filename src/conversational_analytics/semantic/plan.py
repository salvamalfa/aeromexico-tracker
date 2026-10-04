"""Structured query plan and allowlist validation for semantic queries."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


class PlanValidationError(ValueError):
    pass


PERIOD_RE = re.compile(r"^(?:\d{4}Q[1-4]|\d{4}M(?:0[1-9]|1[0-2]))$")
ENTITY_IDS = {"AEROMEXICO", "VOLARIS", "VIVA_AEROBUS", "INDUSTRY", "MEXICAN_CARRIERS"}
SEGMENTS = {"total", "domestic", "international"}


@dataclass(frozen=True)
class QueryPlan:
    metric_ids: list[str]
    entity_ids: list[str]
    periods: list[str]
    operation: str = "query"
    dimensions: list[str] = field(default_factory=list)
    filters: dict[str, str] = field(default_factory=dict)
    comparison: str | None = None
    data_version: str | None = None
    semantic_version: str | None = None
    limit: int = 20


def validate_plan(
    plan: QueryPlan, catalog: dict[str, Any], data_version: str, semantic_version: str
) -> QueryPlan:
    metrics = {item["id"]: item for item in catalog["metrics"]["metrics"]}
    if (
        not isinstance(plan.metric_ids, list)
        or not plan.metric_ids
        or len(plan.metric_ids) > 10
        or any(not isinstance(mid, str) or mid not in metrics for mid in plan.metric_ids)
    ):
        raise PlanValidationError("metric_ids debe contener IDs conocidos (máximo 10)")
    if (
        not isinstance(plan.entity_ids, list)
        or not plan.entity_ids
        or len(plan.entity_ids) > 4
        or any(not isinstance(entity, str) or entity not in ENTITY_IDS for entity in plan.entity_ids)
    ):
        raise PlanValidationError("entity_ids debe contener entidades conocidas")
    if (
        not isinstance(plan.periods, list)
        or not plan.periods
        or len(plan.periods) > 32
        or any(not isinstance(p, str) or not PERIOD_RE.fullmatch(p) for p in plan.periods)
    ):
        raise PlanValidationError("periods debe contener IDs YYYYQn o YYYYMmm (máximo 32)")
    if not isinstance(plan.operation, str) or plan.operation not in {"query", "compare", "time_series"}:
        raise PlanValidationError("operación no permitida")
    if not isinstance(plan.limit, int) or isinstance(plan.limit, bool) or plan.limit < 1 or plan.limit > 20:
        raise PlanValidationError("limit debe estar entre 1 y 20")
    if (
        not isinstance(plan.dimensions, list)
        or any(not isinstance(dim, str) for dim in plan.dimensions)
        or set(plan.dimensions) - {"segment"}
    ):
        raise PlanValidationError("Dimensión desconocida o no habilitada")
    if plan.dimensions and "segment" not in plan.dimensions:
        raise PlanValidationError("Dimensión no permitida")
    if (
        not isinstance(plan.filters, dict)
        or any(not isinstance(key, str) for key in plan.filters)
        or set(plan.filters) - {"segment"}
    ):
        raise PlanValidationError("Filtro desconocido o no habilitado")
    if "segment" in plan.filters and (
        not isinstance(plan.filters["segment"], str) or plan.filters["segment"] not in SEGMENTS
    ):
        raise PlanValidationError("segment debe ser total, domestic o international")
    if plan.data_version and plan.data_version != data_version:
        raise PlanValidationError("La conversación está fijada a otra versión de datos")
    if plan.semantic_version and plan.semantic_version != semantic_version:
        raise PlanValidationError("La conversación está fijada a otra versión semántica")
    for metric_id in plan.metric_ids:
        allowed_dimensions = set(metrics[metric_id]["dimensions"])
        if set(plan.dimensions) - allowed_dimensions or set(plan.filters) - allowed_dimensions:
            raise PlanValidationError(f"Dimensión no permitida para {metric_id}")
    if plan.comparison is not None and (
        not isinstance(plan.comparison, str)
        or plan.comparison not in {"absolute", "relative", "percentage_points", "qoq", "yoy"}
    ):
        raise PlanValidationError("comparison no permitido")
    return QueryPlan(
        metric_ids=list(dict.fromkeys(plan.metric_ids)),
        entity_ids=list(dict.fromkeys(plan.entity_ids)),
        periods=list(dict.fromkeys(plan.periods)),
        operation=plan.operation,
        dimensions=list(dict.fromkeys(plan.dimensions)),
        filters=dict(plan.filters),
        comparison=plan.comparison,
        data_version=data_version,
        semantic_version=semantic_version,
        limit=plan.limit,
    )


__all__ = ["QueryPlan", "PlanValidationError", "validate_plan"]
