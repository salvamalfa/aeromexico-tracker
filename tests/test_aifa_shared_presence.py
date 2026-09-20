"""Shared AIFA market traffic must never become Aeromexico route volume."""

from __future__ import annotations

import duckdb
import openpyxl
import pandas as pd

from src.config import PATHS
from src.dashboard.flights import build_flight_payload
from src.transform.aifa_shared_presence import AFAC, DESTINATIONS, GOLD, SILVER


def test_shared_markets_preserve_carrier_volume_boundary():
    silver = pd.read_parquet(SILVER)
    gold = pd.read_parquet(GOLD)
    afac = openpyxl.load_workbook(AFAC, read_only=True, data_only=True)["REG NAC"]
    assert len(silver) == 48 and len(gold) == 8
    assert set(gold.dest_iata) == set(DESTINATIONS.values())
    assert gold.carrier_movements.isna().all()
    assert set(gold.attribution_status) == {"carrier_route_present_volume_unresolved"}
    assert set(gold.carrier_presence_as_of) == {"2026-06-08"}
    assert set(gold.agent_eligible) == {False}
    for row in silver.itertuples(index=False):
        assert afac[row.source_cell].value == row.market_movements_all_carriers
    with duckdb.connect(str(PATHS.warehouse), read_only=True) as connection:
        assert connection.execute("SELECT count(*) FROM fact_aifa_shared_route_presence").fetchone()[0] == 8
        assert connection.execute("SELECT count(*) FROM bridge_aifa_shared_route_presence_lineage").fetchone()[0] == 16


def test_aifa_routes_are_estimated_without_reusing_all_carrier_movements():
    network = build_flight_payload()["domestic_networks"]["2026Q2"]
    routes = {route["market_key"]: route for route in network["routes"]}
    expected = {"<>".join(sorted(("NLU", airport))) for airport in DESTINATIONS.values()}
    assert expected.issubset(routes)
    assert len(network["routes"]) == 56
    assert network["represented_movements"] is None
    for key in expected:
        assert routes[key]["passengers"] > 0
        assert routes[key]["departures"] is None
        assert routes[key]["operation_status"] == "estimated_from_afac_margins_and_temporal_support"
