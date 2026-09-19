"""AFAC market movements may be attributed only with corroborated route scope."""

from __future__ import annotations

import duckdb
import openpyxl
import pandas as pd

from src.config import PATHS
from src.dashboard.flights import build_flight_payload
from src.transform.afac_exclusive_domestic import AFAC, GOLD, SILVER, _roster


def test_exclusive_market_rows_reconcile_to_afac_and_lineage():
    roster = _roster()
    assert "Colima" in roster["aeromexico"] and "Durango" in roster["aeromexico"]
    assert all("Colima" not in routes and "Durango" not in routes for carrier, routes in roster.items() if carrier != "aeromexico")
    sheet = openpyxl.load_workbook(AFAC, read_only=True, data_only=True)["REG NAC"]
    gold = pd.read_parquet(GOLD)
    silver = pd.read_parquet(SILVER)
    assert len(gold) == len(silver) == 14
    assert int(gold.market_movements.sum()) == 364
    assert set(gold.attribution_status) == {"inferred_exclusive_carrier_market"}
    assert set(gold.agent_eligible) == {False}
    for row in gold.itertuples(index=False):
        assert sheet[row.source_cell].value == row.market_movements
    by_market = gold.assign(market=gold.apply(lambda row: "<>".join(sorted((row.origin_iata, row.dest_iata))), axis=1)).groupby("market").market_movements.sum().to_dict()
    assert by_market == {"CLQ<>MEX": 12, "CLQ<>NLU": 170, "DGO<>NLU": 182}
    with duckdb.connect(str(PATHS.warehouse), read_only=True) as connection:
        assert connection.execute("SELECT sum(market_movements) FROM fact_domestic_exclusive_market_inferences").fetchone()[0] == 364
        assert connection.execute("SELECT count(*) FROM bridge_domestic_exclusive_market_lineage").fetchone()[0] == 36
        assert connection.execute("SELECT count(*) FROM fact_domestic_scheduled_route_movements WHERE origin_iata = 'CLQ' OR dest_iata = 'CLQ'").fetchone()[0] == 0


def test_domestic_consumer_shows_distinct_aifa_and_aicm_colima_markets():
    network = build_flight_payload()["domestic_networks"]["2026Q2"]
    inferred = {route["market_key"]: route for route in network["routes"] if route["operation_status"] == "carrier_inferred_market_observed"}
    assert set(inferred) == {"CLQ<>MEX", "CLQ<>NLU", "DGO<>NLU"}
    assert {key: route["departures"] for key, route in inferred.items()} == {"CLQ<>MEX": 12, "CLQ<>NLU": 170, "DGO<>NLU": 182}
    for route in inferred.values():
        assert route["passengers"] is route["seats"] is route["load_factor"] is None
        assert sum(direction["departures"] for direction in route["directions"]) == route["departures"]
