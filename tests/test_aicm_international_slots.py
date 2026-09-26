"""The international AICM schedule adds destinations without duplicating observed routes."""

import hashlib

import duckdb
import pandas as pd
import pytest

from src.config import PATHS
from src.dashboard.international_routes import ESTIMATED_LABEL
from src.transform.aicm_international_slots import GOLD, SILVER, SOURCE

pytestmark = pytest.mark.local_data


def test_international_aicm_bronze_silver_gold_and_lineage():
    source_hash = hashlib.sha256(SOURCE.read_bytes()).hexdigest()
    silver = pd.read_parquet(SILVER)
    gold = pd.read_parquet(GOLD)
    assert not silver.duplicated([
        "flight_date", "origin_iata", "dest_iata", "flight_number",
        "flight_suffix", "assigned_time_utc",
    ]).any()
    assert int(gold.scheduled_movements.sum()) == len(silver) == 13_662
    assert gold.source_hash.eq(source_hash).all()
    assert gold.observation_status.eq("assigned_slot_not_flown").all()
    assert set(gold.period_id) == {"2026M04", "2026M05", "2026M06"}
    with duckdb.connect(str(PATHS.warehouse), read_only=True) as connection:
        assert connection.execute(
            "SELECT sum(scheduled_movements) FROM fact_aicm_international_scheduled_route_movements"
        ).fetchone()[0] == len(silver)
        assert connection.execute(
            "SELECT count(*) FROM bridge_aicm_international_slot_lineage WHERE artifact_sha256 = ?",
            [source_hash],
        ).fetchone()[0] == len(gold)


def test_international_map_adds_scheduled_destinations_with_observed_precedence(flight_payload):
    network = flight_payload["international_networks"]["2026Q2"]
    by_market = {route["market_key"]: route for route in network["routes"]}
    assert len(by_market) == len(network["routes"])
    sourced = [r for r in network["routes"] if r["source_label"] != ESTIMATED_LABEL]
    assert len(sourced) == 73
    estimate_available = any(r.get("passengers_estimated") for r in network["routes"])
    for market in ("MEX<>NRT", "ICN<>MEX", "MEX<>YYZ", "MAD<>MEX", "BCN<>MEX", "EZE<>MEX"):
        route = by_market[market]
        assert route["operation_status"] == "assigned_slot_not_flown"
        # Slots carry flights, never passengers or seats; where the private
        # estimate is present, passengers and seats come from it and are
        # labelled as estimated.
        if estimate_available:
            assert route["passengers_estimated"] is True and route["passengers"] > 0
            if route["capacity_estimated"]:
                assert route["seats"] > 0
                assert route["load_factor"] is None or 0 < route["load_factor"] <= 1
            else:
                assert route["seats"] is route["load_factor"] is None
        else:
            assert route["passengers"] is None
            assert route["seats"] is route["load_factor"] is None
        assert sum(direction["departures"] for direction in route["directions"]) == route["departures"]
    observed = by_market["LAX<>MEX"]
    assert observed["operation_status"] == "operated_observed"
    assert not observed.get("passengers_estimated")
    for route in network["routes"]:
        if route.get("passengers_estimated"):
            countries = {route["origin"]["country"], route["destination"]["country"]}
            assert "US" not in countries  # Mexico-US belongs to T-100, never to the estimate
    assert observed["scheduled_movements_q2"] > observed["departures"]
    assert all(route["agent_eligible"] is False for route in network["routes"] if route.get("operation_status") == "assigned_slot_not_flown")
