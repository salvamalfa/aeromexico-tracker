import duckdb
import pandas as pd
import pytest

from src.dashboard.international_routes import extend_networks
from src.dashboard.map_periods import period_months


@pytest.mark.parametrize("period", ["2026M04", "2026Q2"])
def test_aicm_notes_describe_filtered_schedule_months(period):
    observed = pd.DataFrame([dict(
        operator_icao="AMX", observation_scope="carrier_route", source_system="caa",
        origin_iata="MEX", dest_iata="LHR", period_id="2026M04", departures=10,
        passengers=None, seats=None, source_hash="a", record_id="observed",
        airport_iata="LHR", metric_key="departures",
    )])
    scheduled = pd.DataFrame([dict(
        origin_iata="MEX", dest_iata=dest, period_id=month, scheduled_movements=20,
        observation_status="assigned_slot_not_flown", source_hash="b", record_id=month + dest,
    ) for month in ["2026M04", "2026M05", "2026M06"] for dest in ["MAD", "LHR"]])
    airports = pd.DataFrame([dict(
        airport_iata=code, latitude=1.0, longitude=1.0, name=code, city=code, country=country,
    ) for code, country in [("MEX", "MX"), ("MAD", "ES"), ("LHR", "GB")]])
    months = period_months(period)
    network = dict(expected_months=months, observed_months=[], routes=[], availability="unavailable")
    with duckdb.connect(":memory:") as connection:
        connection.register("fact_international_route_observations", observed)
        connection.register("fact_aicm_international_scheduled_route_movements", scheduled)
        connection.register("dim_airport", airports)
        result = extend_networks(connection, {period: network})[period]
    routes = {route["market_key"]: route for route in result["routes"]}
    listed = ", ".join(month[5:] for month in months)
    assert routes["MAD<>MEX"]["scheduled_months"] == months
    assert routes["MAD<>MEX"]["coverage_note"].startswith(f"Meses: {listed} · AICM")
    assert routes["MAD<>MEX"]["departures"] == 20 * len(months)
    assert f"AICM meses {listed}:" in routes["LHR<>MEX"]["coverage_note"]
    assert routes["LHR<>MEX"]["observed_months"] == ["2026M04"]
    assert routes["LHR<>MEX"]["departures"] == 10
