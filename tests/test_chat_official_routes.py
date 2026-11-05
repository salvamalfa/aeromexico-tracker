"""Official map/chat parity, hostile inputs and legacy isolation without network calls."""

from __future__ import annotations

import copy
import itertools
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.conversational_analytics.config import ChatConfig
from src.conversational_analytics.data.snapshot import Snapshot
from src.conversational_analytics.semantic.context import OFFICIAL_CARRIERS, validate_context
from src.conversational_analytics.semantic.plan import PlanValidationError
from src.conversational_analytics.tools.official_routes import official_route_tool_spec
from src.conversational_analytics.tools.registry import ToolRegistry
from src.dashboard.official_routes_contract import PUBLIC_PATH, dataset_version

ROOT = Path(__file__).resolve().parents[1]


def document():
    doc = json.loads((ROOT / "tests/fixtures/official-routes.example.json").read_bytes())
    national = doc["networks"][0]
    international = copy.deepcopy(national)
    international["scope"] = "international"
    international["routes"] = []
    for index, (country, region) in enumerate(
        [
            ("CA", "canada"),
            ("PR", "central_america_caribbean"),
            ("BR", "south_america"),
            ("FR", "europe"),
            ("JP", "asia"),
        ]
    ):
        route = copy.deepcopy(national["routes"][0])
        route["route_key"] = f"CITY_MX_MEXICO--CITY_{country}_FOREIGN"
        route["destination"].update(id=f"CITY_{country}_FOREIGN", label=country, country_iso2=country)
        route["region"] = region
        route["departures"] = 6 + index * 3
        for month in route["monthly"]:
            month["departures"] = 2 + index
        route["directions"] = [
            {
                "origin_id": route["origin"]["id"],
                "destination_id": route["destination"]["id"],
                "departures": route["departures"],
            }
        ]
        international["routes"].append(route)
    doc["networks"].append(international)
    doc["sources"].append(
        {
            **doc["sources"][0],
            "id": "bts-2026",
            "label": "BTS T-100 F+G",
            "url": "https://www.transtats.bts.gov/DL_SelectFields.aspx?gnoyr_VQ=FJE"
            "&QO_fu146_anzr=Nv4%20Pn44vr45&requested_geography=Mexico&requested_year=2026",
            "source_period": "2026M07",
        }
    )
    for count in range(1, 4):
        for selected in itertools.combinations(OFFICIAL_CARRIERS, count):
            network = copy.deepcopy(national)
            network.update(
                scope="us",
                grain="airport_pair",
                carrier_keys=list(selected),
                entity="THREE" if count == 3 else "+".join(selected),
                observed_months=["2026M07"],
                availability="partial",
                source_ids=["bts-2026"],
            )
            route = network["routes"][0]
            route.update(
                route_key="MEX--JFK",
                departures=3 * count,
                monthly=[{"period_id": "2026M07", "departures": 3 * count}],
            )
            route["origin"].update(id="MEX", label="Ciudad de México", point_kind="airport", iata="MEX")
            route["destination"].update(
                id="JFK", label="Nueva York", point_kind="airport", iata="JFK", country_iso2="US"
            )
            route["directions"] = [{"origin_id": "MEX", "destination_id": "JFK", "departures": 3 * count}]
            route["operators"] = []
            for carrier in selected:
                ops = (
                    [("19534", 2), ("20250", 1)]
                    if carrier == "AEROMEXICO"
                    else [("21351" if carrier == "VOLARIS" else "21342", 3)]
                )
                for operator, departures in ops:
                    operator_key = "AEROMEXICO_CONNECT" if operator == "20250" else carrier
                    route["operators"].append(
                        {
                            "carrier_key": operator_key,
                            "carrier_group": carrier,
                            "airline_id": operator,
                            "label": operator,
                            "departures": departures,
                        }
                    )
            doc["networks"].append(network)
    for network in doc["networks"]:
        for route in network["routes"]:
            if route["origin"]["id"] > route["destination"]["id"]:
                route["origin"], route["destination"] = route["destination"], route["origin"]
            route["route_key"] = route["origin"]["id"] + "--" + route["destination"]["id"]
    doc["dataset_version"] = dataset_version(doc)
    return doc


class PublicSnapshot:
    def __init__(self, doc=None):
        self.base = Snapshot(ROOT / "tests/fixtures/chat/site")
        self.document = doc or document()
        self.version = self.document["dataset_version"]
        self.semantic_version = "official-semantic-test"
        self.project_root = ROOT

    def payload(self, path):
        return copy.deepcopy(self.document) if path == PUBLIC_PATH else self.base.payload(path)

    def catalog(self):
        return self.base.catalog()


def map_context(doc, scope="national", **overrides):
    filters = {
        "map_schema_version": "official_route_network_v1",
        "map_dataset_version": doc["dataset_version"],
        "map_scope": scope,
        "map_grain": "airport_pair" if scope == "us" else "city_pair",
        "map_months": ["2026M07"] if scope == "us" else ["2026M07", "2026M08", "2026M09"],
        "map_carriers": list(OFFICIAL_CARRIERS) if scope == "us" else [],
    }
    filters.update(overrides)
    return {"tab": "market", "card_id": "route-flow-map", "period": "2026Q3", "filters": filters}


def registry(snapshot, **overrides):
    settings = dict(enable_official_route_tools=True, official_route_dataset_sha256=snapshot.version)
    settings.update(overrides)
    return ToolRegistry(snapshot, SimpleNamespace(**settings))


def test_official_chip_and_direct_tool_equal_published_values_and_keep_all_afac():
    snapshot = PublicSnapshot()
    tools = registry(snapshot)
    context = map_context(snapshot.document)
    result = tools.invoke("query_official_routes", {}, context)
    assert result["rows"] == snapshot.document["networks"][0]["routes"]
    assert result["entity"] == "ALL" and result["grain"] == "city_pair"
    assert result["total_departures"] == 6 and result["total_routes"] == 1
    assert result["observed_months"] == context["filters"]["map_months"]
    assert result["dataset_version"] == context["filters"]["map_dataset_version"]
    assert result["rows"][0]["comparison"]["previous_departures"] is None
    assert result["references"][1]["url"] == snapshot.document["sources"][0]["url"]
    assert tools.invoke("get_dashboard_context", {}, context)["context"] == context
    assert tools.catalog()["official_routes"]["dataset_version"] == snapshot.version


@pytest.mark.parametrize(
    "carriers",
    [list(value) for count in range(1, 4) for value in itertools.combinations(OFFICIAL_CARRIERS, count)],
)
def test_us_multiselect_is_exact_published_network_and_retains_raw_operators(carriers):
    snapshot = PublicSnapshot()
    tools = registry(snapshot)
    result = tools.invoke(
        "query_official_routes",
        {"carrier_keys": list(reversed(carriers))},
        map_context(snapshot.document, "us"),
    )
    assert result["grain"] == "airport_pair"
    assert result["availability"] == "partial"
    assert result["observed_months"] == ["2026M07"]
    assert result["expected_months"] == ["2026M07", "2026M08", "2026M09"]
    assert result["total_departures"] == 3 * len(carriers)
    assert {row["carrier_group"] for row in result["rows"][0]["operators"]} == set(carriers)
    if "AEROMEXICO" in carriers:
        assert {"19534", "20250"} <= {row["airline_id"] for row in result["rows"][0]["operators"]}


def test_us_defaults_three_and_explicit_scope_does_not_inherit_afac_region_or_carriers():
    snapshot = PublicSnapshot()
    result = registry(snapshot).invoke(
        "query_official_routes",
        {"scope": "us"},
        map_context(snapshot.document, "international", map_region="asia"),
    )
    assert result["query"]["carrier_keys"] == list(OFFICIAL_CARRIERS)
    assert result["query"]["region"] is None and result["total_departures"] == 9


@pytest.mark.parametrize("region", ["canada", "central_america_caribbean", "south_america", "europe", "asia"])
def test_international_geographic_regions_are_exact_and_include_puerto_rico(region):
    snapshot = PublicSnapshot()
    result = registry(snapshot).invoke(
        "query_official_routes", {}, map_context(snapshot.document, "international", map_region=region)
    )
    assert len(result["rows"]) == 1 and result["rows"][0]["region"] == region
    assert result["entity"] == "ALL"
    assert result["rows"][0]["destination"]["country_iso2"] != "US"
    if region == "central_america_caribbean":
        assert result["rows"][0]["destination"]["country_iso2"] == "PR"


@pytest.mark.parametrize("arguments", [{"period": "2026Q4"}, {"route_key": "ABSENT"}])
def test_unpublished_period_or_absent_route_stays_missing_without_nearest_or_zero(arguments):
    snapshot = PublicSnapshot()
    result = registry(snapshot).invoke("query_official_routes", arguments, map_context(snapshot.document))
    assert result["availability"] == "missing"
    assert result["total_departures"] is None and result["total_routes"] is None and result["rows"] == []
    if "period" in arguments:
        assert result["query"]["period"] == "2026Q4" and result["observed_months"] == []


@pytest.mark.parametrize(
    "arguments",
    [
        {"carrier_keys": ["AEROMEXICO"]},
        {"entity_id": "AEROMEXICO"},
        {"metric": "passengers"},
        {"scope": "us", "carrier_keys": []},
        {"scope": "us", "carrier_keys": ["INDUSTRY"]},
        {"scope": "us", "carrier_keys": ["VOLARIS", "VOLARIS"]},
        {"region": "asia"},
        {"top_n": True},
        {"top_n": 21},
        {"dataset_version": "0" * 64},
        {"scope": ["us"]},
        {"scope": "us", "carrier_keys": [{}]},
        {"period": "2026M07"},
        {"route_key": {}},
    ],
)
def test_hostile_or_semantically_unsupported_tool_arguments_rejected(arguments):
    snapshot = PublicSnapshot()
    with pytest.raises(PlanValidationError):
        registry(snapshot).invoke("query_official_routes", arguments, map_context(snapshot.document))


@pytest.mark.parametrize(
    "override",
    [
        {"map_grain": "airport_pair"},
        {"map_scope": "other"},
        {"map_dataset_version": "not-a-pin"},
        {"map_carriers": ["AEROMEXICO"]},
        {"map_months": ["2026M07", "2026M07"]},
        {"map_region": "canada"},
        {"flight_evidence": "north_america_observed"},
        {"map_carriers": [{}]},
        {"map_months": [{}]},
        {"map_schema_version": "flight_evidence_v1"},
    ],
)
def test_untrusted_context_filters_rejected(override):
    with pytest.raises(PlanValidationError):
        validate_context(map_context(document(), **override))


def test_stale_chip_version_months_entity_and_wrong_card_rejected():
    snapshot = PublicSnapshot()
    tools = registry(snapshot)
    for changes in ({"map_dataset_version": "0" * 64}, {"map_months": ["2026M07"]}):
        with pytest.raises(PlanValidationError):
            tools.invoke("query_official_routes", {}, map_context(snapshot.document, **changes))
    for field, value in (("tab", "reading"), ("card_id", "market-chart"), ("entity", "AEROMEXICO")):
        context = map_context(snapshot.document)
        context[field] = value
        with pytest.raises(PlanValidationError):
            validate_context(context)


def test_tampered_payload_or_pin_rejected_and_registry_is_default_off():
    snapshot = PublicSnapshot()
    disabled = ToolRegistry(snapshot)
    assert "query_official_routes" not in {spec["name"] for spec in disabled.tool_specs()}
    with pytest.raises(PlanValidationError, match="desconocida"):
        disabled.invoke("query_official_routes", {})
    with pytest.raises(PlanValidationError, match="pin"):
        registry(snapshot, official_route_dataset_sha256="0" * 64)
    snapshot.document["networks"][0]["routes"][0]["departures"] += 1
    with pytest.raises(PlanValidationError, match="identidad"):
        registry(snapshot)


def test_r1_cannot_enable_official_tools_and_pin_is_mandatory():
    assert ChatConfig().enable_official_route_tools is False
    with pytest.raises(ValueError, match="SHA256"):
        ChatConfig(enable_official_route_tools=True)
    with pytest.raises(ValueError, match="exact approved prompt"):
        ChatConfig(enable_official_route_tools=True, official_route_dataset_sha256="a" * 64)


@pytest.mark.parametrize("tool", ["query_routes", "find_shared_routes"])
def test_official_chip_cannot_silently_query_legacy_estimated_routes(tool):
    snapshot = PublicSnapshot()
    tools = registry(snapshot, enable_route_tools=True)
    with pytest.raises(PlanValidationError, match="requiere query_official_routes"):
        tools.invoke(tool, {}, map_context(snapshot.document))


def test_legacy_schemas_catalog_and_financial_results_stay_identical_when_official_enabled():
    snapshot = PublicSnapshot()
    legacy = ToolRegistry(snapshot, SimpleNamespace(enable_route_tools=True))
    combined = registry(snapshot, enable_route_tools=True)
    assert [
        spec for spec in combined.tool_specs() if spec["name"] != "query_official_routes"
    ] == legacy.tool_specs()
    catalog = combined.catalog()
    del catalog["official_routes"]
    assert catalog == legacy.catalog()
    arguments = {"metric_ids": ["load_factor"], "entity_ids": ["AEROMEXICO"], "periods": ["2026Q2"]}
    assert combined.invoke("query_metrics", arguments) == legacy.invoke("query_metrics", arguments)
    assert combined.invoke("get_metric_definition", {"metric_id": "afac_passengers"}) == legacy.invoke(
        "get_metric_definition", {"metric_id": "afac_passengers"}
    )


def test_result_and_catalog_lists_are_detached_from_the_pinned_reader():
    snapshot = PublicSnapshot()
    tools = registry(snapshot)
    arguments = {"period": "2026Q3", "scope": "national"}
    result = tools.invoke("query_official_routes", arguments)
    before = copy.deepcopy(result)
    result["expected_months"].clear()
    result["observed_months"].clear()
    result["rows"][0]["monthly"].clear()
    tools.catalog()["official_routes"]["periods"].clear()
    assert tools.invoke("query_official_routes", arguments) == before


def test_tool_bounds_transport_without_mutation_and_keeps_totals():
    doc = document()
    route = doc["networks"][0]["routes"][0]
    doc["networks"][0]["routes"] = []
    for index in range(40):
        row = copy.deepcopy(route)
        old_id = row["destination"]["id"]
        new_id = old_id + f"_{index:02}"
        row["destination"]["id"] = new_id
        row["route_key"] = row["origin"]["id"] + "--" + new_id
        for direction in row["directions"]:
            for field in ("origin_id", "destination_id"):
                if direction[field] == old_id:
                    direction[field] = new_id
        doc["networks"][0]["routes"].append(row)
    doc["dataset_version"] = dataset_version(doc)
    snapshot = PublicSnapshot(doc)
    before = copy.deepcopy(snapshot.document)
    result = registry(snapshot).invoke(
        "query_official_routes", {"period": "2026Q3", "scope": "national", "top_n": 20}
    )
    assert result["truncated"] and result["total_routes"] == 40 and result["total_departures"] == 240
    assert 0 < result["returned_routes"] <= 20
    assert len(json.dumps(result, ensure_ascii=False).encode()) < 16_000
    assert snapshot.document == before


def test_official_tool_schema_keeps_full_description_pin_and_closed_wire():
    from src.conversational_analytics.providers._openai_runtime_helpers import validate_tool_specs

    spec = official_route_tool_spec("f" * 64)
    assert len(spec["description"]) <= 1000
    tools = validate_tool_specs(ToolRegistry._make_specs() + [spec])
    official = tools[-1]
    assert official["parameters"]["additionalProperties"] is False
    assert set(official["parameters"]["required"]) == set(official["parameters"]["properties"])
    assert "f" * 64 in official["description"]


@pytest.mark.parametrize(
    "source",
    [
        "https://example.org/source",
        "file:///private/data.xlsx",
        "http://www.gob.mx/afac",
        "https://www.gob.mx.evil.test/afac",
        "https://user@www.gob.mx/afac",
        "https://www.gob.mx:8443/afac",
    ],
)
def test_sources_outside_exact_public_allowlist_rejected(source):
    doc = document()
    doc["sources"][0]["url"] = source
    doc["dataset_version"] = dataset_version(doc)
    snapshot = PublicSnapshot(doc)
    with pytest.raises(PlanValidationError, match="Fuente oficial"):
        registry(snapshot).invoke("query_official_routes", {}, map_context(doc))
