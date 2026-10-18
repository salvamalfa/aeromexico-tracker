import copy

from src.conversational_analytics.tools.routes import RouteTools
from src.conversational_analytics.tools._route_provenance import value_kind
from src.web_export.route_support import metric_support
from src.conversational_analytics.tools._route_rollup import rollup_complete_quarter
from test_chat_route_tools import MemorySnapshot, _paths


def _monthly(month, passengers, *, kind="estimated"):
    detail = [
        dict(
            carrier_key="AEROMEXICO",
            origin_iata=origin,
            destination_iata=destination,
            period_id=month,
            passengers=passengers / 2,
            seats=100,
            departures=5,
        )
        for origin, destination in [("MEX", "CUN"), ("CUN", "MEX")]
    ]
    route = dict(
        market_key="CUN<>MEX",
        origin={"iata": "MEX"},
        destination={"iata": "CUN"},
        passengers=passengers,
        seats=200,
        departures=10,
        load_factor=passengers / 200,
        load_factor_status="estimated",
        passengers_estimated=True,
        capacity_estimated=True,
        operation_status="estimated_from_retained_frequencies",
        source_label="AFAC + AeroDataBox · estimado",
        monthly=detail,
        flight_components=[
            {k: v for k, v in row.items() if k not in {"passengers", "seats"}}
            | {
                "kind": kind,
                "source_label": "retained estimate" if kind == "estimated" else "observed authority",
            }
            for row in detail
        ],
    )
    return dict(
        period_label=month,
        availability="complete",
        expected_months=[month],
        observed_months=[month],
        agent_eligible=False,
        coverage_by_source={"AFAC + AeroDataBox · estimado": [month]},
        source_url="https://www.gob.mx/afac/acciones-y-programas/estadisticas-280404",
        routes=[route],
    )


def _tools(networks, entities=("AEROMEXICO_GROUP",)):
    return RouteTools(
        MemorySnapshot(
            _paths(
                {
                    (entity, "domestic", month): copy.deepcopy(network)
                    for entity in entities
                    for month, network in networks.items()
                }
            )
        )
    )


def test_quarter_preserves_all_monthly_cells_without_aliasing_and_mixed_flight_kinds():
    networks = {
        f"2026M{month:02}": _monthly(f"2026M{month:02}", 100, kind="observed" if month == 4 else "estimated")
        for month in (4, 5, 6)
    }
    original = copy.deepcopy(networks)
    quarter = rollup_complete_quarter("2026Q2", list(networks.values()), value_kind)
    route = quarter["routes"][0]
    assert route["passengers"] == 300 and route["departures"] == 30
    assert len(route["monthly"]) == len(route["flight_components"]) == 6
    assert {row["period_id"] for row in route["monthly"]} == {"2026M04", "2026M05", "2026M06"}
    assert metric_support(quarter, route, "passengers")[2] is None
    assert metric_support(quarter, route, "departures")[2] is None
    assert value_kind(quarter, route, "departures") == "mixed"
    route["monthly"][0]["passengers"] = 999
    route["flight_components"][-1]["departures"] = 999
    assert networks == original


def test_complete_quarters_compare_using_each_months_detail():
    networks = {
        f"2026M{month:02}": _monthly(f"2026M{month:02}", 50 if month <= 3 else 100) for month in range(1, 7)
    }
    result = _tools(networks).invoke(
        "query_routes",
        dict(
            entity_id="AEROMEXICO_GROUP",
            segment="domestic",
            period="2026Q2",
            comparison_period="2026Q1",
            metric="passengers",
            top_n=1,
        ),
    )
    row = result["rows"][0]
    assert row["value"] == 300
    assert row["comparison"]["available"] is True
    assert row["comparison"]["value"] == 150
    assert row["comparison"]["absolute_change"] == 150
    assert row["comparison"]["relative_change_percent"] == 100


def test_shared_quarter_rejects_missing_metric_detail_even_when_headlines_exist():
    networks = {f"2026M{month:02}": _monthly(f"2026M{month:02}", 100) for month in (4, 5, 6)}
    networks["2026M05"]["routes"][0].pop("monthly")
    result = _tools(networks, ("AEROMEXICO_GROUP", "VIVA_AEROBUS")).invoke(
        "find_shared_routes",
        dict(
            entity_ids=["AEROMEXICO_GROUP", "VIVA_AEROBUS"],
            segment="domestic",
            period="2026Q2",
            metric="passengers",
            top_n=1,
        ),
    )
    row = result["rows"][0]
    assert row["comparable"] is False
    assert row["combined_value"] is None
    assert "route_metric_coverage_incomplete" in row["comparability_reason"]


def test_missing_route_month_stays_unknown_and_legacy_detail_is_not_invented():
    networks = {f"2026M{month:02}": _monthly(f"2026M{month:02}", 100) for month in (4, 5, 6)}
    networks["2026M05"]["routes"] = []
    quarter, _ = _tools(networks)._load("AEROMEXICO_GROUP", "domestic", "2026Q2")
    assert quarter["routes"][0]["passengers"] is None
    assert {row["period_id"] for row in quarter["routes"][0]["monthly"]} == {"2026M04", "2026M06"}
    for network in networks.values():
        for route in network["routes"]:
            route.pop("monthly")
            route.pop("flight_components")
    legacy, _ = _tools(networks)._load("AEROMEXICO_GROUP", "domestic", "2026Q2")
    assert "monthly" not in legacy["routes"][0]
    assert "flight_components" not in legacy["routes"][0]
