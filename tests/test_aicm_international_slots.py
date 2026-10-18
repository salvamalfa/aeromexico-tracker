"""The international AICM schedule adds destinations without duplicating observed routes."""

import hashlib

import duckdb
import pandas as pd
import pytest

from src.config import PATHS
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
    # Source labels no longer identify a whole route as one evidence class:
    # a single market can contain observed, estimated and scheduled cells.
    with duckdb.connect(str(PATHS.warehouse), read_only=True) as connection:
        has_estimate = connection.execute("SELECT count(*) FROM information_schema.tables WHERE table_name='fact_route_carrier_international_estimate'").fetchone()[0]
        seeds = connection.execute("""
            SELECT carrier_key, period_id, origin_iata, destination_iata,
                   departures_estimated
            FROM fact_route_carrier_international_estimate
            WHERE carrier_key IN ('AEROMEXICO', 'AEROMEXICO_CONNECT')
              AND period_id IN ('2026M04', '2026M05', '2026M06')
        """).df() if has_estimate else pd.DataFrame(columns=[
            "carrier_key", "period_id", "origin_iata", "destination_iata", "departures_estimated"
        ])
    seed_counts = seeds.set_index([
        "carrier_key", "period_id", "origin_iata", "destination_iata"
    ]).departures_estimated.to_dict()
    isolated = by_market["BOG<>TGZ"]
    assert isolated["departures"] == 1 and len(isolated["directions"]) == 1
    assert "parcial" in isolated["coverage_note"]
    estimate_available = any(r.get("passengers_estimated") for r in network["routes"])
    for market in ("MEX<>NRT", "ICN<>MEX", "MEX<>YYZ", "MAD<>MEX", "BCN<>MEX", "EZE<>MEX"):
        route = by_market[market]
        assert "AICM" in route["coverage_note"]
        components = route["flight_components"]
        assert not any(cell["kind"] == "observed" for cell in components)
        frequency_cells = [cell for cell in components if cell["kind"] == "estimated"]
        if frequency_cells:
            assert route["operation_status"].startswith("estimated_")
            assert route["departures"] == pytest.approx(sum(cell["departures"] for cell in frequency_cells))
            for cell in frequency_cells:
                key = tuple(cell[k] for k in ("carrier_key", "period_id", "origin_iata", "destination_iata"))
                assert cell["departures"] == pytest.approx(seed_counts[key])
        else:
            assert route["operation_status"] == "assigned_slot_not_flown"
            assert all(cell["kind"] == "scheduled" for cell in components)
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
    components = observed["flight_components"]
    assert observed["departures"] == sum(cell["departures"] for cell in components if cell["kind"] == "observed")
    actual_cells = {(cell["period_id"], cell["origin_iata"], cell["destination_iata"])
                    for cell in components if cell["kind"] == "observed"}
    assert all((cell["period_id"], cell["origin_iata"], cell["destination_iata"]) not in actual_cells
               for cell in components if cell["kind"] == "scheduled")
    for route in network["routes"]:
        if route.get("passengers_estimated"):
            countries = {route["origin"]["country"], route["destination"]["country"]}
            assert "US" not in countries  # Mexico-US belongs to T-100, never to the estimate
    assert observed["scheduled_movements_q2"] > observed["departures"]
    assert all(route["agent_eligible"] is False for route in network["routes"] if route.get("operation_status") == "assigned_slot_not_flown")
