from __future__ import annotations

from pathlib import Path

import pytest

from src.conversational_analytics.data.snapshot import Snapshot
from src.conversational_analytics.semantic.plan import PlanValidationError
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
    assert result["row_count"] == 1
    assert result["truncated"] is False


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
