import duckdb
import pytest

from src.dashboard.map_periods import period_months, retained_map_periods, refresh_network_availability


def test_retained_periods_include_old_observations_and_partial_july_but_not_capture_only_august():
    with duckdb.connect(":memory:") as connection:
        connection.execute("CREATE TABLE fact_route_traffic_summary AS SELECT '2015M01' AS period_id")
        connection.execute("CREATE TABLE fact_route_carrier_international_estimate AS SELECT '2026M07' AS period_id")
        connection.execute("CREATE TABLE fact_aeromexico_international_capacity_estimate AS SELECT '2026M08' AS period_id")
        periods = {r["period_id"]: r for r in retained_map_periods(connection)}
    assert set(periods) == {"2015M01", "2015Q1", "2026M07", "2026Q3"}
    assert periods["2026Q3"]["expected_months"] == ["2026M07", "2026M08", "2026M09"]
    assert periods["2026M07"]["expected_months"] == ["2026M07"]


@pytest.mark.parametrize("period", ["2026M00", "2026M13", "2026Q5", "2026"])
def test_invalid_map_dates_are_not_silently_coerced(period):
    with pytest.raises(ValueError):
        period_months(period)


def test_non_bts_july_is_available_without_claiming_complete_world_coverage():
    network = {"expected_months": ["2026M07"], "observed_months": [], "availability": "unavailable",
               "eligibility_reason": "T-100 no contiene meses del periodo seleccionado.",
               "routes": [{"departures": 12, "operation_status": "estimated_from_existing_seed"}],
               "agent_eligible": False}
    refresh_network_availability(network)
    assert network["availability"] == "partial"
    assert "T-100 no contiene" not in network["eligibility_reason"]
    assert network["agent_eligible"] is False


@pytest.mark.parametrize("months", [["2026M06"], ["2026M04", "2026M05", "2026M06"]])
def test_complete_observed_window_keeps_source_scope_and_historical_eligibility(months):
    from src.conversational_analytics.tools._route_contract import coverage

    network = dict(expected_months=months, observed_months=months, availability="complete",
                   routes=[dict(departures=0)], agent_eligible=False,
                   coverage="México–EE. UU.; cobertura parcial de la red mundial",
                   coverage_by_source={"BTS T-100": months},
                   eligibility_reason="Descarga posterior al corte histórico")
    refresh_network_availability(network)
    assert network["availability"] == "complete"
    assert coverage(network)["complete"] is True
    assert network["routes"][0]["departures"] == 0
    assert network["coverage"] == "México–EE. UU.; cobertura parcial de la red mundial"
    assert network["coverage_by_source"] == {"BTS T-100": months}
    assert network["agent_eligible"] is False
    assert network["eligibility_reason"] == "Descarga posterior al corte histórico"


@pytest.mark.parametrize("expected,observed,departures,status", [
    (["2026M04", "2026M05", "2026M06"], ["2026M04", "2026M05"], 12, "partial"),
    (["2026M07", "2026M08", "2026M09"], ["2026M07"], 0, "partial"),
    (["2026M07"], ["2026M07"], None, "unavailable"),
    (["2026M07"], [], None, "unavailable"),
    (["2026M07"], ["2026M06", "2026M07"], 12, "partial"),
    ([], [], 12, "partial"),
])
def test_availability_does_not_fill_missing_months_or_unknown_counts(expected, observed, departures, status):
    from src.conversational_analytics.tools._route_contract import coverage

    network = dict(expected_months=expected, observed_months=observed, routes=[dict(departures=departures)])
    refresh_network_availability(network)
    assert network["availability"] == status
    assert coverage(network)["complete"] is False
    assert network["expected_months"] == expected and network["observed_months"] == observed
    assert network["routes"][0]["departures"] is departures
