"""Vuelos map for Industria, Volaris and Viva (Dashboard v2, fase 3).

Mexico–United States comes from each entity's own BTS T-100 routes; every
other international market is the AFAC + AeroDataBox estimate, and the
domestic map is the same estimate (see ``src.dashboard.route_entities`` for
what each entity covers). Grupo Aeroméxico keeps its historical builders in
``flights.py``, ``international_routes.py`` and ``domestic_routes.py``.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Callable

import pandas as pd

from src.dashboard.domestic_routes import load_domestic_monthly_networks
from src.dashboard.international_routes import ESTIMATE_TABLE, ROUTE_PAYLOAD_KEYS, _estimated_routes
from src.dashboard.route_capacity import load_route_capacity
from src.dashboard.route_entities import EXTRA_ROUTE_ENTITIES, RouteEntity, breakdown_totals


def entity_international_networks(connection, networks, entity: RouteEntity):
    """International map of Volaris, Viva or Industria (Dashboard v2, fase 3).

    Mexico–United States comes from each entity's own BTS T-100 routes
    (``networks``, built by ``flights._load_routes`` for the entity); every
    other market is the AFAC + AeroDataBox estimate, labelled as such. None
    of Grupo Aeroméxico's own layers (authority observations, AICM, OMA,
    Aena) apply; seats come from ``route_capacity`` (fleet gauge, fase 4).
    """
    if entity.aeromexico_layers:
        raise ValueError("Grupo Aeroméxico keeps extend_networks()")
    has_estimate = connection.execute(
        f"SELECT count(*) FROM information_schema.tables WHERE table_name='{ESTIMATE_TABLE}'"
    ).fetchone()[0]
    carriers = tuple(entity.estimate_carriers)
    estimates = (
        connection.execute(
            f"SELECT * FROM {ESTIMATE_TABLE} WHERE carrier_key IN ({', '.join('?' for _ in carriers)})",
            list(carriers),
        ).df()
        if has_estimate
        else pd.DataFrame()
    )
    airports = connection.execute("SELECT * FROM dim_airport").df().set_index("airport_iata").to_dict("index")

    def endpoint(code):
        a = airports[code]
        if pd.isna(a["latitude"]) or pd.isna(a["longitude"]):
            raise ValueError("Missing coordinates")
        return dict(
            iata=code, name=a["name"], city=a["city"], country=a["country"],
            lat=float(a["latitude"]), lon=float(a["longitude"]),
        )

    label = entity.international_estimated_label
    capacity = load_route_capacity(connection, entity, "international")
    result = deepcopy(networks)
    for network in result.values():
        months = network["expected_months"]
        original_months = network["observed_months"]
        for route in network["routes"]:
            route["source_label"] = "Estados Unidos · BTS T-100"
            route["observed_months"] = original_months
            route["coverage_note"] = "Meses: " + ", ".join(m[5:] for m in original_months) + " · BTS T-100"
        for market, estimate in _estimated_routes(estimates, capacity, months, endpoint, entity).items():
            if any(r["market_key"] == market for r in network["routes"]):
                continue
            months_text = ", ".join(sorted({m["period_id"][5:] for m in estimate["monthly"]}))
            route = dict(
                market_key=market,
                origin=estimate["origin"],
                destination=estimate["destination"],
                **{k: estimate[k] for k in ROUTE_PAYLOAD_KEYS},
                departures=round(estimate["departures_estimated_seed"]),
                previous={k: None for k in ("passengers", "seats", "departures")},
                directions=[],
                source_label=label,
                observed_months=[],
                estimated_months=sorted({m["period_id"] for m in estimate["monthly"]}),
                coverage_note=(
                    f"Pasajeros estimados de {entity.group_label} (AFAC + AeroDataBox) · meses {months_text}"
                    " · vuelos: frecuencias de AeroDataBox · asientos por promedio de flota (T-100)"
                ),
                operation_status="estimated_from_afac_margins_and_aerodatabox_seed",
                carrier_role="operating_carrier_estimated",
                marketing_carrier=None,
                agent_eligible=False,
            )
            if "carrier_breakdown" in estimate:
                route["carrier_breakdown"] = estimate["carrier_breakdown"]
            network["routes"].append(route)
        network["aena_airport_activity"] = []
        aps = {e["iata"]: e for r in network["routes"] for e in (r["origin"], r["destination"])}
        network["airports"] = sorted(aps.values(), key=lambda a: a["iata"])
        network["route_count"] = len(network["routes"])
        network["airport_count"] = len(aps)
        network["coverage"] = "México–EE. UU. observado por T-100; resto de la red internacional estimado"
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
        network["estimated_passenger_route_count"] = sum(
            bool(r.get("passengers_estimated")) for r in network["routes"]
        )
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
