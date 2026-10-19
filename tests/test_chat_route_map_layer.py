"""The map programming layer must preserve chat's estimated route series."""

import pytest

from test_chat_route_tools import MemorySnapshot, _network, _paths, _route
from src.conversational_analytics.tools.routes import RouteTools


@pytest.mark.parametrize("complete", [True, False])
def test_official_map_quarter_does_not_replace_chat_monthly_estimates(complete) -> None:
    official = _network("2026Q2", [_route("MEX<>MAD", None)])
    official["mode"] = "scheduled_domestic"
    payloads = {("AEROMEXICO_GROUP", "domestic", "2026Q2"): official}
    for entity in ("AEROMEXICO_GROUP", "VIVA_AEROBUS"):
        for month, value in (("2026M04", 20), ("2026M05", 30), ("2026M06", 40)):
            if complete or month != "2026M06":
                payloads[(entity, "domestic", month)] = _network(month, [_route("MEX<>CUN", value)])
    tools = RouteTools(MemorySnapshot(_paths(payloads)))
    query = {"entity_id": "AEROMEXICO_GROUP", "segment": "domestic",
             "period": "2026Q2", "metric": "passengers"}
    result = tools.invoke("query_routes", query)
    shared = tools.invoke("find_shared_routes", {
        "entity_ids": ["AEROMEXICO_GROUP", "VIVA_AEROBUS"], "segment": "domestic",
        "period": "2026Q2", "metric": "passengers",
    })
    if complete:
        assert result["rows"][0]["market_key"] == "MEX<>CUN"
        assert result["rows"][0]["value"] == 90
        assert result["rows"][0]["value_kind"] == "estimated"
        assert shared["rows"][0]["carriers"]["AEROMEXICO_GROUP"]["value"] == 90
        assert {s["url"].rsplit("/", 1)[-1] for s in result["sources"]
                if "salvamalfa.github.io" in s["url"]} == {
                    "2026M04.json", "2026M05.json", "2026M06.json"}
    else:
        assert result["rows"] == []
        assert shared["rows"] == []
