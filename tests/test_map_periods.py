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
