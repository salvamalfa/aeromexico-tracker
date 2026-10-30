"""Comparable authority observations retain their own year-ago map counts."""

import duckdb
import pandas as pd
import pytest

from src.dashboard.international_routes import extend_networks


def authority_observations(source, foreign, current_months, prior_months, previous_count):
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
    if source == "aerocivil":
        for row in rows:
            row.update(
                metric_key="operations",
                operations=row["departures"],
                departures=None,
                passengers=None,
                seats=None,
                load_factor=None,
                source_flight_type_code="S",
                source_traffic_code="I",
                commercial_designator_as_reported="AM",
                source_locator=f"synthetic:{row['record_id']}",
            )
    return pd.DataFrame(rows)


def expand(observations, foreign, country, period, expected):
    airports = pd.DataFrame(
        [
            dict(airport_iata=code, name=code, city=code, country=region, latitude=lat, longitude=lon)
            for code, region, lat, lon in [("MEX", "MX", 19, -99), (foreign, country, 1, 2)]
        ]
    )
    base = dict(period_label=period, expected_months=expected, observed_months=[], routes=[], airports=[])
    with duckdb.connect() as connection:
        connection.register("observations", observations)
        connection.execute("CREATE TABLE fact_international_route_observations AS SELECT * FROM observations")
        connection.register("airports", airports)
        connection.execute("CREATE TABLE dim_airport AS SELECT * FROM airports")
        return extend_networks(connection, {period: base})[period]


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
    observations = authority_observations(source, foreign, current_months, prior_months, previous_count)
    period = "2026M06" if scenario == "month_full" else "2026Q2"
    expanded = expand(observations, foreign, country, period, expected)
    assert len(expanded["routes"]) == 1
    route = expanded["routes"][0]
    if source == "aerocivil":
        movement = route["recorded_movements"]
        assert movement["count"] == 20 * len(current_months)  # Literal movements, never halved.
        assert movement["observed_months"] == sorted(current_months)
        assert len(movement["components"]) == 2 * len(current_months)
        assert all(c["operations"] == 10 for c in movement["components"])
        assert {c["period_id"] for c in movement["components"]} == set(current_months)
        assert movement["provisional"] is True
        assert movement["official_classification_confirmed"] is False
        assert movement["agent_eligible"] is False
        assert route["operation_status"] == "recorded_movements_provisional"
        assert route.get("flight_components", []) == []
        # A complete reporting window does not make movements comparable departures.
        for key in ("departures", "passengers", "seats"):
            assert route[key] is None and route["previous"][key] is None
            assert all(d[key] is None for d in route["directions"])
        assert expanded["coverage_by_source"][movement["source_label"]] == sorted(current_months)
        return
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


@pytest.mark.parametrize(
    "key,value",
    [
        ("departures", 10),
        ("passengers", 1000),
        ("seats", 1200),
        ("load_factor", 0.8),
        ("metric_key", "departures"),
        ("operations", None),
    ],
)
def test_aerocivil_previous_fixture_rejects_mistyped_or_missing_movements(key, value):
    observations = authority_observations("aerocivil", "BOG", ["2026M06"], ["2025M06"], 0)
    observations[key] = value
    with pytest.raises(ValueError, match="Aerocivil|movements"):
        expand(observations, "BOG", "CO", "2026M06", ["2026M06"])
