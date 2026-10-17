"""Comparable route metrics require their own dated operator/direction support."""

from __future__ import annotations

from src.conversational_analytics.tools._route_contract import coverage
from src.conversational_analytics.tools._route_provenance import metric_source_label
from src.web_export.route_support import route_metric_support_reason


def comparability_reason(
    current,
    previous,
    route,
    previous_route,
    value,
    previous_value,
    current_kind,
    previous_kind,
    comparison_period,
    metric,
    entity_id,
):
    if previous is None:
        return "El periodo comparativo no está publicado"
    if not coverage(current)["complete"] or not coverage(previous)["complete"]:
        return "La cobertura de uno o ambos periodos es parcial"
    if previous_route is None:
        return "La ruta no aparece en ambos periodos; no se asume valor cero"
    if value is None or previous_value is None:
        return "Falta el valor de la ruta en al menos un periodo"
    if current_kind != previous_kind:
        return "Cambió el tipo de valor (observado, estimado o programado)"
    if metric_source_label(current, route, metric, entity_id) != metric_source_label(
        previous, previous_route, metric, entity_id
    ):
        return "Cambió la fuente de la ruta"
    support_reason = route_metric_support_reason(current, previous, route, previous_route, metric)
    return support_reason or f"No hay comparación válida contra {comparison_period}"
