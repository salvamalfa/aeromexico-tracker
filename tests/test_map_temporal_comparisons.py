"""Temporal completeness must preserve retrospective international comparisons."""

import pytest

from test_chat_route_tools import MemorySnapshot, _network, _paths, _route
from src.conversational_analytics.tools.routes import RouteTools


@pytest.mark.parametrize(
    "period,previous",
    [
        ("2026M06", "2026M05"),  # MoM
        ("2026M06", "2025M06"),  # monthly YoY
        ("2026Q2", "2025Q2"),  # quarterly YoY
    ],
)
def test_refreshed_international_observed_windows_keep_change_rankings(period, previous):
    from src.dashboard.map_periods import period_months, refresh_network_availability

    payloads = {}
    for selected, value in ((period, 120), (previous, 100)):
        route = _route("LAX<>MEX", value, kind="observed", source="BTS T-100")
        route["departures"] = value
        zero = _route("JFK<>MEX", 0, kind="observed", source="BTS T-100")
        zero["departures"] = 0
        routes = [route, zero]
        if selected == previous:
            routes.append(_route("MEX<>SEA", 10, kind="observed", source="BTS T-100"))
        network = _network(selected, routes, eligible=False)
        network.update(
            expected_months=period_months(selected),
            observed_months=period_months(selected),
            coverage="México–EE. UU.; la red mundial sigue parcial",
        )
        refresh_network_availability(network)
        payloads[("AEROMEXICO_GROUP", "international", selected)] = network
    tools = RouteTools(MemorySnapshot(_paths(payloads)))
    result = tools.invoke(
        "query_routes",
        dict(
            entity_id="AEROMEXICO_GROUP",
            segment="international",
            period=period,
            comparison_period=previous,
            metric="departures",
            order_by="absolute_change",
        ),
    )
    assert [r["market_key"] for r in result["rows"]] == ["LAX<>MEX", "JFK<>MEX"]
    assert result["rows"][0]["comparison"]["available"] is True
    assert result["rows"][0]["comparison"]["absolute_change"] == 20
    assert result["rows"][0]["comparison"]["relative_change_percent"] == 20
    assert result["rows"][1]["value"] == 0
    assert result["rows"][1]["comparison"]["value"] == 0
    assert result["coverage"][period]["complete"] is True
    assert result["coverage"][period]["agent_eligible"] is False
    current = payloads[("AEROMEXICO_GROUP", "international", period)]
    current["observed_months"] = []
    refresh_network_availability(current)
    incomplete = tools.invoke(
        "query_routes",
        dict(
            entity_id="AEROMEXICO_GROUP",
            segment="international",
            period=period,
            comparison_period=previous,
            metric="departures",
            order_by="absolute_change",
        ),
    )
    assert incomplete["rows"] == []
    assert incomplete["coverage"][period]["complete"] is False


def _cells(period, indices=None, *, carrier="AEROMEXICO", reverse=False, value=20, kind="observed"):
    from src.dashboard.map_periods import period_months

    months = period_months(period)
    return [
        dict(
            carrier_key=carrier,
            origin_iata="LAX" if reverse else "MEX",
            destination_iata="MEX" if reverse else "LAX",
            period_id=months[i],
            departures=value,
            kind=kind,
            source_label="BTS T-100",
            source_hashes=[],
        )
        for i in (range(len(months)) if indices is None else indices)
    ]


def _route_tools_with_cells(current, previous, *, period="2026Q2", comparison="2025Q2", monthly=None):
    from src.dashboard.map_periods import period_months, refresh_network_availability

    payloads = {}
    for selected, cells in ((period, current), (comparison, previous)):
        route = _route("LAX<>MEX", 100, kind="observed", source="BTS T-100")
        active = [c for c in cells if c["kind"] != "scheduled"] or cells
        route.update(departures=sum(c["departures"] for c in active), flight_components=cells)
        if monthly is not None:
            route["monthly"] = monthly[selected]
        network = _network(selected, [route], eligible=False)
        network.update(expected_months=period_months(selected), observed_months=period_months(selected))
        refresh_network_availability(network)
        payloads[("AEROMEXICO_GROUP", "international", selected)] = network
    return RouteTools(MemorySnapshot(_paths(payloads)))


def _compare(tools, *, period="2026Q2", comparison="2025Q2", metric="departures", order="value"):
    return tools.invoke(
        "query_routes",
        dict(
            entity_id="AEROMEXICO_GROUP",
            segment="international",
            period=period,
            comparison_period=comparison,
            metric=metric,
            order_by=order,
        ),
    )


@pytest.mark.parametrize("current_indices,previous_indices", [([0], [0, 1, 2]), ([0], [0])])
def test_quarterly_route_partial_months_never_become_complete_comparisons(current_indices, previous_indices):
    tools = _route_tools_with_cells(_cells("2026Q2", current_indices), _cells("2025Q2", previous_indices))
    result = _compare(tools)
    comparison = result["rows"][0]["comparison"]
    assert result["coverage"]["2026Q2"]["complete"] is True
    assert comparison["available"] is False and comparison["absolute_change"] is None
    assert "parcial" in comparison["reason"]
    assert _compare(tools, order="absolute_change")["rows"] == []
    assert _compare(tools, order="relative_change")["rows"] == []


@pytest.mark.parametrize("extra", ["operator", "direction"])
def test_each_operator_and_direction_requires_every_quarter_month(extra):
    prior = _cells("2025Q2") + _cells(
        "2025Q2",
        carrier="AEROMEXICO_CONNECT" if extra == "operator" else "AEROMEXICO",
        reverse=extra == "direction",
    )
    current = _cells("2026Q2") + _cells(
        "2026Q2",
        [0],
        carrier="AEROMEXICO_CONNECT" if extra == "operator" else "AEROMEXICO",
        reverse=extra == "direction",
    )
    result = _compare(_route_tools_with_cells(current, prior))
    assert result["rows"][0]["comparison"]["available"] is False
    assert "operador o sentido" in result["rows"][0]["comparison"]["reason"]


@pytest.mark.parametrize("changed", ["operator", "direction"])
def test_full_windows_require_same_operators_and_directions(changed):
    current = _cells(
        "2026Q2",
        carrier="AEROMEXICO_CONNECT" if changed == "operator" else "AEROMEXICO",
        reverse=changed == "direction",
    )
    result = _compare(_route_tools_with_cells(current, _cells("2025Q2")))
    assert result["rows"][0]["comparison"]["available"] is False
    assert "Cambió el conjunto" in result["rows"][0]["comparison"]["reason"]


def test_programming_does_not_fill_the_missing_observed_month_for_comparison():
    current = _cells("2026Q2", [0, 1]) + _cells("2026Q2", [2], kind="scheduled")
    result = _compare(_route_tools_with_cells(current, _cells("2025Q2")))
    assert result["rows"][0]["value_kind"] == "observed"
    assert result["rows"][0]["comparison"]["available"] is False


@pytest.mark.parametrize("period,comparison", [("2026M06", "2026M05"), ("2026M06", "2025M06")])
def test_explicit_zero_cell_is_comparable_but_absent_cell_is_not(period, comparison):
    positive = _compare(
        _route_tools_with_cells(
            _cells(period, value=120), _cells(comparison, value=100), period=period, comparison=comparison
        ),
        period=period,
        comparison=comparison,
    )
    assert positive["rows"][0]["comparison"]["available"] is True
    assert positive["rows"][0]["comparison"]["absolute_change"] == 20
    current, prior = _cells(period, value=0), _cells(comparison, value=0)
    known = _compare(
        _route_tools_with_cells(current, prior, period=period, comparison=comparison),
        period=period,
        comparison=comparison,
    )
    assert known["rows"][0]["comparison"]["available"] is True
    assert known["rows"][0]["comparison"]["absolute_change"] == 0
    for missing_current, missing_prior in (([], prior), ([], [])):
        missing = _compare(
            _route_tools_with_cells(missing_current, missing_prior, period=period, comparison=comparison),
            period=period,
            comparison=comparison,
        )
        assert missing["rows"][0]["comparison"]["available"] is False
        assert "faltante" in missing["rows"][0]["comparison"]["reason"]


@pytest.mark.parametrize("metric", ["passengers", "seats"])
def test_flight_component_completeness_cannot_establish_passenger_or_seat_completeness(metric):
    monthly = {
        p: [{**cell, metric: 100} for cell in _cells(p, [0] if p == "2026Q2" else None)]
        for p in ("2026Q2", "2025Q2")
    }
    result = _compare(
        _route_tools_with_cells(_cells("2026Q2"), _cells("2025Q2"), monthly=monthly), metric=metric
    )
    assert result["rows"][0]["comparison"]["available"] is False
    # Conversely, complete passenger/seat detail is independent of flight support.
    full = {p: [{**cell, metric: 100} for cell in _cells(p)] for p in monthly}
    independent = _compare(
        _route_tools_with_cells(_cells("2026Q2", [0]), _cells("2025Q2", [0]), monthly=full), metric=metric
    )
    assert independent["rows"][0]["comparison"]["available"] is True


def test_shared_route_sum_requires_its_own_complete_metric_cells():
    from copy import deepcopy

    tools = _route_tools_with_cells(_cells("2026Q2", [0]), _cells("2025Q2"))
    network = deepcopy(tools.snapshot.payloads["data/v1/flights/international/2026Q2.json"])
    route = network["routes"][0]
    route.update(departures=60, flight_components=_cells("2026Q2", carrier="VIVA_AEROBUS"))
    tools.snapshot.payloads["data/v1/flights/entities/VIVA_AEROBUS/international/2026Q2.json"] = network
    result = tools.invoke(
        "find_shared_routes",
        dict(
            entity_ids=["AEROMEXICO_GROUP", "VIVA_AEROBUS"],
            segment="international",
            period="2026Q2",
            metric="departures",
        ),
    )
    assert result["rows"][0]["comparable"] is False
    assert result["rows"][0]["combined_value"] is None
    assert "route_metric_coverage_incomplete" in result["rows"][0]["comparability_reason"]


def test_unknown_seat_detail_is_not_proved_by_known_passenger_or_flight_cells():
    monthly = {
        p: [
            {**cell, "passengers": 100, "seats": None if p == "2026Q2" and i == 2 else 120}
            for i, cell in enumerate(_cells(p))
        ]
        for p in ("2026Q2", "2025Q2")
    }
    tools = _route_tools_with_cells(_cells("2026Q2"), _cells("2025Q2"), monthly=monthly)
    assert _compare(tools, metric="passengers")["rows"][0]["comparison"]["available"] is True
    assert _compare(tools, metric="seats")["rows"][0]["comparison"]["available"] is False


def test_monthly_detail_cannot_be_duplicated_to_establish_comparability():
    current = _cells("2026Q2")
    tools = _route_tools_with_cells(current + [current[0]], _cells("2025Q2"))
    result = _compare(tools)
    assert result["rows"][0]["comparison"]["available"] is False
    assert "duplica" in result["rows"][0]["comparison"]["reason"]
