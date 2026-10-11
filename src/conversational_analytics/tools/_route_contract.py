"""Published route-tool contract, validation and snapshot path mapping."""

from __future__ import annotations

import copy
import re
from typing import Any
from urllib.parse import urlsplit

from src.conversational_analytics.semantic.plan import PlanValidationError

TOOL_NAMES = ("query_routes", "find_shared_routes")
ENTITY_IDS = ("AEROMEXICO_GROUP", "VOLARIS", "VIVA_AEROBUS", "INDUSTRY")
SEGMENTS = ("domestic", "international")
METRICS = ("passengers", "seats", "departures", "load_factor")
PERIOD_RE = re.compile(r"^\d{4}(?:M(?:0[1-9]|1[0-2])|Q[1-4])$")
MAX_TOP_N = 20
ENTITY_LABELS = {
    "AEROMEXICO_GROUP": "Grupo Aeroméxico (Aerovías + Connect)",
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
            "Grupo Aeroméxico suma Aerovías y Connect porque la red publicada no los separa."
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
