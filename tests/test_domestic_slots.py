"""Checks that scheduled AICM assignments stay distinct from performed traffic."""

from __future__ import annotations

import hashlib
import json

import duckdb
import pandas as pd
import pytest

from src.config import PATHS
from src.dashboard.domestic_routes import load_domestic_networks
from src.dashboard.flights_html import integration_flight_payload
from src.transform.domestic_slots import GOLD, SILVER, SOURCE


def _synthetic_domestic_connection(estimates: pd.DataFrame, capacity: pd.DataFrame) -> duckdb.DuckDBPyConnection:
    """An in-memory warehouse stand-in with only the Grupo Aeroméxico capacity tables.

    Lets the aggregation rules in ``domestic_routes.py`` be checked without the
    local-only warehouse (``data/warehouse.duckdb`` is not versioned; see
    ``AGENTS.md``).
    """

    connection = duckdb.connect(":memory:")
    airports = pd.DataFrame(
        [
            {"airport_iata": "MEX", "name": "Ciudad de México Intl.", "city": "Ciudad de México",
             "country": "México", "latitude": 19.4363, "longitude": -99.0721},
            {"airport_iata": "ABC", "name": "Aeropuerto de prueba", "city": "Testville",
             "country": "México", "latitude": 20.0, "longitude": -100.0},
        ]
    )
    connection.register("airports_df", airports)
    connection.execute("CREATE TABLE dim_airport AS SELECT * FROM airports_df")
    connection.register("estimates_df", estimates)
    connection.execute("CREATE TABLE fact_route_carrier_domestic_estimate AS SELECT * FROM estimates_df")
    connection.register("capacity_df", capacity)
    connection.execute("CREATE TABLE fact_aeromexico_domestic_capacity_estimate AS SELECT * FROM capacity_df")
    return connection


def _synthetic_estimate_rows(period: str, market_key: str) -> list[dict]:
    rows = []
    for origin, destination in [("MEX", "ABC"), ("ABC", "MEX")]:
        for carrier, passengers in [("AEROMEXICO", 1_000.0), ("AEROMEXICO_CONNECT", 500.0)]:
            rows.append(
                {
                    "period_id": period, "market_key": market_key,
                    "origin_iata": origin, "destination_iata": destination, "carrier_key": carrier,
                    "passengers_estimated": passengers, "passengers_estimated_low": passengers * 0.9,
                    "passengers_estimated_high": passengers * 1.1, "seed_weight": 1.0,
                    "support_observed_in_period": True, "support_source_periods": period,
                    "support_month_gap": 0, "support_repair_applied": False,
                }
            )
    return rows


def _capacity_row(period: str, market_key: str, origin: str, destination: str, carrier: str,
                   *, departures: float, seats: float, usable: bool = True) -> dict:
    return {
        "period_id": period, "market_key": market_key, "origin_iata": origin,
        "destination_iata": destination, "carrier_key": carrier,
        "departures_estimated": departures, "seats_estimated": seats,
        "seats_estimated_low": seats * 0.9, "seats_estimated_high": seats * 1.1,
        "aircraft_model_coverage": 1.0, "capacity_usable": usable,
        "sample_days": 7, "capacity_method": "synthetic_test",
    }


def test_paid_estimates_never_create_a_domestic_route():
    period = "2026M06"
    market = "ABC<>MEX"
    connection = _synthetic_domestic_connection(
        pd.DataFrame(_synthetic_estimate_rows(period, market)),
        pd.DataFrame([_capacity_row(period, market, "MEX", "ABC", "AEROMEXICO", departures=50, seats=10000)]),
    )
    assert load_domestic_networks(connection, [
        {"period_id": period, "period_label": "junio", "expected_months": [period]}
    ]) == {}


@pytest.mark.local_data
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


@pytest.mark.local_data
def test_domestic_map_keeps_official_slots_without_model_values(flight_payload):
    network = flight_payload["domestic_networks"]["2026Q2"]
    assert network["mode"] == "scheduled_domestic"
    assert network["observed_months"] == []
    gold = pd.read_parquet(GOLD)
    assert network["scheduled_movements"] == gold.scheduled_movements.sum()
    assert network["represented_movements"] is None
    for route in network["routes"]:
        assert route["operation_status"] == "assigned_slot_not_flown"
        assert route["passengers"] is route["seats"] is route["load_factor"] is None
        assert not route.get("passengers_estimated") and not route.get("capacity_estimated")
