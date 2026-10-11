"""F2.5/F2.6 tool contracts, kept separate from the central registry for review."""

from __future__ import annotations

from typing import Any

from src.conversational_analytics.evidence_index import EvidenceIndex, EvidenceIndexError


def _object_schema(properties: dict[str, Any], required: list[str]) -> dict[str, Any]:
    return {"type": "object", "properties": properties, "required": required, "additionalProperties": False}


def evidence_tool_specs() -> list[dict[str, Any]]:
    """Return the two closed function schemas for the future approved registry."""
    query = {"type": "string", "minLength": 1, "maxLength": 240}
    optional_text = {"type": ["string", "null"], "maxLength": 100}
    limit = {"type": "integer", "minimum": 1, "maximum": 5}
    return [
        {
            "type": "function",
            "name": "search_reports",
            "description": (
                "Busca pasajes breves de reportes públicos aprobados. Devuelve empresa, periodo, página "
                "y cita; "
                "si no existe una coincidencia aprobada, devuelve cero resultados."
            ),
            "parameters": _object_schema(
                {
                    "query": query, "company": optional_text,
                    "period": {"type": ["string", "null"], "maxLength": 20}, "limit": limit,
                },
                ["query", "company", "period", "limit"],
            ),
        },
        {
            "type": "function",
            "name": "search_news",
            "description": (
                "Busca fichas breves de noticias aprobadas por fecha y empresa. Devuelve metadatos, "
                "resumen propio "
                "y enlace; nunca devuelve el artículo completo."
            ),
            "parameters": _object_schema(
                {"query": query, "start_date": {"type": ["string", "null"], "maxLength": 10},
                 "end_date": {"type": ["string", "null"], "maxLength": 10}, "company": optional_text,
                 "limit": limit}, ["query", "start_date", "end_date", "company", "limit"]
            ),
        },
    ]


def dispatch_evidence_tool(name: str, arguments: dict[str, Any], index: EvidenceIndex) -> dict[str, Any]:
    """Dispatch validated evidence tools; this adapter is ready for registry integration."""
    if not isinstance(arguments, dict):
        return {"error": "argumentos inválidos"}
    try:
        if name == "search_reports":
            if set(arguments) != {"query", "company", "period", "limit"}:
                return {"error": "argumentos inválidos"}
            return index.search_reports(
                arguments["query"], arguments["company"], arguments["period"], arguments["limit"]
            )
        if name == "search_news":
            if set(arguments) != {"query", "start_date", "end_date", "company", "limit"}:
                return {"error": "argumentos inválidos"}
            return index.search_news(
                arguments["query"], arguments["start_date"], arguments["end_date"], arguments["company"],
                arguments["limit"],
            )
    except EvidenceIndexError as exc:
        return {"error": str(exc)}
    return {"error": "herramienta de evidencia desconocida"}
