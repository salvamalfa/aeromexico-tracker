"""Independent mixed-family contracts for the unpublished PR152 compatibility proposal."""

from __future__ import annotations

import json
import shutil
from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest

from src.common.storage import save_bronze
from src.source_updates import (
    government_candidate,
    government_traffic,
    readiness,
    retained,
    retained_round,
    series_candidate,
)
from src.source_updates.catalog import ROOT
from tests.test_government_traffic_independent import aicm_document
from tests.test_source_update_afac_airports import workbook
from tests.test_source_update_series_independent import macro_inputs

CUTOFF = "2026-10-23T12:00:00-06:00"
PAIRS = [
    ("fuel", "series"),
    ("banxico", "series"),
    ("equities", "series"),
    ("aicm_traffic", "government"),
    ("aifa_traffic", "government"),
    ("afac_airports", "retained"),
    ("oma_traffic", "retained"),
]


@pytest.fixture
def workspace():
    root = ROOT / "tmp/source-updates" / ("independent-adapter-compatibility-" + uuid4().hex)
    try:
        yield root
    finally:
        shutil.rmtree(root, ignore_errors=True)


def task(root, product, adapter, period="2026M07", receipt="a" * 32):
    return dict(
        id=product,
        product=product,
        adapter=adapter,
        period=period,
        workspace=str(root / "candidates" / product),
        receipt_id=receipt,
        required=True,
        candidate_as_of=CUTOFF,
    )


def recipe(items):
    return dict(version=1, as_of=CUTOFF, required_items=[item["id"] for item in items], items=items)


@pytest.mark.parametrize("product,expected", PAIRS)
@pytest.mark.parametrize("adapter", ["series", "government", "retained"])
def test_preflight_requires_the_exact_registered_certifier(workspace, product, expected, adapter):
    proposal = recipe([task(workspace, product, adapter)])
    if adapter == expected:
        plan = readiness.preflight(proposal, workspace / "round")
        assert plan[0]["adapter"] == expected
    else:
        with pytest.raises(ValueError, match="adapter"):
            readiness.preflight(proposal, workspace / "round")
    assert not workspace.exists()


@pytest.mark.parametrize(
    "product,adapter,period,allowed",
    [
        ("fuel", "series", "2026Q3", True),
        ("banxico", "series", "2026Q3", True),
        ("equities", "series", "2026Q3", True),
        ("aicm_traffic", "government", "2026Q3", False),
        ("aifa_traffic", "government", "2026Q3", False),
        ("iasa", "retained", "2026Q3", True),
    ],
)
def test_quarterly_support_survives_merge_without_allowing_monthly_government(
    workspace, product, adapter, period, allowed
):
    proposal = recipe([task(workspace, product, adapter, period)])
    if allowed:
        assert readiness.preflight(proposal, workspace / "round")[0]["period"] == period
    else:
        with pytest.raises(ValueError, match="monthly"):
            readiness.preflight(proposal, workspace / "round")
    assert not workspace.exists()


@pytest.mark.parametrize("product", ["fuel", "banxico", "equities", "aicm_traffic", "aifa_traffic"])
@pytest.mark.parametrize("method", ["run", "frames"])
def test_native_only_entrypoints_reject_both_integral_families_before_reading_originals(
    workspace, monkeypatch, product, method
):
    def forbidden(*args, **kwargs):
        pytest.fail("An integral product reached the legacy native-only reader")

    monkeypatch.setattr(retained, "originals", forbidden)
    with pytest.raises(ValueError, match="candidate"):
        getattr(retained, method)(workspace / "candidate", product, "2026M07", CUTOFF, "a" * 32)
    assert not workspace.exists()


@pytest.fixture
def mixed_sources(tmp_path, monkeypatch):
    root = tmp_path / "bronze"
    selections = {}
    for product, inputs in {
        "fuel": macro_inputs("fuel"),
        "aicm_traffic": {
            "pdf": (
                b"%PDF-1.7\n" + json.dumps(aicm_document()).encode(),
                dict(
                    source_system="aicm",
                    logical_key="aicm|airport|2026M07|pdf",
                    source_url="https://www.aicm.com.mx/compatibility-fixture.pdf",
                ),
            )
        },
        "afac_airports": {
            "workbook": (
                workbook(),
                dict(
                    source_system="afac",
                    logical_key="afac|airport|2026M07|xlsx",
                    source_url="https://www.gob.mx/compatibility-fixture.xlsx",
                ),
            )
        },
    }.items():
        selections[product] = {}
        for role, (body, row) in inputs.items():
            _, entity, period, extension = row["logical_key"].split("|")
            path = save_bronze(
                body,
                row["source_system"],
                entity,
                period,
                extension,
                row["source_url"],
                "manual",
                bronze_root=root,
                downloaded_at=datetime(2026, 10, 19, tzinfo=UTC),
            )
            selections[product][role] = path.relative_to(root).as_posix()

    def reader(stream):
        pages = json.loads(stream.read().split(b"\n", 1)[1])
        return SimpleNamespace(pages=[SimpleNamespace(extract_text=lambda text=t: text) for t in pages])

    def no_http(*args, **kwargs):
        pytest.fail("Mixed compatibility tests must never issue source HTTP requests")

    monkeypatch.setattr(government_traffic, "PdfReader", reader)
    monkeypatch.setattr(httpx.Client, "send", no_http)
    return root, selections


def mixed_recipe(mixed_sources, order):
    root, selections = mixed_sources
    return dict(
        version=1,
        as_of=CUTOFF,
        source_root=str(root),
        items=[
            dict(product=p, period="2026Q3" if p == "fuel" else "2026M07", originals=selections[p])
            for p in order
        ],
    )


@pytest.mark.parametrize(
    "order",
    [
        ["fuel", "aicm_traffic", "afac_airports"],
        ["aicm_traffic", "afac_airports", "fuel"],
    ],
)
def test_mixed_batch_certifies_each_family_and_actual_readiness_replays_exactly(
    workspace, mixed_sources, order
):
    proposal = mixed_recipe(mixed_sources, order)
    batch = workspace / "batch"
    dry = retained_round.execute(proposal, batch)
    assert [row["adapter"] for row in dry["plan"]] == [
        {"fuel": "series", "aicm_traffic": "government", "afac_airports": "retained"}[p] for p in order
    ]
    assert not workspace.exists() and dry["network_requests"] == 0
    result = retained_round.execute(proposal, batch, write=True)
    assert result["status"] == "checks_passed", result
    assert [r["product"] for r in result["results"]] == order
    assert all(row["offline_replay_identical"] for row in result["results"])
    tasks = []
    for row in result["results"]:
        product = row["product"]
        adapter = {"fuel": "series", "aicm_traffic": "government", "afac_airports": "retained"}[product]
        item = task(workspace, product, adapter, row["review_period"], row["retention_run_id"])
        item["workspace"] = row["workspace"]
        tasks.append(item)
    round_root = workspace / "readiness"
    before = readiness.inventory(batch)
    verified = readiness.execute(recipe(tasks), round_root, write=True)
    assert verified["status"] == "checks_passed" and verified["ready_for_review"]
    assert not verified["ready_for_calendar_incorporation"] and not verified["ready_for_automatic_execution"]
    assert all(r["collection_basis"] == "retained" for r in verified["results"])
    by_product = {r["product"]: r for r in verified["results"]}
    assert "publication_calendar_completeness_not_verified" in by_product["fuel"]["source_conditions"]
    assert (
        "publication_calendar_completeness_not_verified"
        not in by_product["aicm_traffic"]["source_conditions"]
    )
    checked = readiness.execute(recipe(tasks), round_root, check=True)
    assert checked["ready_for_review"] and readiness.inventory(batch) == before
    assert checked["activation"] == "none" and checked["publication"] == "not_authorized"


@pytest.mark.parametrize(
    "failed_product,module",
    [
        ("aicm_traffic", government_candidate),
        ("fuel", series_candidate),
    ],
)
def test_mixed_required_failure_uses_correct_checker_and_preserves_earlier_legacy_success(
    workspace, mixed_sources, monkeypatch, failed_product, module
):
    later = "fuel" if failed_product == "aicm_traffic" else "aicm_traffic"
    proposal = mixed_recipe(mixed_sources, ["afac_airports", failed_product, later])
    calls = []

    def failing(*args, **kwargs):
        calls.append((args[1], kwargs))
        raise ValueError("independent required-checker failure")

    monkeypatch.setattr(module, "run", failing)
    batch = workspace / "batch"
    result = retained_round.execute(proposal, batch, write=True)
    assert result["status"] == "blocked" and result["failed_action"] == "certify"
    assert [r["product"] for r in result["results"]] == ["afac_airports"]
    assert calls == [(failed_product, {"execute": True})]
    assert result["remaining_products_not_started"] == 1
    assert list((batch / "afac_airports-2026M07/data/gold").glob("*.parquet"))
    assert not (batch / (later + "-" + ("2026Q3" if later == "fuel" else "2026M07"))).exists()
    assert result["activation"] == "none" and result["publication"] == "not_authorized"
