"""Official scheduling remains separate from performed traffic and passengers."""
import pytest
pytestmark = pytest.mark.local_data


def test_2026q2_offers_exactly_its_official_scheduling_months(flight_payload):
    monthly = flight_payload["domestic_monthly_networks"]
    assert sorted(monthly) == ["2026M04", "2026M05", "2026M06"]
    quarter = flight_payload["domestic_networks"]["2026Q2"]
    assert quarter["scheduled_movements"] == sum(
        route["departures"] for network in monthly.values() for route in network["routes"]
    )
    assert quarter["observed_months"] == []
    assert quarter["represented_movements"] is None


def test_no_seed_extension_to_unobserved_quarters(flight_payload):
    assert "2026Q1" not in flight_payload["domestic_networks"]
    assert "2026M07" not in flight_payload["domestic_monthly_networks"]
    for network in flight_payload["domestic_networks"].values():
        assert all(route["passengers"] is route["seats"] is route["load_factor"] is None
                   for route in network["routes"])
