"""Checks that scheduled AICM assignments stay distinct from performed traffic."""

from __future__ import annotations

import hashlib
import json

import duckdb
import pandas as pd
import pytest

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


def test_domestic_map_shows_reconciled_estimates_for_every_queried_month():
    payload = build_flight_payload()
    network = payload["domestic_networks"]["2026Q2"]
    assert network["mode"] == "estimated_domestic"
    assert network["agent_eligible"] is False
    assert len(network["routes"]) == 56
    assert network["represented_passengers"] == pytest.approx(3_831_996.712046853)
    assert network["represented_movements"] is None
    assert network["availability"] == "complete"
    assert set(payload["domestic_monthly_networks"]) == {
        "2026M03", "2026M04", "2026M05", "2026M06", "2026M07",
    }
    assert all(route["passengers_estimated"] for route in network["routes"])
    assert all(route["passengers"] > 0 for route in network["routes"])
    assert all(route["departures"] is route["seats"] is route["load_factor"] is None
               for route in network["routes"])
    dual_operator = next(route for route in network["routes"] if route["market_key"] == "MEX<>MTY")
    assert {item["carrier_label"] for item in dual_operator["monthly"]} == {
        "Aerovías de México", "Aeroméxico Connect",
    }
    consumer = integration_flight_payload(payload)
    assert consumer["domestic_networks"] == {}
    assert set(consumer["domestic_monthly_networks"]) == set(payload["domestic_monthly_networks"])
    assert consumer["domestic_monthly_networks"]["2026M07"]["routes"][0]["passengers_estimated"] is True
    assert {item["airport_iata"] for item in consumer["route_networks"]["2026Q2"]["aena_airport_activity"]} == {"MAD", "BCN"}
