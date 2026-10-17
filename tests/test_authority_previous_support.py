"""Comparable authority observations retain their own year-ago map counts."""

import duckdb
import pandas as pd
import pytest

from src.dashboard.international_routes import extend_networks


@pytest.mark.parametrize(
    "source,foreign,country", [("anac", "GRU", "BR"), ("aerocivil", "BOG", "CO"), ("caa", "LHR", "GB")]
)
@pytest.mark.parametrize(
    "scenario", ["quarter_full", "quarter_current_partial", "quarter_prior_partial", "month_full"]
)
@pytest.mark.parametrize("previous_count", [0, 5])
def test_authority_previous_uses_complete_matching_source_cells(
    source, foreign, country, scenario, previous_count
):
    expected = ["2026M06"] if scenario == "month_full" else ["2026M04", "2026M05", "2026M06"]
    current_months = expected[:1] if scenario == "quarter_current_partial" else expected
    prior_months = [m.replace("2026", "2025") for m in expected]
    if scenario == "quarter_prior_partial":
        prior_months = prior_months[:2]
    rows = []
    for months, count in ((current_months, 10), (prior_months, previous_count)):
        for month in months:
            for origin, destination in (("MEX", foreign), (foreign, "MEX")):
                rows.append(
                    dict(
                        source_system=source,
                        observation_scope="carrier_route",
                        operator_icao="AMX",
                        period_id=month,
                        origin_iata=origin,
                        dest_iata=destination,
                        airport_iata=None,
                        departures=float(count),
                        passengers=float(count * 100),
                        seats=float(count * 120),
                        source_hash=month,
                        record_id=f"{month}:{origin}:{destination}",
                    )
                )
    observations = pd.DataFrame(rows)
    airports = pd.DataFrame(
        [
            dict(airport_iata=code, name=code, city=code, country=region, latitude=lat, longitude=lon)
            for code, region, lat, lon in [("MEX", "MX", 19, -99), (foreign, country, 1, 2)]
        ]
    )
    period = "2026M06" if scenario == "month_full" else "2026Q2"
    base = dict(period_label=period, expected_months=expected, observed_months=[], routes=[], airports=[])
    with duckdb.connect() as connection:
        connection.register("observations", observations)
        connection.execute("CREATE TABLE fact_international_route_observations AS SELECT * FROM observations")
        connection.register("airports", airports)
        connection.execute("CREATE TABLE dim_airport AS SELECT * FROM airports")
        expanded = extend_networks(connection, {period: base})[period]
    assert len(expanded["routes"]) == 1
    route = expanded["routes"][0]
    assert {k: route[k] for k in ("departures", "passengers", "seats")} == dict(
        departures=20 * len(current_months),
        passengers=2000 * len(current_months),
        seats=2400 * len(current_months),
    )
    assert sum(d["departures"] for d in route["directions"]) == route["departures"]
    assert route["operation_status"] == "operated_observed"
    assert all(
        c["source_label"]
        == {"anac": "Brasil · ANAC", "aerocivil": "Colombia · Aerocivil", "caa": "Reino Unido · CAA"}[source]
        for c in route["flight_components"]
    )
    if "partial" in scenario:
        assert route["previous"]["departures"] is None
    else:
        assert route["previous"]["departures"] == previous_count * 2 * len(expected)
        assert route["previous"]["passengers"] == previous_count * 200 * len(expected)
        assert route["previous"]["seats"] == previous_count * 240 * len(expected)
