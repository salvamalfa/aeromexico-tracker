from pathlib import Path

from src.conversational_analytics.data.snapshot import Snapshot
from src.conversational_analytics.tools.routes import RouteTools


def test_route_metric_provenance_uses_evidence_for_each_metric() -> None:
    tools = RouteTools(Snapshot(Path("site")))
    # The published Q2 international payload has an ancillary AICM note on the
    # BTS LAX route and a scheduled departure row whose passengers are AFAC
    # estimates. Interpret each selected metric from its own evidence.
    for market_key, expected in {
        "LAX<>MEX": ("observed", "observed", "observed"),
        "GUA<>MEX": ("estimated", "scheduled", "estimated"),
    }.items():
        kinds = {}
        for metric in ("passengers", "departures", "load_factor"):
            result = tools.invoke(
                "query_routes",
                {
                    "entity_id": "AEROMEXICO_GROUP",
                    "segment": "international",
                    "period": "2026Q2",
                    "metric": metric,
                    "origin_iata": market_key.split("<>")[0],
                    "destination_iata": market_key.split("<>")[1],
                    "top_n": 1,
                },
            )
            row = result["rows"][0]
            kinds[metric] = row["value_kind"]
            assert row["metric_source_label"]
            if metric == "load_factor":
                assert row["value"] <= 100
        assert tuple(kinds[metric] for metric in ("passengers", "departures", "load_factor")) == expected

    gua_passengers = tools.invoke(
        "query_routes",
        {
            "entity_id": "AEROMEXICO_GROUP",
            "segment": "international",
            "period": "2026Q2",
            "metric": "passengers",
            "origin_iata": "GUA",
            "destination_iata": "MEX",
            "top_n": 1,
        },
    )["rows"][0]
    assert gua_passengers["metric_source_label"].startswith("AFAC + AeroDataBox")
