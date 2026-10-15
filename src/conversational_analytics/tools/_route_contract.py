"""Published route-tool contract, validation and snapshot path mapping."""

from __future__ import annotations

import copy
import hashlib
import json
import re
from typing import Any
from urllib.parse import quote, urlsplit

from src.conversational_analytics.semantic.plan import PlanValidationError

TOOL_NAMES = ("query_routes", "find_shared_routes")
ENTITY_IDS = ("AEROMEXICO_GROUP", "VOLARIS", "VIVA_AEROBUS", "INDUSTRY")
SEGMENTS = ("domestic", "international")
METRICS = ("passengers", "seats", "departures", "load_factor")
PERIOD_RE = re.compile(r"^\d{4}(?:M(?:0[1-9]|1[0-2])|Q[1-4])$")
MAX_TOP_N = 20
AEROMEXICO_SCOPE = (
    "AEROMEXICO_GROUP es la selección del dashboard: el histórico estimado puede agregar "
    "Aerovías y Connect; cada fuente oficial conserva su operador/reportante y su cobertura, "
    "que puede ser parcial."
)
ENTITY_LABELS = {
    "AEROMEXICO_GROUP": "Grupo Aeroméxico · cobertura según fuente",
    "VOLARIS": "Volaris",
    "VIVA_AEROBUS": "Viva Aerobus",
    "INDUSTRY": "Industria",
}
AIRLINE_IDS = ("AEROMEXICO_GROUP", "VOLARIS", "VIVA_AEROBUS")
METRIC_LABELS = {
    "passengers": ("Pasajeros por tramo", "pasajeros"),
    "seats": ("Asientos", "asientos"),
    "departures": ("Salidas", "vuelos"),
    "load_factor": ("Factor de ocupación", "%"),
}
SOURCE_HOSTS = {"gob.mx", "www.gob.mx", "salvamalfa.github.io"}


def _schema(properties: dict[str, Any], required: list[str]) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": properties,
        "required": required,
        "additionalProperties": False,
    }


_PERIOD = {"type": "string", "pattern": PERIOD_RE.pattern}
_ENTITY = {"type": "string", "enum": list(ENTITY_IDS)}
_SEGMENT = {"type": "string", "enum": list(SEGMENTS)}
_TOP_N = {"type": "integer", "minimum": 1, "maximum": MAX_TOP_N}
ROUTE_TOOL_SPECS = [
    {
        "type": "function",
        "name": "query_routes",
        "description": (
            "Consulta rutas publicadas por tramo, con filtros de aerolínea, segmento y periodo. "
            "Ordena el top N por valor actual o por cambio frente a un periodo comparable. "
            "Las estimaciones, vuelos observados y programación se identifican por fila; "
            "faltantes no se convierten en cero. Aeroméxico se consulta como Grupo Aeroméxico."
        ),
        "parameters": _schema(
            {
                "entity_id": _ENTITY,
                "segment": _SEGMENT,
                "period": _PERIOD,
                "metric": {"type": "string", "enum": list(METRICS)},
                "top_n": _TOP_N,
                "order_by": {"type": "string", "enum": ["value", "absolute_change", "relative_change"]},
                "comparison_period": _PERIOD,
                "origin_iata": {"type": "string", "pattern": "^[A-Z]{3}$"},
                "destination_iata": {"type": "string", "pattern": "^[A-Z]{3}$"},
            },
            ["entity_id", "segment", "period", "metric"],
        ),
    },
    {
        "type": "function",
        "name": "find_shared_routes",
        "description": (
            "Encuentra rutas publicadas que comparten al menos dos aerolíneas en un mismo periodo "
            "y segmento. Devuelve el valor por aerolínea, cobertura y tipo de valor. "
            "El histórico estimado puede agregar Aerovías y Connect; las observaciones "
            "oficiales conservan el alcance de su operador/reportante."
        ),
        "parameters": _schema(
            {
                "entity_ids": {
                    "type": "array",
                    "items": {"type": "string", "enum": list(AIRLINE_IDS)},
                    "minItems": 2,
                    "maxItems": 3,
                },
                "segment": _SEGMENT,
                "period": _PERIOD,
                "metric": {"type": "string", "enum": ["passengers", "seats", "departures"]},
                "top_n": _TOP_N,
            },
            ["entity_ids", "segment", "period"],
        ),
    },
]


def validate_period(value: Any, name: str) -> str:
    if not isinstance(value, str) or not PERIOD_RE.fullmatch(value):
        raise PlanValidationError(f"{name} debe ser YYYYQn o YYYYMmm")
    return value


def validate_choice(value: Any, choices: tuple[str, ...], name: str) -> str:
    if not isinstance(value, str) or value not in choices:
        raise PlanValidationError(f"{name} debe ser uno de: {', '.join(choices)}")
    return value


def validate_top_n(value: Any) -> int:
    if value is None:
        return 10
    if not isinstance(value, int) or isinstance(value, bool) or not 1 <= value <= MAX_TOP_N:
        raise PlanValidationError(f"top_n debe estar entre 1 y {MAX_TOP_N}")
    return value


def path_for(entity_id: str, segment: str, period: str) -> str:
    if segment == "domestic" and entity_id == "AEROMEXICO_GROUP":
        return f"data/v1/flights/domestic/{period}.json"
    if segment == "international" and entity_id == "AEROMEXICO_GROUP":
        return f"data/v1/flights/international/{period}.json"
    return f"data/v1/flights/entities/{entity_id}/{segment}/{period}.json"


def coverage(network: dict[str, Any]) -> dict[str, Any]:
    expected = list(network.get("expected_months") or [])
    observed = list(network.get("observed_months") or [])
    complete = bool(network.get("availability") == "complete" and expected and set(expected) <= set(observed))
    return {
        "availability": network.get("availability", "missing"),
        "expected_months": expected,
        "observed_months": observed,
        "complete": complete,
        "agent_eligible": network.get("agent_eligible"),
        "eligibility_reason": network.get("eligibility_reason"),
        "usage_scope": "published_dashboard_retrospective",
        "usage_scope_description": (
            "Consulta de datos ya publicados en el dashboard; esto no modifica ni implica "
            "elegibilidad histórica para AnalysisAgent."
        ),
        "sources": copy.deepcopy(network.get("coverage_by_source") or {}),
    }


def safe_source_url(url: Any) -> str | None:
    if not isinstance(url, str):
        return None
    try:
        parsed = urlsplit(url)
    except ValueError:
        return None
    if parsed.scheme != "https" or parsed.hostname not in SOURCE_HOSTS or parsed.username or parsed.password:
        return None
    return url


def source_references(networks: list[tuple[dict[str, Any], str]]) -> list[dict[str, str]]:
    refs = []
    for network, path in networks:
        paths = network.get("source_paths")
        if not isinstance(paths, list):
            paths = [path]
        for source_path in paths:
            period_label = (
                source_path.rsplit("/", 1)[-1].removesuffix(".json")
                if isinstance(network.get("source_paths"), list)
                else network.get("period_label", source_path.rsplit("/", 1)[-1])
            )
            refs.append(
                {
                    "label": f"Dashboard público · {period_label}",
                    "url": "https://salvamalfa.github.io/aeromexico-tracker/" + quote(source_path, safe="/"),
                }
            )
    return deduplicate_source_references(refs)


def deduplicate_source_references(refs: list[dict[str, str]]) -> list[dict[str, str]]:
    by_url: dict[str, dict[str, Any]] = {}
    for ref in refs:
        url, label = ref.get("url"), ref.get("label")
        if not isinstance(url, str) or not isinstance(label, str) or not label:
            continue
        source = by_url.setdefault(url, {"url": url, "labels": []})
        if label not in source["labels"]:
            source["labels"].append(label)
    prefix = "Dashboard público · "
    merged = []
    for url, source in by_url.items():
        labels = source["labels"]
        label = (
            prefix + " / ".join(item.removeprefix(prefix) for item in labels)
            if all(item.startswith(prefix) for item in labels)
            else " · ".join(labels)
        )
        merged.append({"url": url, "label": label})
    return merged


def build_display(
    query: dict[str, Any], rows: list[dict[str, Any]], networks: list[tuple[dict[str, Any], str]]
) -> dict[str, Any]:
    metric = query.get("metric", "passengers")
    title, unit = METRIC_LABELS[metric]
    columns = [
        {"key": "market_key", "label": "Ruta"},
        {"key": "value", "label": title, "unit": unit},
        {"key": "value_kind", "label": "Tipo de valor"},
        {"key": "metric_source_label", "label": "Fuente de la métrica"},
    ]
    if query.get("comparison_period"):
        columns.extend(
            [
                {"key": "comparison_value", "label": query["comparison_period"], "unit": unit},
                {"key": "comparison_value_kind", "label": "Tipo en periodo anterior"},
                {"key": "comparison_available", "label": "Comparación disponible"},
                {"key": "comparison_reason", "label": "Motivo"},
                {"key": "absolute_change", "label": "Cambio", "unit": unit},
                {"key": "relative_change_percent", "label": "Cambio relativo", "unit": "%"},
            ]
        )
    display_rows = []
    for row in rows:
        display_row = {
            key: row[key]
            for key in ("market_key", "value", "value_kind", "metric_source_label")
        }
        if row.get("comparison"):
            comparison = row["comparison"]
            display_row.update(
                {
                    "comparison_value": comparison["value"],
                    "comparison_value_kind": comparison["value_kind"],
                    "comparison_available": "Sí" if comparison["available"] else "No",
                    "comparison_reason": comparison["reason"],
                    "absolute_change": comparison["absolute_change"],
                    "relative_change_percent": comparison["relative_change_percent"],
                }
            )
        display_rows.append(display_row)
    kinds = {row.get("value_kind") for row in rows if row.get("value_kind")}
    value_kind = next(iter(kinds)) if len(kinds) == 1 else "mixed" if kinds else "missing"
    query_hash = display_query_hash(query)
    refs = source_references(networks)
    return {
        "display_id": f"tabla:rutas_{query_hash}",
        "kind": "table",
        "title": query.get("title", f"Rutas compartidas · {query.get('period', '')}"),
        "columns": columns,
        "rows": display_rows,
        "value_kind": value_kind,
        "source": refs[0] if refs else None,
        "sources": refs,
        "source_references": refs,
    }


def display_query_hash(query: dict[str, Any]) -> str:
    """Stable short identifier for every normalized query dimension."""
    return hashlib.sha256(
        json.dumps(query, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()[:16]
