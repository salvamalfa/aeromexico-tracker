"""Versioned schemas for the base public chat tools."""

from __future__ import annotations

from typing import Any

from src.conversational_analytics.semantic.plan import SEGMENTS


def _schema(properties: dict[str, Any], required: list[str]) -> dict[str, Any]:
    return {"type": "object", "properties": properties, "required": required, "additionalProperties": False}


def make_base_tool_specs() -> list[dict[str, Any]]:
    qstr = {"type": "string", "minLength": 1}
    arr = {"type": "array", "items": qstr, "minItems": 1, "maxItems": 32}
    specs = [
        {
            "type": "function",
            "name": "get_data_catalog",
            "description": (
                "Catálogo público con IDs, alias, unidades, granos, cobertura y periodos disponibles. "
                "Incluye periodos exportados por segmento para consultas de rutas. "
                "Usa métricas habilitadas; el inventario no habilitado no es consultable."
            ),
            "parameters": _schema({}, []),
        },
        {
            "type": "function",
            "name": "get_metric_definition",
            "description": (
                "Definición, fuente, unidad, cobertura y límites de un ID exacto. "
                "Consulta la ficha cuando dos conceptos o denominadores puedan confundirse."
            ),
            "parameters": _schema({"metric_id": qstr}, ["metric_id"]),
        },
        {
            "type": "function",
            "name": "query_metrics",
            "description": (
                "Consulta exacta por IDs publicados de métrica, entidad y periodo. "
                "No sustituye una serie cercana; verifica las filas y su disponibilidad."
            ),
            "parameters": _schema(
                {
                    "metric_ids": arr,
                    "entity_ids": {"type": "array", "items": qstr, "minItems": 1, "maxItems": 4},
                    "periods": arr,
                    "segment": {"type": "string", "enum": sorted(SEGMENTS)},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 20},
                },
                ["metric_ids", "entity_ids", "periods"],
            ),
        },
        {
            "type": "function",
            "name": "compare_metrics",
            "description": (
                "Compara dos periodos solicitados para la misma métrica, entidad y fuente; "
                "separa delta nativo, puntos porcentuales y cambio relativo."
            ),
            "parameters": _schema(
                {
                    "metric_id": qstr,
                    "entity_id": qstr,
                    "periods": {"type": "array", "items": qstr, "minItems": 2, "maxItems": 2},
                    "segment": {"type": "string", "enum": sorted(SEGMENTS)},
                    "data_version": qstr,
                    "semantic_version": qstr,
                },
                ["metric_id", "entity_id", "periods"],
            ),
        },
        {
            "type": "function",
            "name": "get_time_series",
            "description": (
                "Serie inclusiva y ordenada dentro del rango publicado solicitado. Si excede "
                "el límite de filas, devuelve los periodos más recientes e indica cuántos omitió."
            ),
            "parameters": _schema(
                {
                    "metric_id": qstr,
                    "entity_id": qstr,
                    "start_period": qstr,
                    "end_period": qstr,
                    "segment": {"type": "string", "enum": sorted(SEGMENTS)},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 20},
                },
                ["metric_id", "entity_id", "start_period", "end_period"],
            ),
        },
        {
            "type": "function",
            "name": "get_source_references",
            "description": ("Referencias públicas permitidas para los IDs exactos de métricas consultadas."),
            "parameters": _schema({"metric_ids": {"type": "array", "items": qstr, "maxItems": 10}}, []),
        },
        {
            "type": "function",
            "name": "get_dashboard_context",
            "description": (
                "Devuelve únicamente contexto visible del dashboard después de validar sus claves y valores."
            ),
            "parameters": _schema({}, []),
        },
    ]
    return specs
