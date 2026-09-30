"""Seat capacity behind each Vuelos map entity (Dashboard v2, fase 4).

Aerovías and Connect keep the aircraft-model capacity tables; Volaris and
Viva use the fleet-average estimate of :mod:`src.analytics.fleet_capacity`.
Industria stacks both. The dashboard's completeness rule lets a carrier
missing from the capacity table contribute nothing to a group's seats; for
Industria that would understate seats wherever an Aeroméxico cell has
passengers but no capacity row, so such a cell gets an unusable row and the
occupancy stays N/D instead.
"""

from __future__ import annotations

import pandas as pd

from src.analytics.fleet_capacity import CAPACITY_COLUMNS, fleet_capacity
from src.dashboard.route_entities import RouteEntity

MODEL_TABLES = {
    "domestic": "fact_aeromexico_domestic_capacity_estimate",
    "international": "fact_aeromexico_international_capacity_estimate",
}
ESTIMATE_TABLES = {
    "domestic": "fact_route_carrier_domestic_estimate",
    "international": "fact_route_carrier_international_estimate",
}
CELL = ["period_id", "market_key", "origin_iata", "destination_iata", "carrier_key"]


def _exists(connection, table: str) -> bool:
    return bool(connection.execute(
        "SELECT count(*) FROM information_schema.tables WHERE table_name = ?", [table]
    ).fetchone()[0])


def load_route_capacity(connection, entity: RouteEntity, scope: str) -> pd.DataFrame:
    """Capacity rows for the entity's carriers, or an empty frame without capacity."""

    if not entity.capacity:
        return pd.DataFrame()
    model_carriers = [key for key in entity.estimate_carriers if key not in entity.fleet_capacity_carriers]
    frames = []
    table = MODEL_TABLES[scope]
    if model_carriers and _exists(connection, table):
        placeholders = ", ".join("?" for _ in model_carriers)
        model = connection.execute(
            f"SELECT * FROM {table} WHERE carrier_key IN ({placeholders})", model_carriers
        ).df()
        frames.append(model)
        if entity.fleet_capacity_carriers and _exists(connection, ESTIMATE_TABLES[scope]):
            cells = connection.execute(
                f"SELECT DISTINCT {', '.join(CELL)} FROM {ESTIMATE_TABLES[scope]} "
                f"WHERE carrier_key IN ({placeholders})",
                model_carriers,
            ).df()
            missing = cells.merge(model[CELL], on=CELL, how="left", indicator=True)
            missing = missing[missing["_merge"] == "left_only"].drop(columns="_merge")
            if not missing.empty:
                frames.append(missing.assign(capacity_usable=False, aircraft_model_coverage=0.0))
    if entity.fleet_capacity_carriers:
        frames.append(fleet_capacity(connection, scope, entity.fleet_capacity_carriers))
    frames = [frame for frame in frames if not frame.empty]
    if not frames:
        return pd.DataFrame(columns=list(CAPACITY_COLUMNS))
    return pd.concat(frames, ignore_index=True)
