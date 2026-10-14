"""Official BTS route views for Industria, Volaris and Viva.

No domestic carrier-route observations are available for these entities.
Historical paid-provider estimates remain outside the active view.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Callable

from src.dashboard.domestic_routes import load_domestic_monthly_networks
from src.dashboard.route_entities import EXTRA_ROUTE_ENTITIES, RouteEntity, breakdown_totals


def entity_international_networks(connection, networks, entity: RouteEntity):
    """Keep the entity's own observed Mexico–United States BTS markets."""
    if entity.aeromexico_layers:
        raise ValueError("Grupo Aeroméxico keeps extend_networks()")
    result = deepcopy(networks)
    for network in result.values():
        original_months = network["observed_months"]
        for route in network["routes"]:
            route["source_label"] = "Estados Unidos · BTS T-100"
            route["observed_months"] = original_months
            route["coverage_note"] = "Meses: " + ", ".join(m[5:] for m in original_months) + " · BTS T-100"
        network["aena_airport_activity"] = []
        aps = {e["iata"]: e for r in network["routes"] for e in (r["origin"], r["destination"])}
        network["airports"] = sorted(aps.values(), key=lambda a: a["iata"])
        network["route_count"] = len(network["routes"])
        network["airport_count"] = len(aps)
        network["coverage"] = "México–EE. UU. observado por T-100; cobertura parcial, meses disponibles por operador"
        network["coverage_by_source"] = {
            source: sorted(
                {
                    m
                    for r in network["routes"]
                    if r.get("source_label") == source
                    for m in (r.get("observed_months") or r.get("estimated_months", []))
                }
            )
            for source in sorted({r["source_label"] for r in network["routes"]})
        }
        network["totals"] = {k: None for k in ("passengers", "seats", "departures")}
        network["agent_eligible"] = False
    return result


def build_entity_networks(
    connection, quarters: list[dict[str, Any]], load_routes: Callable[..., dict[str, Any]]
) -> dict[str, dict[str, Any]]:
    """International (quarterly) and domestic (monthly) maps per extra entity.

    ``load_routes`` is ``flights._load_routes`` (T-100 per entity), passed in
    to avoid a circular import.
    """
    result = {}
    for entity in EXTRA_ROUTE_ENTITIES:
        t100 = {}
        for record in quarters:
            network = load_routes(connection, record["period_id"], entity)
            if "operator" in network:
                network["operator"] = f"{entity.label}, operador/reportante BTS"
            _add_t100_breakdown(connection, network, entity)
            t100[record["period_id"]] = network
        result[entity.key] = {
            "label": entity.label,
            "route_networks": entity_international_networks(connection, t100, entity),
            "domestic_monthly_networks": load_domestic_monthly_networks(connection, entity),
        }
    return result


def _add_t100_breakdown(connection, network: dict[str, Any], entity: RouteEntity) -> None:
    """Industria: each T-100 route's passengers by airline, same months as the route."""
    months = network.get("observed_months") or []
    if not entity.breakdown or not months:
        return
    carriers = tuple(entity.t100_carriers)
    rows = connection.execute(
        f"""SELECT market_key, carrier_key, SUM(passengers)
            FROM fact_route_traffic_summary
            WHERE carrier_key IN ({', '.join('?' for _ in carriers)})
              AND period_id IN ({', '.join('?' for _ in months)})
            GROUP BY market_key, carrier_key""",
        [*carriers, *months],
    ).fetchall()
    by_market: dict[str, list[tuple[str, float]]] = {}
    for market, carrier, passengers in rows:
        by_market.setdefault(str(market), []).append((str(carrier), float(passengers or 0)))
    for route in network["routes"]:
        route["carrier_breakdown"] = breakdown_totals(entity, by_market.get(route["market_key"], []))
