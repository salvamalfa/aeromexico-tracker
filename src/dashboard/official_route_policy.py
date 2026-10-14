"""Remove retired model values from active route views and runtime snapshots.

The builders read official sources directly. This additional boundary protects
chat from older signed snapshots and exports from accidental model enrichment.
It never deletes the retained source files or substitutes missing values.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any


def official_network(network: dict[str, Any]) -> dict[str, Any]:
    result = deepcopy(network)
    routes = []
    changed = False
    for route in result.get("routes", []):
        source = str(route.get("source_label") or "").lower()
        status = str(route.get("operation_status") or "").lower()
        if (
            network.get("mode") == "estimated_domestic"
            or status.startswith("estimated_")
            or status == "carrier_inferred_market_observed"
            or "aerodatabox" in source
        ):
            changed = True
            continue
        retired = set()
        for metric in ("passengers", "seats", "departures", "load_factor"):
            kind = (route.get("metric_value_kinds") or {}).get(metric)
            provenance = (route.get("metric_provenance") or {}).get(metric) or {}
            if kind == "estimated" or "aerodatabox" in str(provenance).lower():
                retired.add(metric)
        if route.get("passengers_estimated"):
            retired.add("passengers")
        if route.get("departures_estimated"):
            retired.add("departures")
        if route.get("capacity_estimated"):
            retired.update(("seats", "load_factor"))
        # A known official route may have been enriched without changing its
        # source label. Suppress those metrics and every dependent breakdown.
        if retired:
            changed = True
            for metric in retired:
                route[metric] = None
                route.get("previous", {}).pop(metric, None)
                for suffix in ("_low", "_high"):
                    route.pop(metric + suffix, None)
                for direction in route.get("directions", []):
                    direction[metric] = None
                    direction.pop(metric + "_low", None)
                    direction.pop(metric + "_high", None)
            route.pop("monthly", None)
            route.pop("months_covered", None)
            route.pop("months_selected", None)
            route.pop("carrier_breakdown", None)
            route.pop("capacity_provenance", None)
            route.pop("metric_provenance", None)
            route.pop("metric_value_kinds", None)
            route.pop("estimator_version", None)
            route.pop("load_factor_status", None)
            route.pop("departures_estimated", None)
            # Older notes appended an IPF passenger explanation to the
            # original authority coverage note.
            route["coverage_note"] = str(route.get("coverage_note") or "").split(" · Pasajeros estimados")[0]
        route["passengers_estimated"] = False
        route["capacity_estimated"] = False
        routes.append(route)
    result["routes"] = routes
    result.pop("estimated_passenger_route_count", None)
    if changed:
        airports = {
            endpoint["iata"]: endpoint
            for route in routes
            for endpoint in (route["origin"], route["destination"])
        }
        result["airports"] = sorted(airports.values(), key=lambda endpoint: endpoint["iata"])
        result["route_count"] = len(routes)
        result["airport_count"] = len(airports)
        result["totals"] = {metric: None for metric in ("passengers", "seats", "departures")}
        for key in ("represented_passengers", "represented_movements"):
            if key in result:
                result[key] = None
        result["coverage_by_source"] = {
            label: months
            for label, months in result.get("coverage_by_source", {}).items()
            if "aerodatabox" not in label.lower()
        }
        result["coverage"] = "Fuentes oficiales retenidas; cobertura parcial"
        if network.get("mode") == "estimated_domestic":
            result["mode"] = "official_domestic_unavailable"
            result["availability"] = "unavailable"
            result["observed_months"] = []
            result["eligibility_reason"] = (
                "Sin vuelos realizados por compañía y ruta disponibles en fuentes oficiales."
            )
    return result
