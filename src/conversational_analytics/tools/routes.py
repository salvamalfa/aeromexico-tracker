"""Deterministic route queries over the verified, published flight snapshot.

This module is intentionally independent from the shared tool registry. The
registry can compose ``ROUTE_TOOL_SPECS`` and delegate these two tool names to
``RouteTools`` without coupling the route query contract to metric queries.
"""

from __future__ import annotations

import copy
import re
from typing import Any
from urllib.parse import quote

from src.conversational_analytics.semantic.plan import PlanValidationError
from src.conversational_analytics.tools._route_contract import (
    AIRLINE_IDS as _AIRLINE_IDS,
)
from src.conversational_analytics.tools._route_contract import (
    ENTITY_IDS,
    METRICS,
    ROUTE_TOOL_SPECS,
    SEGMENTS,
    TOOL_NAMES,
    path_for,
)
from src.conversational_analytics.tools._route_contract import (
    ENTITY_LABELS as _ENTITY_LABELS,
)
from src.conversational_analytics.tools._route_contract import (
    METRIC_LABELS as _METRIC_LABELS,
)
from src.conversational_analytics.tools._route_contract import (
    build_display as _build_display,
)
from src.conversational_analytics.tools._route_contract import (
    coverage as _coverage,
)
from src.conversational_analytics.tools._route_contract import (
    deduplicate_source_references as _deduplicate_source_references,
)
from src.conversational_analytics.tools._route_contract import (
    display_query_hash as _display_query_hash,
)
from src.conversational_analytics.tools._route_contract import (
    safe_source_url as _safe_source_url,
)
from src.conversational_analytics.tools._route_contract import (
    source_references as _source_references,
)
from src.conversational_analytics.tools._route_contract import (
    validate_choice as _validate_choice,
)
from src.conversational_analytics.tools._route_contract import (
    validate_period as _validate_period,
)
from src.conversational_analytics.tools._route_contract import (
    validate_top_n as _validate_top_n,
)
from src.conversational_analytics.tools._route_rollup import rollup_complete_quarter
from src.conversational_analytics.tools._route_shared_display import build_shared_display


def _value_kind(network: dict[str, Any], route: dict[str, Any], metric: str) -> str:
    override = (route.get("metric_value_kinds") or {}).get(metric)
    if override in {"reported", "observed", "estimated", "scheduled", "mixed", "missing"}:
        return override
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


class RouteTools:
    """Read-only route query adapter over a ``Snapshot``-like object."""

    def __init__(self, snapshot: Any):
        self.snapshot = snapshot

    @staticmethod
    def tool_specs() -> list[dict[str, Any]]:
        return copy.deepcopy(ROUTE_TOOL_SPECS)

    def _load(self, entity_id: str, segment: str, period: str) -> tuple[dict[str, Any] | None, str]:
        path = path_for(entity_id, segment, period)
        try:
            network = self.snapshot.payload(path)
        except (ValueError, KeyError):
            if segment == "domestic" and "Q" in period:
                year, quarter = int(period[:4]), int(period[-1])
                first_month = (quarter - 1) * 3 + 1
                month_periods = [f"{year:04d}M{month:02d}" for month in range(first_month, first_month + 3)]
                month_networks = []
                for month_period in month_periods:
                    try:
                        month_networks.append(
                            self.snapshot.payload(path_for(entity_id, segment, month_period))
                        )
                    except (ValueError, KeyError):
                        return None, path
                rollup = rollup_complete_quarter(period, month_networks, _value_kind)
                if rollup is not None:
                    rollup["source_paths"] = [path_for(entity_id, segment, month) for month in month_periods]
                return rollup, path
            return None, path
        return network, path

    def _metadata(self, query: dict[str, Any], networks: list[tuple[dict[str, Any], str]]) -> dict[str, Any]:
        refs = []
        for network, path in networks:
            source_paths = network.get("source_paths")
            if not isinstance(source_paths, list):
                source_paths = [path]
            for source_path in source_paths:
                published_url = "https://salvamalfa.github.io/aeromexico-tracker/" + quote(
                    source_path, safe="/"
                )
                source_period = source_path.rsplit("/", 1)[-1].removesuffix(".json")
                refs.append(
                    {
                        "label": f"Dashboard público, rutas: {source_period}",
                        "url": published_url,
                    }
                )
            source_urls = network.get("source_urls")
            if not isinstance(source_urls, list):
                source_urls = [network.get("source_url")]
            for raw_source_url in source_urls:
                source_url = _safe_source_url(raw_source_url)
                if not source_url:
                    continue
                refs.append(
                    {
                        "label": ", ".join(sorted(network.get("coverage_by_source", {})))
                        or "Fuente publicada",
                        "url": source_url,
                    }
                )
        unique_refs = _deduplicate_source_references(refs)
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
                "missing_route_count": 0,
                "truncated": False,
                "display": _build_display(query, [], []),
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
        missing_route_count = 0
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
                missing_route_count += 1
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
        coverage = {
            period: {
                **_coverage(current_network),
                "missing_route_count": missing_route_count,
                "missing_value_reason": (
                    "Las rutas sin valor para esta métrica se excluyen; su ausencia no significa cero."
                    if missing_route_count
                    else None
                ),
            }
        }
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
            "missing_route_count": missing_route_count,
            "truncated": available_route_count > top_n,
            "display": _build_display(display_query, rows, networks),
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
                carrier_coverages = {
                    entity_id: _coverage(network_by_entity[entity_id]) for entity_id in entity_ids
                }
                expected_universes = {
                    tuple(sorted(item["expected_months"])) for item in carrier_coverages.values()
                }
                observed_universes = {
                    tuple(sorted(item["observed_months"])) for item in carrier_coverages.values()
                }
                comparability_reasons = []
                if not all(item["complete"] for item in carrier_coverages.values()):
                    comparability_reasons.append("coverage_incomplete")
                if len(expected_universes) != 1 or len(observed_universes) != 1:
                    comparability_reasons.append("period_universe_differs")
                if len(kinds) != 1:
                    comparability_reasons.append("value_kind_differs")
                if len(source_families) != 1:
                    comparability_reasons.append("source_family_differs")
                rows.append(
                    {
                        "market_key": market_key,
                        "origin": copy.deepcopy(first_route.get("origin")),
                        "destination": copy.deepcopy(first_route.get("destination")),
                        "carriers": carriers,
                        "combined_value": sum(item["value"] for item in carriers.values()),
                        "unit": _METRIC_LABELS[metric][1],
                        "coverage": {
                            **carrier_coverages,
                        },
                        "comparable": not comparability_reasons,
                        "comparability_reason": comparability_reasons,
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
        display_columns, display_rows = build_shared_display(
            rows, entity_ids, _ENTITY_LABELS, _METRIC_LABELS[metric][1]
        )
        value_kinds = {row["value_kind"] for row in rows}
        source_references = _source_references(networks_with_paths)
        display = {
            "display_id": f"tabla:rutas_compartidas_{_display_query_hash(query)}",
            "kind": "table",
            "title": f"Rutas compartidas · {period}",
            "columns": display_columns,
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
