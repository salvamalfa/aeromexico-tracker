"""Checks that scheduled AICM assignments stay distinct from performed traffic."""

from __future__ import annotations

import hashlib
import json

import duckdb
import pandas as pd

from src.config import PATHS
from src.dashboard.flights import build_flight_payload
from src.dashboard.flights_html import integration_flight_payload
from src.transform.domestic_slots import GOLD, SILVER, SOURCE


def test_aicm_bronze_silver_gold_reconcile_and_preserve_scope():
    source_hash = hashlib.sha256(SOURCE.read_bytes()).hexdigest()
    metadata = json.loads(SOURCE.with_name(SOURCE.name + ".meta.json").read_text(encoding="utf-8"))
    assert metadata["sha256"] == source_hash
    silver = pd.read_parquet(SILVER)
    gold = pd.read_parquet(GOLD)
    assert not silver.duplicated(["flight_date", "origin_iata", "dest_iata", "flight_number", "flight_suffix", "assigned_time_utc"]).any()
    assert int(gold.scheduled_movements.sum()) == len(silver) == 31_098
    assert gold.source_hash.eq(source_hash).all()
    assert gold.observation_status.eq("assigned_slot_not_flown").all()
    assert set(gold.period_id) == {"2026M04", "2026M05", "2026M06"}
    with duckdb.connect(str(PATHS.warehouse), read_only=True) as connection:
        assert connection.execute("SELECT sum(scheduled_movements) FROM fact_domestic_scheduled_route_movements").fetchone()[0] == len(silver)
        assert connection.execute("SELECT count(*) FROM bridge_domestic_slot_lineage WHERE artifact_sha256 = ?", [source_hash]).fetchone()[0] == len(gold)
        assert connection.execute("SELECT count(*) FROM dim_source_artifact WHERE artifact_sha256 = ?", [source_hash]).fetchone()[0] == 1


def test_domestic_map_contains_routes_without_fabricating_passengers():
    payload = build_flight_payload()
    network = payload["domestic_networks"]["2026Q2"]
    assert network["mode"] == "scheduled_domestic"
    assert network["agent_eligible"] is False
    assert len(network["routes"]) == 56
    assert network["scheduled_movements"] == 31_098
    assert network["attributed_market_movements"] == 364
    assert network["presence_only_route_count"] == 8
    assert network["represented_movements"] == 31_462
    by_destination = {route["destination"]["iata"]: route for route in network["routes"]
                      if route["origin"]["iata"] == "MEX"}
    assert {code: by_destination[code]["departures"] for code in ("CUN", "MTY", "GDL")} == {
        "CUN": 2_704, "MTY": 2_510, "GDL": 2_030,
    }
    scheduled = [route for route in network["routes"] if route["operation_status"] == "assigned_slot_not_flown"]
    assert len(scheduled) == 45
    for route in scheduled:
        assert route["operation_status"] == "assigned_slot_not_flown"
        assert route["passengers"] is route["seats"] is route["load_factor"] is None
        assert sum(direction["departures"] for direction in route["directions"]) == route["departures"]
    consumer = integration_flight_payload(payload)
    assert len(consumer["domestic_networks"]["2026Q2"]["routes"]) == 56
    assert {item["airport_iata"] for item in consumer["route_networks"]["2026Q2"]["aena_airport_activity"]} == {"MAD", "BCN"}
