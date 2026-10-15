import pandas as pd
import duckdb

from src.dashboard.international_routes import _estimated_routes
from src.dashboard.international_routes import extend_networks


def test_july_estimate_is_partial_and_us_fallback_requires_explicit_opt_in():
    estimates = pd.DataFrame([{
        "period_id": "2026M07", "market_key": "JFK<>MEX", "origin_iata": "MEX",
        "destination_iata": "JFK", "carrier_key": "AEROMEXICO",
        "passengers_estimated": 100.0, "passengers_estimated_low": 80.0,
        "passengers_estimated_high": 120.0, "departures_estimated": 12.0,
        "estimator_version": "existing historical output",
    }])
    endpoint = lambda code: {"iata": code, "country": "US" if code == "JFK" else "MX"}
    months = ["2026M07", "2026M08", "2026M09"]
    assert not _estimated_routes(estimates, pd.DataFrame(), months, endpoint)
    route = _estimated_routes(estimates, pd.DataFrame(), months, endpoint, include_us=True)["JFK<>MEX"]
    assert route["months_covered"] == 1 and route["months_selected"] == 3
    assert [item["period_id"] for item in route["monthly"]] == ["2026M07"]
    assert route["monthly"][0]["departures"] == 12.0
    assert route["monthly"][0]["seats"] is None


def test_one_reported_direction_is_retained_without_inventing_the_return():
    observations = pd.DataFrame([{
        "source_system": "aerocivil", "observation_scope": "carrier_route", "operator_icao": "AMX",
        "period_id": "2026M07", "origin_iata": "MEX", "dest_iata": "BOG", "airport_iata": None,
        "departures": 3.0, "passengers": None, "seats": None,
        "source_hash": "official snapshot", "record_id": "one direction",
    }])
    airports = pd.DataFrame([{"airport_iata": code, "name": code, "city": code,
                              "country": country, "latitude": lat, "longitude": lon}
                             for code, country, lat, lon in [("MEX", "MX", 19, -99), ("BOG", "CO", 4, -74)]])
    with duckdb.connect(":memory:") as connection:
        connection.register("observations", observations)
        connection.execute("CREATE TABLE fact_international_route_observations AS SELECT * FROM observations")
        connection.register("airports", airports)
        connection.execute("CREATE TABLE dim_airport AS SELECT * FROM airports")
        network = {"expected_months": ["2026M07"], "observed_months": [], "routes": [], "airports": []}
        route = extend_networks(connection, {"2026M07": network})["2026M07"]["routes"][0]
    assert route["departures"] == 3
    assert len(route["directions"]) == 1
    assert route["previous"]["departures"] is None
    assert "parcial" in route["coverage_note"]
