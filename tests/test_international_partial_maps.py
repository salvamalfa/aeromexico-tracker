import pandas as pd
import duckdb
import pytest

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


@pytest.mark.parametrize("enrich", [False, True])
def test_one_reported_direction_is_retained_without_inventing_the_return(enrich):
    observations = pd.DataFrame([{
        "source_system": "aerocivil", "observation_scope": "carrier_route", "operator_icao": "AMX",
        "period_id": "2026M07", "origin_iata": "MEX", "dest_iata": "BOG", "airport_iata": None,
        "departures": None, "operations": 3.0, "metric_key": "operations",
        "source_flight_type_code": "S", "source_traffic_code": "I",
        "commercial_designator_as_reported": "AMX", "source_locator": "record:1",
        "passengers": None, "seats": None, "load_factor": None,
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
        if enrich:
            estimates = pd.DataFrame([{
                "period_id": "2026M07", "market_key": "BOG<>MEX", "origin_iata": origin,
                "destination_iata": destination, "carrier_key": "AEROMEXICO",
                "passengers_estimated": passengers, "passengers_estimated_low": passengers * .8,
                "passengers_estimated_high": passengers * 1.2, "departures_estimated": 12.,
                "estimator_version": "existing historical output",
            } for origin, destination, passengers in [("MEX", "BOG", 100.), ("BOG", "MEX", 200.)]])
            connection.register("estimates", estimates)
            connection.execute("CREATE TABLE fact_route_carrier_international_estimate AS SELECT * FROM estimates")
        network = {"period_label": "julio 2026", "expected_months": ["2026M07"], "observed_months": [], "routes": [], "airports": []}
        expanded = extend_networks(connection, {"2026M07": network})
        route = expanded["2026M07"]["routes"][0]
    assert route["departures"] == (24 if enrich else None)
    assert route["recorded_movements"]["count"] == 3
    assert len(route["directions"]) == (2 if enrich else 1)
    assert route["previous"]["departures"] is None
    assert "parcial" in route["coverage_note"]
    from src.dashboard.flights_html import integration_flight_payload
    normalized = integration_flight_payload({"schema_version": "flight_dashboard_payload_v1",
        "metadata": {}, "quarters": [], "monthly_passengers": {}, "route_network": {"world_geometry": {}},
        "route_networks": {}, "international_networks": expanded})["route_networks"]["2026M07"]["routes"][0]
    if enrich:
        assert sum(item["departures"] for item in normalized["directions"]) == normalized["departures"]
    else:
        assert all(item["departures"] is None for item in normalized["directions"])
    observed = [c for c in normalized.get("flight_components", []) if c["kind"] == "observed"]
    assert [(c["origin_iata"], c["destination_iata"], c["departures"]) for c in observed] == []
    if not enrich:
        assert len(normalized["directions"]) == 1
    else:
        # The return is retained estimated evidence, never a fabricated observation.
        assert normalized["operation_status"] == "estimated_from_retained_frequencies"
        assert [(c["origin_iata"], c["destination_iata"], c["departures"]) for c in normalized["flight_components"] if c["kind"] == "estimated"] == [("BOG", "MEX", 12), ("MEX", "BOG", 12)]
    if enrich:
        assert normalized["passengers_estimated"] is True
        assert normalized["passengers"] == 100
        assert [(item["origin_iata"], item["destination_iata"]) for item in normalized["monthly"]] == [("MEX", "BOG")]
