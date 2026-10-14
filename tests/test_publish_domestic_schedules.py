"""The withdrawal gate binds newly exposed schedules to unchanged source rows."""

from __future__ import annotations

import json
from pathlib import Path

import duckdb
import pandas as pd
import pytest

from src.dashboard.domestic_routes import load_domestic_monthly_networks, load_domestic_networks
from src.publish.domestic_schedules import require_domestic_gold_schedules
from src.web_export.flights import export_flights
from tests.test_web_export import _build_synthetic_raw_flight_payload


@pytest.fixture
def scheduled_candidate(tmp_path):
    gold = tmp_path / "gold"
    gold.mkdir()
    rows = []
    for airport, months in [("ABC", [4, 5, 6]), ("DEF", [4, 5])]:
        for month in months:
            for origin, destination in [("MEX", airport), (airport, "MEX")]:
                rows.append({
                    "period_id": f"2026M{month:02d}", "origin_iata": origin, "dest_iata": destination,
                    "scheduled_movements": 10, "carrier_code": "AM", "source_system": "aicm",
                    "observation_status": "assigned_slot_not_flown", "source_hash": "official",
                    "source_url": "https://www.aicm.com.mx/", "record_id": f"{month}-{origin}-{destination}",
                })
    observations = pd.DataFrame(rows)
    airports = pd.DataFrame([
        {"airport_iata": code, "name": code, "city": code, "country": "México",
         "latitude": 20.0, "longitude": -100.0} for code in ["MEX", "ABC", "DEF"]
    ])
    observations.to_parquet(gold / "fact_domestic_scheduled_route_movements.parquet", index=False)
    airports.to_parquet(gold / "dim_airport.parquet", index=False)
    raw = _build_synthetic_raw_flight_payload()
    with duckdb.connect(":memory:") as connection:
        connection.register("observations", observations)
        connection.register("airports", airports)
        connection.execute("CREATE TABLE fact_domestic_scheduled_route_movements AS SELECT * FROM observations")
        connection.execute("CREATE TABLE dim_airport AS SELECT * FROM airports")
        raw["domestic_networks"] = load_domestic_networks(connection, raw["quarters"])
        raw["domestic_monthly_networks"] = load_domestic_monthly_networks(connection)
    candidate = tmp_path / "candidate"
    export_flights(raw, candidate / "data/v1", skip_input_check=True)
    baseline = tmp_path / "baseline"
    target = baseline / "data/v1/flights/quarters.json"
    target.parent.mkdir(parents=True)
    prior = json.loads((candidate / "data/v1/flights/quarters.json").read_text())
    prior["available_periods"]["domestic"] = []
    prior["available_periods"]["domestic_monthly"] = ["2026M03", "2026M04", "2026M05", "2026M06", "2026M07"]
    target.write_text(json.dumps(prior))
    return baseline, candidate, gold


def test_pinned_gold_accepts_native_and_monthly_schedules_with_partial_route_coverage(scheduled_candidate):
    baseline, candidate, gold = scheduled_candidate
    require_domestic_gold_schedules(baseline, candidate, gold)
    network = json.loads((candidate / "data/v1/flights/domestic/2026Q2.json").read_text())
    seasonal = next(route for route in network["routes"] if route["market_key"] == "DEF<>MEX")
    assert seasonal["departures"] == 40
    assert seasonal["coverage_note"] == "Meses programados: 04, 05 · AICM · ejecución sin verificar"


@pytest.mark.parametrize("change", [
    "departures", "direction_redistribution", "passengers", "coverage", "geography",
    "other_entity", "missing_period", "missing_route", "international_listing", "source", "performed",
])
def test_domestic_gold_guard_rejects_fabricated_values_coverage_or_periods(scheduled_candidate, change):
    baseline, candidate, gold = scheduled_candidate
    target = candidate / "data/v1/flights/domestic/2026Q2.json"
    network = json.loads(target.read_text())
    route = next(route for route in network["routes"] if route["market_key"] == "DEF<>MEX")
    if change == "departures":
        route["departures"] += 1
    elif change == "direction_redistribution":
        route["directions"][0]["departures"] += 1
        route["directions"][1]["departures"] -= 1
    elif change == "passengers":
        route["passengers"] = 1
    elif change == "coverage":
        route["coverage_note"] = "Meses programados: 04, 05, 06 · AICM · ejecución sin verificar"
    elif change == "geography":
        route["destination"]["lat"] += 1
    elif change == "source":
        network["source_url"] = "https://example.invalid/"
    elif change == "performed":
        route["operation_status"] = "operated_observed"
    elif change == "missing_route":
        network["routes"].remove(route)
    elif change == "other_entity":
        extra = candidate / "data/v1/flights/entities/VOLARIS/domestic/2026Q2.json"
        extra.parent.mkdir(parents=True)
        extra.write_text(json.dumps(network))
    elif change == "missing_period":
        (candidate / "data/v1/flights/domestic/2026M05.json").unlink()
    elif change == "international_listing":
        listing = candidate / "data/v1/flights/quarters.json"
        document = json.loads(listing.read_text())
        document["available_periods"]["international"] = []
        listing.write_text(json.dumps(document))
    target.write_text(json.dumps(network))
    with pytest.raises(ValueError, match="Domestic|Flight period"):
        require_domestic_gold_schedules(baseline, candidate, gold)
