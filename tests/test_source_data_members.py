"""Coalesce ready units without requiring a global monthly barrier."""

import json
from types import SimpleNamespace

import pytest

from src.publish import source_data_members as members
from src.publish import source_data_scope as scope


def binding(product):
    return {
        "product": product,
        "period": "2026M09",
        "receipt_id": "a" * 32,
        "candidate_as_of": "2026-10-28T12:00:00Z",
        "output_sha256": {"gold/fact_x": "b" * 64},
    }


def unit(product, value):
    return {
        "product": product,
        "period": "2026M09",
        "source_binding": binding(product),
        "projection": {product: value},
    }


def adapter(product):
    def project(before, projection):
        old = json.loads(before["data/v1/market-demand.json"])
        return {"data/v1/market-demand.json": scope.encoded({**old, **projection})}

    return SimpleNamespace(
        TARGETS=("data/v1/market-demand.json",),
        CONTRACTS=("market_demand.schema.json",),
        public_outputs=project,
    )


def test_each_ready_source_can_project_independently_and_ready_members_compose():
    before = {"data/v1/market-demand.json": scope.encoded({"retained_group": 10})}
    first, second = unit("aicm_traffic", 20), unit("aifa_traffic", 30)
    assert json.loads(members.compose(before, [first], adapter)[next(iter(before))]) == {
        "retained_group": 10,
        "aicm_traffic": 20,
    }
    composed = members.compose(before, [first, second], adapter)
    assert json.loads(composed[next(iter(before))]) == {
        "retained_group": 10,
        "aicm_traffic": 20,
        "aifa_traffic": 30,
    }
    assert members.compose(before, [second, first], adapter) == composed


def test_batch_is_optional_and_duplicate_units_are_rejected():
    request = {
        "product": "aicm_traffic",
        "period": "2026M09",
        "source_profile": {"path": "first", "sha256": "a" * 64},
    }
    assert members.selections(request) == [request]
    with pytest.raises(ValueError, match="twice"):
        members.selections({**request, "additional_sources": [request]})


def test_authority_binds_each_additional_native_source_not_only_aggregate_numbers():
    primary, extra = unit("aicm_traffic", 20), unit("aifa_traffic", 30)
    spec = {
        "product": primary["product"],
        "period_id": primary["period"],
        "source_binding": primary["source_binding"],
        "baseline_commit": "c" * 40,
        "data_files": [],
        "frontend_files": [],
        "producer_code_version": "d" * 64,
        "contract_changes": {},
        "projection": primary["projection"],
        "additional_sources": [extra],
    }
    assert scope.scope(spec)["additional_source_bindings"] == [extra["source_binding"]]
    spec["additional_sources"][0]["source_binding"]["period"] = "2026M08"
    with pytest.raises(ValueError, match="mismatched native period"):
        scope.scope(spec)
