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


def test_group_capacity_survives_a_single_carrier_without_invalidating_the_route():
    """A market where only Aerovías (never Connect) is present in the AeroDataBox
    capacity fact for one direction must still report Grupo Aeroméxico seats and
    departures for that direction, instead of falling back to N/D."""

    period = "2026M06"
    market_key = "<>".join(sorted(("MEX", "ABC")))
    estimates = pd.DataFrame(_synthetic_estimate_rows(period, market_key))
    capacity = pd.DataFrame(
        [
            # MEX -> ABC: only Aerovías de México observed by AeroDataBox.
            _capacity_row(period, market_key, "MEX", "ABC", "AEROMEXICO", departures=50.0, seats=10_000.0),
            # ABC -> MEX: both carriers observed.
            _capacity_row(period, market_key, "ABC", "MEX", "AEROMEXICO", departures=30.0, seats=6_000.0),
            _capacity_row(period, market_key, "ABC", "MEX", "AEROMEXICO_CONNECT", departures=20.0, seats=4_000.0),
        ]
    )
    connection = _synthetic_domestic_connection(estimates, capacity)
    quarters = [{"period_id": period, "period_label": "junio 2026", "expected_months": [period]}]
    route = load_domestic_networks(connection, quarters)[period]["routes"][0]

    assert route["capacity_complete"] is True
    assert route["passengers"] == pytest.approx(3_000.0)
    # Both directions' capacity summed at the Grupo Aeroméxico level, without
    # requiring both filiales to have their own capacity row.
    assert route["seats"] == pytest.approx(20_000.0)
    assert route["departures"] == pytest.approx(100.0)
    assert route["load_factor"] == pytest.approx(3_000.0 / 20_000.0)
    directions = {(d["origin_iata"], d["destination_iata"]): d for d in route["directions"]}
    assert directions[("MEX", "ABC")]["capacity_complete"] is True
    assert directions[("MEX", "ABC")]["seats"] == pytest.approx(10_000.0)
    assert directions[("MEX", "ABC")]["departures"] == pytest.approx(50.0)
    assert {item["carrier_label"] for item in route["monthly"]} == {"Grupo Aeroméxico"}


def test_group_capacity_sums_both_carriers_exactly_once():
    """When both filiales have AeroDataBox capacity for the same direction/month,
    Grupo Aeroméxico totals must be their sum, not a duplicate or a single one."""

    period = "2026M06"
    market_key = "<>".join(sorted(("MEX", "ABC")))
    estimates = pd.DataFrame(_synthetic_estimate_rows(period, market_key))
    capacity = pd.DataFrame(
        [
            _capacity_row(period, market_key, "MEX", "ABC", "AEROMEXICO", departures=40.0, seats=8_000.0),
            _capacity_row(period, market_key, "MEX", "ABC", "AEROMEXICO_CONNECT", departures=10.0, seats=1_000.0),
            _capacity_row(period, market_key, "ABC", "MEX", "AEROMEXICO", departures=40.0, seats=8_000.0),
            _capacity_row(period, market_key, "ABC", "MEX", "AEROMEXICO_CONNECT", departures=10.0, seats=1_000.0),
        ]
    )
    connection = _synthetic_domestic_connection(estimates, capacity)
    quarters = [{"period_id": period, "period_label": "junio 2026", "expected_months": [period]}]
    route = load_domestic_networks(connection, quarters)[period]["routes"][0]

    assert route["seats"] == pytest.approx(2 * (8_000.0 + 1_000.0))
    assert route["departures"] == pytest.approx(2 * (40.0 + 10.0))


def test_load_factor_above_100_percent_is_nd_but_keeps_flights_and_seats():
    """An implausible estimated point (>100% occupancy) must hide the load factor
    only; flights and seats must be preserved exactly as estimated, per AGENTS.md
    ("no conviertas un faltante en cero")."""

    period = "2026M06"
    market_key = "<>".join(sorted(("MEX", "ABC")))
    rows = []
    for origin, destination in [("MEX", "ABC"), ("ABC", "MEX")]:
        for carrier, passengers in [("AEROMEXICO", 100_000.0), ("AEROMEXICO_CONNECT", 50_000.0)]:
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
    estimates = pd.DataFrame(rows)
    capacity = pd.DataFrame(
        [
            _capacity_row(period, market_key, origin, destination, carrier, departures=dep, seats=seats)
            for origin, destination in [("MEX", "ABC"), ("ABC", "MEX")]
            for carrier, dep, seats in [("AEROMEXICO", 5.0, 1_000.0), ("AEROMEXICO_CONNECT", 3.0, 500.0)]
        ]
    )
    connection = _synthetic_domestic_connection(estimates, capacity)
    quarters = [{"period_id": period, "period_label": "junio 2026", "expected_months": [period]}]
    route = load_domestic_networks(connection, quarters)[period]["routes"][0]

    assert route["capacity_complete"] is True
    assert route["seats"] == pytest.approx(3_000.0)
    assert route["departures"] == pytest.approx(16.0)
    assert route["load_factor"] is None
    assert route["load_factor_status"] == "inconsistent_inputs"


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
def test_domestic_map_shows_reconciled_estimates_for_every_queried_month(flight_payload):
    payload = flight_payload
    network = payload["domestic_networks"]["2026Q2"]
    assert network["mode"] == "estimated_domestic"
    assert network["agent_eligible"] is False
    assert len(network["routes"]) == 56
    assert network["represented_passengers"] == pytest.approx(3_831_996.712046853)
    assert network["represented_movements"] is None
    assert network["represented_departures_estimated"] > 0
    assert network["availability"] == "complete"
    assert set(payload["domestic_monthly_networks"]) == {
        "2026M03", "2026M04", "2026M05", "2026M06", "2026M07",
    }
    assert all(route["passengers_estimated"] for route in network["routes"])
    assert all(route["passengers"] > 0 for route in network["routes"])
    assert network["capacity_complete_route_count"] > 0
    assert network["load_factor_route_count"] > 0
    assert any(route["departures"] is not None and route["seats"] is not None
               for route in network["routes"])
    assert all(route["load_factor"] is None or 0 <= route["load_factor"] <= 1
               for route in network["routes"])
    dual_operator = next(route for route in network["routes"] if route["market_key"] == "MEX<>MTY")
    assert {item["carrier_label"] for item in dual_operator["monthly"]} == {
        "Grupo Aeroméxico",
    }
    june = payload["domestic_monthly_networks"]["2026M06"]
    gdl = next(route for route in june["routes"] if route["market_key"] == "GDL<>MEX")
    assert gdl["departures"] == pytest.approx(745.0)
    assert gdl["seats"] == pytest.approx(131_925.8)
    assert gdl["load_factor"] == pytest.approx(gdl["passengers"] / gdl["seats"])
    assert {item["carrier_label"] for item in gdl["monthly"]} == {
        "Grupo Aeroméxico",
    }
    assert all(item["capacity_complete"] for item in gdl["monthly"])
    consumer = integration_flight_payload(payload)
    assert consumer["domestic_networks"] == {}
    assert set(consumer["domestic_monthly_networks"]) == set(payload["domestic_monthly_networks"])
    assert consumer["domestic_monthly_networks"]["2026M07"]["routes"][0]["passengers_estimated"] is True
    assert {item["airport_iata"] for item in consumer["route_networks"]["2026Q2"]["aena_airport_activity"]} == {"MAD", "BCN"}
