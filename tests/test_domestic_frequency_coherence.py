"""Retained monthly flight admission stays additive at every display grain."""

from __future__ import annotations

import pandas as pd
import pytest

from src.dashboard.domestic_routes import load_domestic_networks
from tests.test_domestic_slots import (
    _capacity_row,
    _synthetic_domestic_connection,
    _synthetic_estimate_rows,
)


def _month(period: str, *, incomplete_direction: str | None) -> tuple[list[dict], list[dict]]:
    estimates = _synthetic_estimate_rows(period, "ABC<>MEX")
    capacity = []
    weights = {
        ("MEX", "AEROMEXICO"): 100.0,
        ("MEX", "AEROMEXICO_CONNECT"): 25.0,
        ("ABC", "AEROMEXICO"): 77.0,
        ("ABC", "AEROMEXICO_CONNECT"): 48.0,
    }
    for row in estimates:
        row["seed_weight"] = weights[(row["origin_iata"], row["carrier_key"])]
        usable = not (row["origin_iata"] == incomplete_direction and row["carrier_key"] == "AEROMEXICO")
        # A complete direction's model-supported count is four below its seed.
        # The aggregate cannot retrospectively validate those four identities.
        departures = row["seed_weight"] - (4 if row["carrier_key"] == "AEROMEXICO" else 0)
        capacity.append(
            _capacity_row(
                period,
                "ABC<>MEX",
                row["origin_iata"],
                row["destination_iata"],
                row["carrier_key"],
                departures=departures if usable else float("nan"),
                seats=departures * 180 if usable else float("nan"),
                usable=usable,
            )
        )
    return estimates, capacity


def _period(period: str, months: list[str]) -> dict:
    return {"period_id": period, "period_label": period, "expected_months": months}


@pytest.mark.parametrize("incomplete_direction", ["MEX", "ABC"])
def test_incomplete_month_keeps_existing_250_and_its_breakdown(incomplete_direction):
    estimates, capacity = _month("2026M06", incomplete_direction=incomplete_direction)
    with _synthetic_domestic_connection(pd.DataFrame(estimates), pd.DataFrame(capacity)) as connection:
        network = load_domestic_networks(connection, [_period("2026M06", ["2026M06"])])["2026M06"]
    route = network["routes"][0]
    # This repairs the retained 250-versus-246 disagreement, not the network total.
    assert network["represented_departures_estimated"] == route["departures"] == 250
    assert sum(row["departures"] for row in route["monthly"]) == 250
    assert sum(row["departures"] for row in route["directions"]) == 250
    assert [row["departures"] for row in route["monthly"]] == [125, 125]
    assert route["seats"] is None
    assert route["capacity_complete"] is False
    assert route["agent_eligible"] is False


def test_complete_month_does_not_admit_previously_withheld_seed_frequencies():
    estimates, capacity = _month("2026M04", incomplete_direction=None)
    with _synthetic_domestic_connection(pd.DataFrame(estimates), pd.DataFrame(capacity)) as connection:
        route = load_domestic_networks(connection, [_period("2026M04", ["2026M04"])])["2026M04"]["routes"][0]
    assert sum(row["seed_weight"] for row in estimates) == 250
    assert route["departures"] == 242
    assert sum(row["departures"] for row in route["monthly"]) == 242
    assert sum(row["departures"] for row in route["directions"]) == 242
    assert route["capacity_complete"] is True


@pytest.mark.parametrize("incomplete_direction", ["MEX", "ABC"])
def test_quarter_adds_retained_months_without_rechoosing_frequency_basis(incomplete_direction):
    april, april_capacity = _month("2026M04", incomplete_direction=None)
    june, june_capacity = _month("2026M06", incomplete_direction=incomplete_direction)
    selections = [
        _period("2026M04", ["2026M04"]),
        _period("2026M06", ["2026M06"]),
        _period("2026Q2", ["2026M04", "2026M05", "2026M06"]),
    ]
    with _synthetic_domestic_connection(
        pd.DataFrame(april + june), pd.DataFrame(april_capacity + june_capacity)
    ) as connection:
        networks = load_domestic_networks(connection, selections)
    quarter = networks["2026Q2"]["routes"][0]
    monthly_routes = [networks[month]["routes"][0] for month in ("2026M04", "2026M06")]
    assert [route["departures"] for route in monthly_routes] == [242, 250]
    assert quarter["departures"] == 492
    assert quarter["departures"] == sum(route["departures"] for route in monthly_routes)
    assert quarter["departures"] == sum(row["departures"] for row in quarter["directions"])
    assert quarter["departures"] == sum(row["departures"] for row in quarter["monthly"])
    for direction in quarter["directions"]:
        source_rows = [
            row
            for route in monthly_routes
            for row in route["monthly"]
            if row["origin_iata"] == direction["origin_iata"]
        ]
        assert direction["departures"] == sum(row["departures"] for row in source_rows)
    assert quarter["months_selected"] == 3
    assert quarter["months_covered"] == 2
    assert quarter["capacity_complete"] is False


def test_borrowed_support_never_turns_into_frequency_or_zero():
    estimates, capacity = _month("2026M06", incomplete_direction="ABC")
    for row in estimates:
        row.update(
            support_observed_in_period=False,
            support_month_gap=1,
            support_source_periods="2026M05",
            support_repair_applied=True,
        )
    with _synthetic_domestic_connection(pd.DataFrame(estimates), pd.DataFrame(capacity)) as connection:
        route = load_domestic_networks(connection, [_period("2026M06", ["2026M06"])])["2026M06"]["routes"][0]
    assert route["departures"] is None
    assert all(row["departures"] is None for row in route["monthly"])
    assert all(row["departures"] is None for row in route["directions"])
    assert route["flight_count_partial"] is True
