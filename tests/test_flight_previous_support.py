"""Map rankings retain native previous counts only with comparable dated evidence."""

from copy import deepcopy

import duckdb
import pandas as pd
import pytest

from src.config import PATHS
from src.dashboard.flight_cells import apply_flight_cells, international_cells
from src.dashboard.route_entities import AEROMEXICO_ROUTES
from test_flight_cells import cell, endpoint


def cells(
    year,
    *,
    months=(4, 5, 6),
    carrier="AEROMEXICO",
    reverse=False,
    count=10,
    source="BTS T-100",
    kind="observed",
):
    return [
        cell(
            carrier=carrier,
            origin="JFK" if reverse else "MEX",
            dest="MEX" if reverse else "JFK",
            month=f"{year}M{m:02}",
            kind=kind,
            count=count,
            source=source,
        )
        for m in months
    ]


def network(previous=30, months=(4, 5, 6)):
    return dict(
        expected_months=[f"2026M{m:02}" for m in months],
        routes=[
            dict(
                market_key="JFK<>MEX",
                origin=endpoint("MEX"),
                destination=endpoint("JFK"),
                passengers=100,
                seats=120,
                departures=30,
                load_factor=5 / 6,
                directions=[],
                previous=dict(passengers=80, seats=110, departures=previous),
            )
        ],
    )


@pytest.mark.parametrize("months", [(4, 5, 6), (6,)])
@pytest.mark.parametrize("previous_count", [0, 10])
def test_complete_current_and_prior_evidence_preserves_native_count_and_known_zero(months, previous_count):
    current, prior = cells(2026, months=months), cells(2025, months=months, count=previous_count)
    n = network(previous=previous_count * len(months), months=months)
    previous_other_metrics = deepcopy(n["routes"][0]["previous"])
    apply_flight_cells(n, current, endpoint, previous_cells=prior)
    route = n["routes"][0]
    assert route["previous"] == previous_other_metrics
    assert route["departures"] == 10 * len(months)
    assert (route["passengers"], route["seats"], route["load_factor"]) == (100, 120, 5 / 6)


@pytest.mark.parametrize(
    "current,prior,previous_value",
    [
        (cells(2026, months=(4,)), cells(2025), 30),
        (cells(2026), cells(2025, months=(4,)), 10),
        (cells(2026), cells(2025, carrier="AEROMEXICO_CONNECT"), 30),
        (cells(2026), cells(2025, reverse=True), 30),
        (cells(2026), cells(2025, source="another source"), 30),
        (cells(2026), cells(2025, kind="estimated"), 30),
        (cells(2026), None, 30),
        (cells(2026), [], 0),
        (cells(2026), cells(2025), 31),
    ],
)
def test_unproved_previous_support_clears_only_the_flight_comparison(current, prior, previous_value):
    n = network(previous=previous_value)
    apply_flight_cells(n, current, endpoint, previous_cells=prior)
    route = n["routes"][0]
    assert route["previous"] == dict(passengers=80, seats=110, departures=None)
    assert (route["passengers"], route["seats"], route["load_factor"]) == (100, 120, 5 / 6)


@pytest.mark.local_data
def test_retained_q2_incomplete_directions_cannot_enter_map_change_rankings():
    from src.dashboard.flights import _load_routes
    from src.dashboard.international_routes import extend_networks
    from src.web_export.route_support import metric_support

    with duckdb.connect(str(PATHS.warehouse), read_only=True) as connection:
        native = _load_routes(connection, "2026Q2")
        expanded = extend_networks(connection, {"2026Q2": native})["2026Q2"]
        prior = international_cells(
            connection,
            ["2025M04", "2025M05", "2025M06"],
            AEROMEXICO_ROUTES,
            pd.DataFrame(),
            endpoint,
        )
    by_market = {r["market_key"]: r for r in expanded["routes"]}
    for route in native["routes"]:
        current = by_market[route["market_key"]]
        assert {k: current[k] for k in ("passengers", "seats", "departures")} == {
            k: route[k] for k in ("passengers", "seats", "departures")
        }
        if metric_support(expanded, current, "departures")[2]:
            assert current["previous"]["departures"] is None
    for market in ("LAX<>MEX", "JFK<>MEX"):
        assert metric_support(expanded, by_market[market], "departures")[2]
        assert by_market[market]["previous"]["departures"] is None
    kept = [r for r in expanded["routes"] if r["previous"]["departures"] is not None]
    assert kept  # Complete, matching BTS evidence still supports comparisons.
    assert prior  # The check uses retained source evidence, not an empty fallback.
