"""Seat capacity per route for Volaris and Viva from a fleet-average gauge.

Grupo Aeroméxico's capacity maps each captured flight's aircraft model to a
versioned seat configuration (:mod:`src.analytics.international_capacity`).
The transient captures that carried the aircraft model are gone, and only
monthly flights per route x carrier were kept, so Volaris and Viva use the
next best public evidence (owner decision of 30 Sep 2026, Dashboard v2 fase
4):

    seats = departures x seats per departure observed by BTS T-100

The gauge is each carrier's own T-100 seats / departures over the 12
reported months before the period (never the period itself, so the T-100
backtest stays out of sample). The band uses the 10th and 90th percentiles
of the per-route gauge on routes with at least ``MIN_ROUTE_DEPARTURES``
departures in that window. Departures come from the passenger estimates'
own flights: the domestic seed weight when the route was observed in the
period (a seed borrowed from another month is not a departure count and
leaves the cell unusable), and ``departures_estimated`` internationally.

The output has the columns of the Aeroméxico capacity tables, with
``aircraft_model_coverage = 0`` because no aircraft model is known, and
``capacity_method = FLEET_CAPACITY_METHOD``. Measured error against T-100 on
Mexico–United States routes is documented in
``docs/etapas/dashboard-v2-fase4-capacidad-20260930.md``.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

FLEET_CAPACITY_METHOD = "departures_x_t100_fleet_gauge_v1"
FLEET_CAPACITY_CARRIERS = ("VOLARIS", "VIVA_AEROBUS")
GAUGE_MONTHS = 12
MIN_ROUTE_DEPARTURES = 50
CAPACITY_COLUMNS = (
    "period_id", "market_key", "origin_iata", "destination_iata", "carrier_key",
    "departures_estimated", "seats_estimated", "seats_estimated_low",
    "seats_estimated_high", "aircraft_model_coverage", "capacity_usable",
    "capacity_method",
)
_SOURCES = {
    "domestic": (
        "fact_route_carrier_domestic_estimate",
        "seed_weight AS departures, support_observed_in_period AS observed",
    ),
    "international": (
        "fact_route_carrier_international_estimate",
        "departures_estimated AS departures, TRUE AS observed",
    ),
}


def _table_exists(connection, table: str) -> bool:
    return bool(connection.execute(
        "SELECT count(*) FROM information_schema.tables WHERE table_name = ?", [table]
    ).fetchone()[0])


def t100_gauge(connection, carrier: str, period_id: str) -> dict | None:
    """Seats per departure from the carrier's 12 T-100 months before ``period_id``."""

    if not _table_exists(connection, "fact_route_traffic_summary"):
        return None
    months = [str(row[0]) for row in connection.execute(
        """SELECT DISTINCT period_id FROM fact_route_traffic_summary
           WHERE carrier_key = ? AND period_id < ? ORDER BY period_id DESC LIMIT ?""",
        [carrier, period_id, GAUGE_MONTHS],
    ).fetchall()]
    if len(months) < GAUGE_MONTHS:
        return None
    routes = connection.execute(
        f"""SELECT market_key, SUM(seats) AS seats, SUM(departures) AS departures
            FROM fact_route_traffic_summary
            WHERE carrier_key = ? AND period_id IN ({', '.join('?' for _ in months)})
            GROUP BY market_key""",
        [carrier, *months],
    ).df()
    if routes.empty or routes["departures"].sum() <= 0:
        return None
    busy = routes[routes["departures"] >= MIN_ROUTE_DEPARTURES]
    if busy.empty:
        return None
    low, high = np.quantile(busy["seats"] / busy["departures"], [0.1, 0.9])
    return {
        "point": float(routes["seats"].sum() / routes["departures"].sum()),
        "low": float(low),
        "high": float(high),
        "months": sorted(months),
        "routes": int(len(busy)),
    }


def fleet_capacity(connection, scope: str, carriers: tuple[str, ...]) -> pd.DataFrame:
    """Monthly seat capacity per direction for ``carriers`` (see module doc)."""

    table, columns = _SOURCES[scope]
    unknown = set(carriers) - set(FLEET_CAPACITY_CARRIERS)
    if unknown:
        raise ValueError(f"no fleet-gauge capacity for {sorted(unknown)}")
    if not carriers or not _table_exists(connection, table):
        return pd.DataFrame(columns=list(CAPACITY_COLUMNS))
    frame = connection.execute(
        f"""SELECT period_id, market_key, origin_iata, destination_iata, carrier_key, {columns}
            FROM {table} WHERE carrier_key IN ({', '.join('?' for _ in carriers)})""",
        list(carriers),
    ).df()
    gauges: dict[tuple[str, str], dict | None] = {}
    rows = []
    for row in frame.itertuples(index=False):
        key = (str(row.carrier_key), str(row.period_id))
        if key not in gauges:
            gauges[key] = t100_gauge(connection, *key)
        gauge = gauges[key]
        departures = float(row.departures) if pd.notna(row.departures) else None
        usable = bool(row.observed) and gauge is not None and departures is not None and departures > 0
        rows.append({
            "period_id": key[1],
            "market_key": str(row.market_key),
            "origin_iata": str(row.origin_iata),
            "destination_iata": str(row.destination_iata),
            "carrier_key": key[0],
            "departures_estimated": departures if usable else None,
            "seats_estimated": departures * gauge["point"] if usable else None,
            "seats_estimated_low": departures * gauge["low"] if usable else None,
            "seats_estimated_high": departures * gauge["high"] if usable else None,
            "aircraft_model_coverage": 0.0,
            "capacity_usable": usable,
            "capacity_method": FLEET_CAPACITY_METHOD,
        })
    return pd.DataFrame(rows, columns=list(CAPACITY_COLUMNS))
