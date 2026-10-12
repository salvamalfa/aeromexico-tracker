from __future__ import annotations

from pathlib import Path

import pytest

from src.conversational_analytics.data.snapshot import Snapshot
from src.conversational_analytics.semantic.plan import PlanValidationError
from src.conversational_analytics.tools._route_contract import source_references
from src.conversational_analytics.tools.routes import RouteTools


class MemorySnapshot:
    version = "route-fixture-v1"
    semantic_version = "semantic-fixture-v1"

    def __init__(self, payloads: dict[str, dict]):
        self.payloads = payloads

    def payload(self, path: str) -> dict:
        if path not in self.payloads:
            raise ValueError("missing public payload")
        return self.payloads[path]


def _network(period: str, routes: list[dict], *, complete: bool = True, eligible: bool = True) -> dict:
    months = [period] if "M" in period else [period]
    return {
        "period_label": period,
        "expected_months": months,
        "observed_months": months if complete else [],
        "availability": "complete" if complete else "partial",
        "agent_eligible": eligible,
        "eligibility_reason": "Published after the historical cutoff" if not eligible else "",
        "coverage_by_source": {"AFAC + AeroDataBox · estimado": months},
        "source_url": "https://www.gob.mx/afac/acciones-y-programas/estadisticas-280404",
        "routes": routes,
    }


def _route(
    market_key: str,
    passengers: float | None,
    *,
    kind: str = "estimated",
    source="AFAC + AeroDataBox · estimado",
) -> dict:
    return {
        "market_key": market_key,
        "origin": {"iata": market_key.split("<>")[0]},
        "destination": {"iata": market_key.split("<>")[1]},
        "passengers": passengers,
        "passengers_estimated": kind == "estimated",
        "capacity_estimated": kind == "estimated",
        "seats": passengers * 1.1 if passengers is not None else None,
        "departures": 4 if passengers is not None else None,
        "load_factor": 0.8 if passengers is not None else None,
        "load_factor_status": "estimated" if kind == "estimated" else None,
        "source_label": source,
        "operation_status": "estimated_from_public_margins" if kind == "estimated" else "operated_observed",
        "coverage_note": "estimated" if kind == "estimated" else "BTS T-100",
        "carrier_breakdown": None,
    }


def _paths(payloads: dict[tuple[str, str, str], dict]) -> dict[str, dict]:
    return {
        (
            f"data/v1/flights/{segment}/{period}.json"
            if entity == "AEROMEXICO_GROUP"
            else f"data/v1/flights/entities/{entity}/{segment}/{period}.json"
        ): payload
        for (entity, segment, period), payload in payloads.items()
    }


def test_published_route_query_ranks_estimates_and_preserves_value_kind() -> None:
    current = _network(
        "2026M07",
        [_route("MEX<>CUN", 100), _route("MEX<>MTY", 200), _route("CUN<>MTY", None)],
        eligible=False,
    )
    tools = RouteTools(MemorySnapshot(_paths({("AEROMEXICO_GROUP", "domestic", "2026M07"): current})))

    result = tools.invoke(
        "query_routes",
        {
            "entity_id": "AEROMEXICO_GROUP",
            "segment": "domestic",
            "period": "2026M07",
            "metric": "passengers",
            "top_n": 1,
        },
    )

    assert result["rows"][0]["market_key"] == "MEX<>MTY"
    assert result["rows"][0]["value"] == 200
    assert result["rows"][0]["value_kind"] == "estimated"
    assert result["coverage"]["2026M07"]["agent_eligible"] is False
    assert result["coverage"]["2026M07"]["eligibility_reason"]
    assert result["coverage"]["2026M07"]["usage_scope"] == "published_dashboard_retrospective"
    assert "no modifica ni implica" in result["coverage"]["2026M07"]["usage_scope_description"]
    assert result["truncated"] is True
    assert result["available_route_count"] == 2
    assert result["missing_route_count"] == 1
    assert all(row["value"] is not None for row in result["rows"])
    assert result["display"]["rows"][0]["value_kind"] == "estimated"
    assert result["sources"][0]["url"].endswith("domestic/2026M07.json")


def test_null_metric_values_do_not_count_as_available_or_truncated_routes() -> None:
    current = _network(
        "2026M07",
        [_route("MEX<>CUN", 100), _route("MEX<>MTY", None)],
    )
    tools = RouteTools(MemorySnapshot(_paths({("AEROMEXICO_GROUP", "domestic", "2026M07"): current})))

    result = tools.invoke(
        "query_routes",
        {
            "entity_id": "AEROMEXICO_GROUP",
            "segment": "domestic",
            "period": "2026M07",
            "metric": "passengers",
            "top_n": 1,
        },
    )

    assert result["rows"][0]["market_key"] == "MEX<>CUN"
    assert result["available_route_count"] == 1
    assert result["missing_route_count"] == 1
    assert result["row_count"] == 1
    assert result["truncated"] is False
    assert "no significa cero" in result["coverage"]["2026M07"]["missing_value_reason"]


def test_growth_comparison_requires_same_route_complete_coverage_and_value_kind() -> None:
    paths = _paths(
        {
            ("AEROMEXICO_GROUP", "domestic", "2025M07"): _network(
                "2025M07",
                [
                    _route("MEX<>CUN", 100),
                    _route("MEX<>MTY", 40),
                    _route("CUN<>MTY", 20),
                ],
            ),
            ("AEROMEXICO_GROUP", "domestic", "2026M07"): _network(
                "2026M07",
                [
                    _route("MEX<>CUN", 125),
                    _route("MEX<>MTY", 80, kind="observed"),
                    # CUN<>MTY is absent. Absence does not become a zero-base growth value.
                ],
            ),
        }
    )
    tools = RouteTools(MemorySnapshot(paths))
    result = tools.invoke(
        "query_routes",
        {
            "entity_id": "AEROMEXICO_GROUP",
            "segment": "domestic",
            "period": "2026M07",
            "comparison_period": "2025M07",
            "metric": "passengers",
            "order_by": "absolute_change",
            "top_n": 5,
        },
    )

    assert [row["market_key"] for row in result["rows"]] == ["MEX<>CUN"]
    assert result["rows"][0]["comparison"]["absolute_change"] == 25
    assert result["rows"][0]["comparison"]["relative_change_percent"] == 25
    assert result["rows"][0]["comparison"]["available"] is True
    assert result["available_route_count"] == 1
    assert result["display"]["rows"][0]["comparison_available"] == "Sí"
    assert result["display"]["rows"][0]["comparison_value_kind"] == "estimated"
    assert result["display"]["rows"][0]["comparison_reason"] is None


def test_partial_coverage_cannot_be_ranked_as_growth_and_missing_period_stays_missing() -> None:
    paths = _paths(
        {
            ("AEROMEXICO_GROUP", "international", "2025Q2"): _network("2025Q2", [_route("MEX<>LAX", 100)]),
            ("AEROMEXICO_GROUP", "international", "2026Q2"): _network(
                "2026Q2", [_route("MEX<>LAX", 120)], complete=False
            ),
        }
    )
    tools = RouteTools(MemorySnapshot(paths))
    result = tools.invoke(
        "query_routes",
        {
            "entity_id": "AEROMEXICO_GROUP",
            "segment": "international",
            "period": "2026Q2",
            "comparison_period": "2025Q2",
            "metric": "passengers",
            "order_by": "value",
        },
    )
    assert result["rows"][0]["value"] == 120
    assert result["rows"][0]["comparison"]["absolute_change"] is None
    assert "cobertura" in result["rows"][0]["comparison"]["reason"]
    display_row = result["display"]["rows"][0]
    assert display_row["comparison_value"] == 100
    assert display_row["comparison_value_kind"] == "estimated"
    assert display_row["comparison_available"] == "No"
    assert "cobertura" in display_row["comparison_reason"]
    ranked = tools.invoke(
        "query_routes",
        {
            "entity_id": "AEROMEXICO_GROUP",
            "segment": "international",
            "period": "2026Q2",
            "comparison_period": "2025Q2",
            "metric": "passengers",
            "order_by": "absolute_change",
        },
    )
    assert ranked["rows"] == []


def test_shared_routes_intersect_only_positive_published_values_and_keep_airline_scope() -> None:
    group_route = _route("MEX<>CUN", 60)
    group_route["carrier_breakdown"] = {"AEROMEXICO": 60, "VIVA_AEROBUS": 60}
    payloads = _paths(
        {
            ("AEROMEXICO_GROUP", "domestic", "2026M07"): _network("2026M07", [group_route]),
            ("VIVA_AEROBUS", "domestic", "2026M07"): _network(
                "2026M07",
                [
                    _route("MEX<>CUN", 60),
                    _route("MEX<>MID", 10),
                ],
            ),
        }
    )
    result = RouteTools(MemorySnapshot(payloads)).invoke(
        "find_shared_routes",
        {
            "entity_ids": ["AEROMEXICO_GROUP", "VIVA_AEROBUS"],
            "segment": "domestic",
            "period": "2026M07",
        },
    )
    assert len(result["rows"]) == 1
    assert result["rows"][0]["market_key"] == "MEX<>CUN"
    assert result["rows"][0]["carriers"]["AEROMEXICO_GROUP"]["value"] == 60
    assert "Aerovías" in result["aeromexico_scope"] and "Connect" in result["aeromexico_scope"]
    assert result["display"]["kind"] == "table"


def test_validation_rejects_open_periods_and_bad_limits() -> None:
    tools = RouteTools(MemorySnapshot({}))
    with pytest.raises(PlanValidationError):
        tools.invoke(
            "query_routes",
            {
                "entity_id": "AEROMEXICO_GROUP",
                "segment": "domestic",
                "period": "2026M00",
                "metric": "passengers",
            },
        )
    with pytest.raises(PlanValidationError):
        tools.invoke(
            "query_routes",
            {
                "entity_id": "AEROMEXICO_GROUP",
                "segment": "domestic",
                "period": "2026M07",
                "metric": "passengers",
                "top_n": True,
            },
        )
    with pytest.raises(PlanValidationError):
        tools.invoke(
            "find_shared_routes",
            {
                "entity_ids": ["VOLARIS", "VOLARIS"],
                "segment": "domestic",
                "period": "2026M07",
            },
        )


def test_queries_the_signed_public_snapshot_without_private_inputs() -> None:
    tools = RouteTools(Snapshot(Path("site")))
    result = tools.invoke(
        "query_routes",
        {
            "entity_id": "AEROMEXICO_GROUP",
            "segment": "domestic",
            "period": "2026M07",
            "metric": "passengers",
            "top_n": 3,
        },
    )
    assert result["rows"]
    assert result["rows"][0]["value_kind"] == "estimated"
    assert result["data_version"] == tools.snapshot.version
    assert result["sources"][0]["url"].endswith("domestic/2026M07.json")

    international = tools.invoke(
        "query_routes",
        {
            "entity_id": "AEROMEXICO_GROUP",
            "segment": "international",
            "period": "2026Q2",
            "metric": "passengers",
            "top_n": 3,
        },
    )
    assert international["rows"]
    assert international["coverage"]["2026Q2"]["complete"] is False
    assert {row["value_kind"] for row in international["rows"]} <= {"observed", "estimated", "scheduled"}
    assert all(row["source_label"] and row["operation_status"] for row in international["rows"])

    shared = tools.invoke(
        "find_shared_routes",
        {
            "entity_ids": ["AEROMEXICO_GROUP", "VIVA_AEROBUS"],
            "segment": "domestic",
            "period": "2026M07",
            "top_n": 3,
        },
    )
    assert shared["rows"]
    assert all(row["carriers"]["AEROMEXICO_GROUP"]["value"] > 0 for row in shared["rows"])
    assert all(row["carriers"]["VIVA_AEROBUS"]["value"] > 0 for row in shared["rows"])

    international_shared = tools.invoke(
        "find_shared_routes",
        {
            "entity_ids": ["AEROMEXICO_GROUP", "VOLARIS", "VIVA_AEROBUS"],
            "segment": "international",
            "period": "2026Q2",
            "top_n": 20,
        },
    )
    assert international_shared["rows"]
    assert all(not coverage["complete"] for coverage in international_shared["coverage"].values())
    assert all(not row["comparable"] for row in international_shared["rows"])
    assert all("coverage_incomplete" in row["comparability_reason"] for row in international_shared["rows"])


def test_domestic_quarter_rollup_uses_only_three_complete_published_months() -> None:
    snapshot = Snapshot(Path("site"))
    tools = RouteTools(snapshot)
    months = ["2026M04", "2026M05", "2026M06"]
    networks = [snapshot.payload(f"data/v1/flights/domestic/{period}.json") for period in months]
    monthly_maps = [{route["market_key"]: route for route in network["routes"]} for network in networks]
    passenger_keys = set.intersection(
        *(
            {
                market
                for market, route in routes.items()
                if isinstance(route.get("passengers"), (int, float))
            }
            for routes in monthly_maps
        )
    )
    complete_keys = set.intersection(
        *(
            set(
                market
                for market, route in routes.items()
                if isinstance(route.get("passengers"), (int, float))
                and isinstance(route.get("load_factor"), (int, float))
                and route.get("load_factor_status") != "inconsistent_inputs"
            )
            for routes in monthly_maps
        )
    )
    market_key = sorted(complete_keys)[0]
    origin, destination = market_key.split("<>")
    result = tools.invoke(
        "query_routes",
        {
            "entity_id": "AEROMEXICO_GROUP",
            "segment": "domestic",
            "period": "2026Q2",
            "metric": "passengers",
            "origin_iata": origin,
            "destination_iata": destination,
            "top_n": 1,
        },
    )

    assert result["rows"][0]["market_key"] == market_key
    assert result["rows"][0]["value"] == sum(routes[market_key]["passengers"] for routes in monthly_maps)
    assert result["rows"][0]["value_kind"] == "estimated"
    assert result["coverage"]["2026Q2"]["expected_months"] == months
    assert result["coverage"]["2026Q2"]["observed_months"] == months
    assert result["coverage"]["2026Q2"]["agent_eligible"] is False
    assert result["coverage"]["2026Q2"]["usage_scope"] == "published_dashboard_retrospective"
    dashboard_sources = [
        source["url"] for source in result["sources"] if "salvamalfa.github.io" in source["url"]
    ]
    assert {url.rsplit("/", 1)[-1] for url in dashboard_sources} == {f"{month}.json" for month in months}
    assert not any(url.endswith("domestic/2026Q2.json") for url in dashboard_sources)

    load_factor = tools.invoke(
        "query_routes",
        {
            "entity_id": "AEROMEXICO_GROUP",
            "segment": "domestic",
            "period": "2026Q2",
            "metric": "load_factor",
            "origin_iata": origin,
            "destination_iata": destination,
            "top_n": 1,
        },
    )
    passengers = sum(routes[market_key]["passengers"] for routes in monthly_maps)
    seats = sum(routes[market_key]["seats"] for routes in monthly_maps)
    assert load_factor["rows"][0]["value"] == pytest.approx(passengers / seats * 100)

    published_rollup, _ = tools._load("AEROMEXICO_GROUP", "domestic", "2026Q2")
    mex_vsa = next(row for row in published_rollup["routes"] if row["market_key"] == "MEX<>VSA")
    assert mex_vsa["load_factor"] is None
    assert mex_vsa["load_factor_status"] == "inconsistent_inputs"
    assert mex_vsa["metric_value_kinds"]["load_factor"] == "missing"

    partial_keys = set.union(*(set(routes) for routes in monthly_maps)) - passenger_keys
    assert partial_keys
    partial_key = sorted(partial_keys)[0]
    origin, destination = partial_key.split("<>")
    missing = tools.invoke(
        "query_routes",
        {
            "entity_id": "AEROMEXICO_GROUP",
            "segment": "domestic",
            "period": "2026Q2",
            "metric": "passengers",
            "origin_iata": origin,
            "destination_iata": destination,
            "top_n": 1,
        },
    )
    assert missing["rows"] == []
    assert missing["missing_route_count"] == 1
    assert "no significa cero" in missing["coverage"]["2026Q2"]["missing_value_reason"]


def test_domestic_quarter_requires_all_months_and_prefers_native_quarter_payload() -> None:
    month4 = _network("2026M04", [_route("MEX<>CUN", 20)])
    month5 = _network("2026M05", [_route("MEX<>CUN", 30)])
    incomplete = RouteTools(
        MemorySnapshot(
            _paths(
                {
                    ("AEROMEXICO_GROUP", "domestic", "2026M04"): month4,
                    ("AEROMEXICO_GROUP", "domestic", "2026M05"): month5,
                }
            )
        )
    ).invoke(
        "query_routes",
        {"entity_id": "AEROMEXICO_GROUP", "segment": "domestic", "period": "2026Q2", "metric": "passengers"},
    )
    assert incomplete["rows"] == []
    assert incomplete["coverage"]["2026Q2"]["availability"] == "missing"

    native = _network("2026Q2", [_route("MEX<>CUN", 777)])
    paths = _paths(
        {
            ("AEROMEXICO_GROUP", "domestic", "2026Q2"): native,
            ("AEROMEXICO_GROUP", "domestic", "2026M04"): month4,
            ("AEROMEXICO_GROUP", "domestic", "2026M05"): month5,
            ("AEROMEXICO_GROUP", "domestic", "2026M06"): _network("2026M06", [_route("MEX<>CUN", 40)]),
        }
    )
    preferred = RouteTools(MemorySnapshot(paths)).invoke(
        "query_routes",
        {"entity_id": "AEROMEXICO_GROUP", "segment": "domestic", "period": "2026Q2", "metric": "passengers"},
    )
    assert preferred["rows"][0]["value"] == 777


def test_route_display_ids_change_with_filters_and_metric() -> None:
    domestic = _network(
        "2026M07",
        [_route("MEX<>CUN", 100), _route("MEX<>MTY", 200)],
    )
    international = _network("2026M07", [_route("MEX<>CUN", 300)])
    previous = _network("2025M07", [_route("MEX<>CUN", 90)])
    paths = _paths(
        {
            ("AEROMEXICO_GROUP", "domestic", "2026M07"): domestic,
            ("AEROMEXICO_GROUP", "domestic", "2025M07"): previous,
            ("AEROMEXICO_GROUP", "international", "2026M07"): international,
        }
    )
    tools = RouteTools(MemorySnapshot(paths))
    common = {"entity_id": "AEROMEXICO_GROUP", "period": "2026M07", "top_n": 5}
    queries = [
        {**common, "segment": "domestic", "metric": "passengers"},
        {**common, "segment": "domestic", "metric": "seats"},
        {**common, "segment": "domestic", "metric": "passengers", "origin_iata": "CUN"},
        {
            **common,
            "segment": "domestic",
            "metric": "passengers",
            "comparison_period": "2025M07",
        },
        {**common, "segment": "international", "metric": "passengers"},
    ]
    display_ids = [tools.invoke("query_routes", query)["display"]["display_id"] for query in queries]
    assert len(set(display_ids)) == len(queries)


def test_shared_route_display_ids_include_entities_metric_and_top_n() -> None:
    routes = [_route("MEX<>CUN", 100)]
    payloads = _paths(
        {
            (entity, "domestic", "2026M07"): _network("2026M07", routes)
            for entity in ("AEROMEXICO_GROUP", "VIVA_AEROBUS", "VOLARIS")
        }
    )
    tools = RouteTools(MemorySnapshot(payloads))
    base = {"segment": "domestic", "period": "2026M07"}
    first = tools.invoke(
        "find_shared_routes",
        {**base, "entity_ids": ["AEROMEXICO_GROUP", "VIVA_AEROBUS"], "metric": "passengers", "top_n": 3},
    )
    second = tools.invoke(
        "find_shared_routes",
        {**base, "entity_ids": ["AEROMEXICO_GROUP", "VOLARIS"], "metric": "seats", "top_n": 3},
    )
    third = tools.invoke(
        "find_shared_routes",
        {**base, "entity_ids": ["AEROMEXICO_GROUP", "VIVA_AEROBUS"], "metric": "passengers", "top_n": 1},
    )
    assert (
        len({first["display"]["display_id"], second["display"]["display_id"], third["display"]["display_id"]})
        == 3
    )


def test_shared_route_display_preserves_incomparability_and_each_carriers_metadata() -> None:
    route_aero = _route("MEX<>CUN", 100, kind="estimated")
    route_viva = _route("MEX<>CUN", 80, kind="observed", source="BTS T-100")
    paths = _paths(
        {
            ("AEROMEXICO_GROUP", "domestic", "2026M07"): _network("2026M07", [route_aero]),
            ("VIVA_AEROBUS", "domestic", "2026M07"): _network(
                "2026M07", [route_viva], complete=False
            ),
        }
    )
    result = RouteTools(MemorySnapshot(paths)).invoke(
        "find_shared_routes",
        {
            "entity_ids": ["AEROMEXICO_GROUP", "VIVA_AEROBUS"],
            "segment": "domestic",
            "period": "2026M07",
            "metric": "passengers",
        },
    )

    row = result["rows"][0]
    display = result["display"]
    shown = display["rows"][0]
    assert row["comparable"] is False
    assert {"coverage_incomplete", "value_kind_differs", "source_family_differs"} <= set(
        row["comparability_reason"]
    )
    assert shown["comparable"] is False
    assert "coverage_incomplete" in shown["comparability_reason"]
    assert shown["AEROMEXICO_GROUP_value_kind"] == "estimated"
    assert shown["VIVA_AEROBUS_value_kind"] == "observed"
    assert shown["carrier_coverage"] == row["coverage"]
    assert {"AEROMEXICO_GROUP_value", "VIVA_AEROBUS_value"} <= {
        column["key"] for column in display["columns"]
    }


def test_source_references_deduplicate_by_url_and_merge_distinct_labels() -> None:
    path = "data/v1/flights/domestic/2026Q2.json"
    refs = source_references(
        [
            ({"period_label": "2T26, Grupo Aeroméxico"}, path),
            ({"period_label": "2T26, Industria"}, path),
        ]
    )
    assert refs == [
        {
            "label": "Dashboard público · 2T26, Grupo Aeroméxico / 2T26, Industria",
            "url": "https://salvamalfa.github.io/aeromexico-tracker/data/v1/flights/domestic/2026Q2.json",
        }
    ]
