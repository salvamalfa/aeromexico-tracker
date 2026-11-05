"""Read-only projection of the map's North America observed-flight view."""

from __future__ import annotations

import copy
from typing import Any

# Same region membership as the existing dashboard regions.ts contract.
REGION_MEMBERS = {
    "asia": {"ICN", "NRT"},
    "europa": {"AMS", "BCN", "CDG", "FCO", "LHR", "MAD"},
    "sudamerica": {"BOG", "CLO", "CTG", "EZE", "GRU", "LIM", "MDE", "SCL", "UIO", "VCP"},
}


def route_region(route: dict[str, Any]) -> str:
    def mexican(airport: dict) -> bool:
        lat, lon = airport.get("lat"), airport.get("lon")
        return (
            isinstance(lat, (int, float))
            and isinstance(lon, (int, float))
            and 14 <= lat <= 33
            and -118 <= lon <= -86
        )

    origin, destination = route.get("origin", {}), route.get("destination", {})
    airport = destination if mexican(origin) else origin if mexican(destination) else destination
    return next(
        (name for name, members in REGION_MEMBERS.items() if airport.get("iata") in members), "norteamerica"
    )


def _observed(route: dict) -> bool:
    status, source = route.get("operation_status", ""), route.get("source_label", "")
    if (
        status == "assigned_slot_not_flown"
        or status.startswith(("scheduled_", "estimated_"))
        or status == "carrier_inferred_market_observed"
    ):
        return False
    if "observed" in status or "T-100" in source:
        return True
    return not route.get("capacity_estimated") and "aerodatabox" not in source.lower()


def observed_north_america_view(network: dict[str, Any], region: str | None = None) -> dict[str, Any]:
    """Keep observed components in NA; other regions keep their original kinds.

    A mixed route has no passenger/capacity split by flight evidence. Those
    metrics stay missing after projection, matching the map consumer.
    """
    result = copy.deepcopy(network)
    routes = []
    observed_months: set[str] = set()
    for route in result.get("routes", []):
        route_area = route_region(route)
        if region == "norteamerica" and route_area != region:
            continue
        if route_area != "norteamerica":
            routes.append(route)
            continue
        components = route.get("flight_components") or []
        if components:
            observed = [component for component in components if component.get("kind") == "observed"]
            if not observed:
                continue
            if len(observed) != len(components):
                route.update(
                    passengers=None, seats=None, load_factor=None, monthly=[], capacity_estimated=False
                )
                route.pop("previous", None)
            route["flight_components"] = observed
            directions: dict[tuple[str, str], dict] = {}
            for component in observed:
                key = (component["origin_iata"], component["destination_iata"])
                direction = directions.setdefault(
                    key, {"origin_iata": key[0], "destination_iata": key[1], "departures": 0}
                )
                direction["departures"] += component["departures"]
            route["directions"] = list(directions.values())
            route["departures"] = sum(component["departures"] for component in observed)
            route["source_label"] = " · ".join(sorted({component["source_label"] for component in observed}))
            route["operation_status"] = "operated_observed"
            observed_months.update(component["period_id"] for component in observed)
            route.setdefault("metric_value_kinds", {})["departures"] = "observed"
            route.get("metric_provenance", {}).pop("departures", None)
        elif not _observed(route):
            continue
        else:
            observed_months.update(
                row["period_id"] for row in route.get("monthly", []) if row.get("period_id")
            )
        route.pop("recorded_movements", None)
        routes.append(route)
    result["routes"] = routes
    result["flight_evidence"] = "north_america_observed"
    result["flight_evidence_scope"] = (
        "Norteamérica: sólo vuelos observados; las demás regiones conservan su tipo de evidencia."
    )
    if observed_months and region == "norteamerica":
        result["observed_months"] = sorted(observed_months)
        if not set(result.get("expected_months", [])) <= observed_months:
            result["availability"] = "partial"
    return result
