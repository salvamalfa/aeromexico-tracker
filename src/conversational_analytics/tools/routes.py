"""Deterministic route queries over the verified, published flight snapshot.

This module is intentionally independent from the shared tool registry. The
registry can compose ``ROUTE_TOOL_SPECS`` and delegate these two tool names to
``RouteTools`` without coupling the route query contract to metric queries.
"""

from __future__ import annotations

import copy
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
_ENTITY_LABELS = {
    "AEROMEXICO_GROUP": "Grupo Aeroméxico (Aerovías + Connect)",
    "VOLARIS": "Volaris",
    "VIVA_AEROBUS": "Viva Aerobus",
    "INDUSTRY": "Industria",
}
_AIRLINE_IDS = ("AEROMEXICO_GROUP", "VOLARIS", "VIVA_AEROBUS")
_SOURCE_HOSTS = {"gob.mx", "www.gob.mx", "salvamalfa.github.io"}
_METRIC_LABELS = {
    "passengers": ("Pasajeros por tramo", "pasajeros"),
    "seats": ("Asientos", "asientos"),
    "departures": ("Salidas", "vuelos"),
    "load_factor": ("Factor de ocupación", "%"),
}


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
                    "items": {"type": "string", "enum": list(_AIRLINE_IDS)},
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


def _validate_period(value: Any, name: str) -> str:
    if not isinstance(value, str) or not PERIOD_RE.fullmatch(value):
        raise PlanValidationError(f"{name} debe ser YYYYQn o YYYYMmm")
    return value


def _validate_choice(value: Any, choices: tuple[str, ...], name: str) -> str:
    if not isinstance(value, str) or value not in choices:
        raise PlanValidationError(f"{name} debe ser uno de: {', '.join(choices)}")
    return value


def _validate_top_n(value: Any) -> int:
    if value is None:
        return 10
    if not isinstance(value, int) or isinstance(value, bool) or not 1 <= value <= MAX_TOP_N:
        raise PlanValidationError(f"top_n debe estar entre 1 y {MAX_TOP_N}")
    return value


def _path(entity_id: str, segment: str, period: str) -> str:
    if segment == "domestic" and entity_id == "AEROMEXICO_GROUP":
        return f"data/v1/flights/domestic/{period}.json"
    if segment == "international" and entity_id == "AEROMEXICO_GROUP":
        return f"data/v1/flights/international/{period}.json"
    return f"data/v1/flights/entities/{entity_id}/{segment}/{period}.json"


def _value_kind(network: dict[str, Any], route: dict[str, Any], metric: str) -> str:
    if metric == "passengers" and route.get("passengers_estimated"):
        return "estimated"
    if metric in {"seats", "load_factor"} and route.get("capacity_estimated"):
        return "estimated"
    if metric == "load_factor" and route.get("load_factor_status") == "estimated":
        return "estimated"
    status = str(route.get("operation_status") or "").lower()
    source = str(route.get("source_label") or "").lower()
    note = str(route.get("coverage_note") or "").lower()
    if "programad" in status or "programad" in source or "programad" in note:
        return "scheduled"
    if "observed" in status or "t-100" in source or "observad" in note:
        return "observed"
    if metric in {"passengers", "seats", "departures", "load_factor"} and route.get("capacity_estimated"):
        return "estimated"
    return "observed"


def _coverage(network: dict[str, Any]) -> dict[str, Any]:
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


def _safe_source_url(url: Any) -> str | None:
    if not isinstance(url, str):
        return None
    try:
        parsed = urlsplit(url)
    except ValueError:
        return None
    if parsed.scheme != "https" or parsed.hostname not in _SOURCE_HOSTS or parsed.username or parsed.password:
        return None
    return url


class RouteTools:
    """Read-only route query adapter over a ``Snapshot``-like object."""

    def __init__(self, snapshot: Any):
        self.snapshot = snapshot

    @staticmethod
    def tool_specs() -> list[dict[str, Any]]:
        return copy.deepcopy(ROUTE_TOOL_SPECS)

    def _load(self, entity_id: str, segment: str, period: str) -> tuple[dict[str, Any] | None, str]:
        path = _path(entity_id, segment, period)
        try:
            network = self.snapshot.payload(path)
        except (ValueError, KeyError):
            return None, path
        return network, path

    def _metadata(self, query: dict[str, Any], networks: list[tuple[dict[str, Any], str]]) -> dict[str, Any]:
        refs = []
        for network, path in networks:
            published_url = "https://salvamalfa.github.io/aeromexico-tracker/" + quote(path, safe="/")
            refs.append(
                {
                    "label": f"Dashboard público, rutas: {network.get('period_label', query['period'])}",
                    "url": published_url,
                }
            )
            source_url = _safe_source_url(network.get("source_url"))
            if source_url:
                refs.append(
                    {
                        "label": ", ".join(sorted(network.get("coverage_by_source", {})))
                        or "Fuente publicada",
                        "url": source_url,
                    }
                )
        refs = list({(item["label"], item["url"]): item for item in refs}.values())
        unique_refs = list({(item["label"], item["url"]): item for item in refs}.values())
        return {
            "data_version": self.snapshot.version,
            "semantic_version": self.snapshot.semantic_version,
            "query": copy.deepcopy(query),
            "sources": unique_refs,
            "references": unique_refs,
        }

    def query_routes(self, arguments: dict[str, Any]) -> dict[str, Any]:
        allowed = {
            "entity_id",
            "segment",
            "period",
            "metric",
            "top_n",
            "order_by",
            "comparison_period",
            "origin_iata",
            "destination_iata",
        }
        if set(arguments) - allowed:
            raise PlanValidationError("Argumentos query_routes no válidos")
        entity_id = _validate_choice(arguments.get("entity_id"), ENTITY_IDS, "entity_id")
        segment = _validate_choice(arguments.get("segment"), SEGMENTS, "segment")
        period = _validate_period(arguments.get("period"), "period")
        metric = _validate_choice(arguments.get("metric", "passengers"), METRICS, "metric")
        top_n = _validate_top_n(arguments.get("top_n"))
        order_by = arguments.get("order_by", "value")
        if order_by not in {"value", "absolute_change", "relative_change"}:
            raise PlanValidationError("order_by no válido")
        comparison_period = arguments.get("comparison_period")
        if order_by != "value" and comparison_period is None:
            raise PlanValidationError("comparison_period es obligatorio para ordenar por cambio")
        if comparison_period is not None:
            comparison_period = _validate_period(comparison_period, "comparison_period")
            if comparison_period == period or ("M" in comparison_period) != ("M" in period):
                raise PlanValidationError(
                    "Los periodos comparados deben ser distintos y tener el mismo grano"
                )
        if metric == "load_factor" and order_by != "value":
            raise PlanValidationError("El cambio de factor de ocupación no está habilitado para rutas")
        query = {
            "entity_id": entity_id,
            "entity_label": _ENTITY_LABELS[entity_id],
            "segment": segment,
            "period": period,
            "metric": metric,
            "top_n": top_n,
            "order_by": order_by,
            "comparison_period": comparison_period,
        }
        for key in ("origin_iata", "destination_iata"):
            value = arguments.get(key)
            if value is not None:
                if not isinstance(value, str) or not re.fullmatch(r"[A-Z]{3}", value):
                    raise PlanValidationError(f"{key} debe ser un código IATA de tres letras")
                query[key] = value

        current_network, current_path = self._load(entity_id, segment, period)
        if current_network is None:
            return {
                **self._metadata(query, []),
                "coverage": {period: {"availability": "missing", "complete": False}},
                "rows": [],
                "row_count": 0,
                "available_route_count": 0,
                "truncated": False,
                "display": self._display(query, [], []),
            }
        networks = [(current_network, current_path)]
        previous_network = None
        if comparison_period:
            previous_network, previous_path = self._load(entity_id, segment, comparison_period)
            if previous_network is not None:
                networks.append((previous_network, previous_path))
        current_map = {
            route.get("market_key"): route
            for route in current_network.get("routes", [])
            if route.get("market_key")
        }
        previous_map = {
            route.get("market_key"): route
            for route in (previous_network or {}).get("routes", [])
            if route.get("market_key")
        }
        rows = []
        for market_key, route in current_map.items():
            if query.get("origin_iata") and query["origin_iata"] not in market_key.split("<>"):
                continue
            if query.get("destination_iata") and query["destination_iata"] not in market_key.split("<>"):
                continue
            value = route.get(metric)
            if metric == "load_factor" and value is not None:
                value = value * 100
            # Missing values are not queryable routes and must not inflate the
            # available count or appear as rows that look like zero-valued data.
            if value is None:
                continue
            previous_route = previous_map.get(market_key)
            previous_value = previous_route.get(metric) if previous_route else None
            if metric == "load_factor" and previous_value is not None:
                previous_value = previous_value * 100
            current_kind = _value_kind(current_network, route, metric) if value is not None else None
            previous_kind = (
                _value_kind(previous_network, previous_route, metric)
                if previous_network and previous_route and previous_value is not None
                else None
            )
            comparable = bool(
                comparison_period
                and previous_network
                and _coverage(current_network)["complete"]
                and _coverage(previous_network)["complete"]
                and previous_route
                and value is not None
                and previous_value is not None
                and current_kind == previous_kind
                and route.get("source_label") == previous_route.get("source_label")
            )
            delta = value - previous_value if comparable else None
            relative = delta / abs(previous_value) * 100 if comparable and previous_value != 0 else None
            if order_by == "absolute_change" and delta is None:
                continue
            if order_by == "relative_change" and relative is None:
                continue
            row = {
                "market_key": market_key,
                "origin": copy.deepcopy(route.get("origin")),
                "destination": copy.deepcopy(route.get("destination")),
                "value": value,
                "value_kind": current_kind,
                "unit": _METRIC_LABELS[metric][1],
                "source_label": route.get("source_label"),
                "operation_status": route.get("operation_status"),
                "coverage_note": route.get("coverage_note"),
                "comparison": {
                    "period": comparison_period,
                    "value": previous_value,
                    "value_kind": previous_kind,
                    "absolute_change": delta,
                    "relative_change_percent": relative,
                    "available": comparable,
                    "reason": None
                    if comparable
                    else self._comparability_reason(
                        current_network,
                        previous_network,
                        route,
                        previous_route,
                        value,
                        previous_value,
                        current_kind,
                        previous_kind,
                        comparison_period,
                    ),
                }
                if comparison_period
                else None,
            }
            rows.append(row)

        if order_by == "absolute_change":
            rows.sort(key=lambda row: (row["comparison"]["absolute_change"], row["market_key"]), reverse=True)
        elif order_by == "relative_change":
            rows.sort(
                key=lambda row: (row["comparison"]["relative_change_percent"], row["market_key"]),
                reverse=True,
            )
        else:
            rows.sort(key=lambda row: (row["value"] is not None, row["value"] or 0), reverse=True)
        available_route_count = len(rows)
        rows = rows[:top_n]
        coverage = {period: _coverage(current_network)}
        if comparison_period:
            coverage[comparison_period] = (
                _coverage(previous_network)
                if previous_network
                else {
                    "availability": "missing",
                    "complete": False,
                    "expected_months": [],
                    "observed_months": [],
                    "agent_eligible": None,
                    "eligibility_reason": "Periodo no publicado",
                    "sources": {},
                }
            )
        title, _ = _METRIC_LABELS[metric]
        display_query = {**query, "title": f"{title} por ruta · {_ENTITY_LABELS[entity_id]} · {period}"}
        return {
            **self._metadata(query, networks),
            "coverage": coverage,
            "rows": rows,
            "row_count": len(rows),
            "available_route_count": available_route_count,
            "truncated": available_route_count > top_n,
            "display": self._display(display_query, rows, networks),
        }

    @staticmethod
    def _comparability_reason(
        current,
        previous,
        route,
        previous_route,
        value,
        previous_value,
        current_kind,
        previous_kind,
        comparison_period,
    ):
        if previous is None:
            return "El periodo comparativo no está publicado"
        if not _coverage(current)["complete"] or not _coverage(previous)["complete"]:
            return "La cobertura de uno o ambos periodos es parcial"
        if previous_route is None:
            return "La ruta no aparece en ambos periodos; no se asume valor cero"
        if value is None or previous_value is None:
            return "Falta el valor de la ruta en al menos un periodo"
        if current_kind != previous_kind:
            return "Cambió el tipo de valor (observado, estimado o programado)"
        if route.get("source_label") != previous_route.get("source_label"):
            return "Cambió la fuente de la ruta"
        return f"No hay comparación válida contra {comparison_period}"

    @staticmethod
    def _display(
        query: dict[str, Any], rows: list[dict[str, Any]], networks: list[tuple[dict[str, Any], str]]
    ):
        metric = query.get("metric", "passengers")
        title, unit = _METRIC_LABELS[metric]
        columns = [
            {"key": "market_key", "label": "Ruta"},
            {"key": "value", "label": title, "unit": unit},
            {"key": "value_kind", "label": "Tipo de valor"},
        ]
        if query.get("comparison_period"):
            columns.extend(
                [
                    {"key": "comparison_value", "label": query["comparison_period"], "unit": unit},
                    {"key": "absolute_change", "label": "Cambio", "unit": unit},
                    {"key": "relative_change_percent", "label": "Cambio relativo", "unit": "%"},
                ]
            )
        display_rows = []
        for row in rows:
            display_row = {
                "market_key": row["market_key"],
                "value": row["value"],
                "value_kind": row["value_kind"],
            }
            if row.get("comparison"):
                display_row.update(
                    {
                        "comparison_value": row["comparison"]["value"],
                        "absolute_change": row["comparison"]["absolute_change"],
                        "relative_change_percent": row["comparison"]["relative_change_percent"],
                    }
                )
            display_rows.append(display_row)
        kinds = {row.get("value_kind") for row in rows if row.get("value_kind")}
        value_kind = next(iter(kinds)) if len(kinds) == 1 else "mixed" if kinds else "missing"
        period_id = query.get("period", "periodo").replace("/", "-")
        source_references = RouteTools._source_refs(networks)
        return {
            "display_id": f"tabla:rutas_{query.get('entity_id', 'compartidas').lower()}_{period_id}",
            "kind": "table",
            "title": query.get("title", f"Rutas compartidas · {query.get('period', '')}"),
            "columns": columns,
            "rows": display_rows,
            "value_kind": value_kind,
            "source": source_references[0] if source_references else None,
            "sources": source_references,
            "source_references": source_references,
        }

    @staticmethod
    def _source_refs(networks: list[tuple[dict[str, Any], str]]) -> list[dict[str, str]]:
        refs = []
        for network, path in networks:
            refs.append(
                {
                    "label": f"Dashboard público · {network.get('period_label', path.rsplit('/', 1)[-1])}",
                    "url": "https://salvamalfa.github.io/aeromexico-tracker/" + quote(path, safe="/"),
                }
            )
        return refs

    def find_shared_routes(self, arguments: dict[str, Any]) -> dict[str, Any]:
        allowed = {"entity_ids", "segment", "period", "metric", "top_n"}
        if set(arguments) - allowed:
            raise PlanValidationError("Argumentos find_shared_routes no válidos")
        entity_ids = arguments.get("entity_ids")
        if not isinstance(entity_ids, list) or not 2 <= len(entity_ids) <= 3:
            raise PlanValidationError("entity_ids debe incluir entre 2 y 3 aerolíneas")
        if len(set(entity_ids)) != len(entity_ids):
            raise PlanValidationError("entity_ids no puede repetir entidades")
        entity_ids = [_validate_choice(item, _AIRLINE_IDS, "entity_id") for item in entity_ids]
        segment = _validate_choice(arguments.get("segment"), SEGMENTS, "segment")
        period = _validate_period(arguments.get("period"), "period")
        metric = _validate_choice(
            arguments.get("metric", "passengers"), ("passengers", "seats", "departures"), "metric"
        )
        top_n = _validate_top_n(arguments.get("top_n"))
        query = {
            "entity_ids": entity_ids,
            "segment": segment,
            "period": period,
            "metric": metric,
            "top_n": top_n,
        }
        network_by_entity, paths = {}, {}
        for entity_id in entity_ids:
            network, path = self._load(entity_id, segment, period)
            if network is not None:
                network_by_entity[entity_id] = network
                paths[entity_id] = path

        route_maps: dict[str, dict[str, dict[str, Any]]] = {}
        for entity_id, network in network_by_entity.items():
            route_maps[entity_id] = {
                r["market_key"]: r for r in network.get("routes", []) if r.get("market_key")
            }

        route_keys = (
            set.intersection(*(set(route_maps.get(entity_id, {})) for entity_id in entity_ids))
            if len(route_maps) == len(entity_ids)
            else set()
        )
        rows = []
        for market_key in route_keys:
            carriers = {}
            valid = True
            for entity_id in entity_ids:
                route = route_maps[entity_id][market_key]
                value = (
                    route.get("carrier_breakdown", {}).get("AEROMEXICO")
                    if entity_id == "INDUSTRY" and "AEROMEXICO_GROUP" in entity_ids
                    else route.get(metric)
                )
                if entity_id == "INDUSTRY" and value is None:
                    valid = False
                    break
                carriers[entity_id] = {
                    "label": _ENTITY_LABELS[entity_id],
                    "value": value,
                    "value_kind": _value_kind(network_by_entity[entity_id], route, metric)
                    if value is not None
                    else None,
                    "source_label": route.get("source_label"),
                }
            # Exact entity route sets are the evidence of presence. For INDUSTRY + an
            # individual airline, the airline's own file must carry a positive value.
            if valid and all(item["value"] is not None and item["value"] > 0 for item in carriers.values()):
                first_route = route_maps[entity_ids[0]][market_key]
                kinds = {item["value_kind"] for item in carriers.values()}
                source_families = {
                    str(item["source_label"] or "").split(" · ", maxsplit=1)[0] for item in carriers.values()
                }
                rows.append(
                    {
                        "market_key": market_key,
                        "origin": copy.deepcopy(first_route.get("origin")),
                        "destination": copy.deepcopy(first_route.get("destination")),
                        "carriers": carriers,
                        "combined_value": sum(item["value"] for item in carriers.values()),
                        "unit": _METRIC_LABELS[metric][1],
                        "coverage": {
                            entity_id: _coverage(network_by_entity[entity_id]) for entity_id in entity_ids
                        },
                        "comparable": len(kinds) == 1 and len(source_families) == 1,
                        "value_kind": next(iter(kinds)) if len(kinds) == 1 else "mixed",
                    }
                )
        rows.sort(key=lambda row: (row["combined_value"], row["market_key"]), reverse=True)
        count = len(rows)
        rows = rows[:top_n]
        networks_with_paths = [
            (network_by_entity[key], paths[key]) for key in entity_ids if key in network_by_entity
        ]
        coverage = {
            key: _coverage(value)
            if value
            else {
                "availability": "missing",
                "complete": False,
                "expected_months": [],
                "observed_months": [],
                "agent_eligible": None,
                "eligibility_reason": "Periodo no publicado para esta entidad",
                "sources": {},
            }
            for key, value in ((entity, network_by_entity.get(entity)) for entity in entity_ids)
        }
        meta = self._metadata(query, networks_with_paths)
        display_rows = [
            {
                "market_key": row["market_key"],
                "combined_value": row["combined_value"],
                **{f"{key}_value": value["value"] for key, value in row["carriers"].items()},
                "value_kind": row["value_kind"],
            }
            for row in rows
        ]
        value_kinds = {row["value_kind"] for row in rows}
        source_references = self._source_refs(networks_with_paths)
        display = {
            "display_id": f"tabla:rutas_compartidas_{period}",
            "kind": "table",
            "title": f"Rutas compartidas · {period}",
            "columns": [
                {"key": "market_key", "label": "Ruta"},
                *[
                    {
                        "key": f"{entity}_value",
                        "label": _ENTITY_LABELS[entity],
                        "unit": _METRIC_LABELS[metric][1],
                    }
                    for entity in entity_ids
                ],
                {"key": "value_kind", "label": "Tipo de valor"},
            ],
            "rows": display_rows,
            "value_kind": next(iter(value_kinds))
            if len(value_kinds) == 1
            else "mixed"
            if value_kinds
            else "missing",
            "source": source_references[0] if source_references else None,
            "sources": source_references,
            "source_references": source_references,
        }
        return {
            **meta,
            "coverage": coverage,
            "rows": rows,
            "row_count": len(rows),
            "available_route_count": count,
            "truncated": count > top_n,
            "aeromexico_scope": (
                "AEROMEXICO_GROUP agrega Aerovías de México y Aeroméxico Connect; "
                "la red pública exportada no permite separarlos."
            ),
            "display": display,
        }

    def invoke(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        if name not in TOOL_NAMES:
            raise PlanValidationError(f"Herramienta desconocida: {name}")
        if not isinstance(arguments, dict):
            raise PlanValidationError("arguments debe ser un objeto")
        if name == "query_routes":
            return self.query_routes(arguments)
        return self.find_shared_routes(arguments)

    execute = invoke


__all__ = ["RouteTools", "ROUTE_TOOL_SPECS", "TOOL_NAMES", "ENTITY_IDS", "SEGMENTS", "METRICS"]
