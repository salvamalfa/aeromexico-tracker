"""Reject incompatible capture aliases and omitted gates before candidate writes."""

import shutil
from uuid import uuid4

import pytest

from src.source_updates.build import build, worker
from src.source_updates.catalog import ROOT
from src.source_updates.collection import selection_plan
from src.source_updates.recipes import describe


@pytest.mark.parametrize("product", ["am_sec", "volaris_sec", "delta_sec", "ryanair_sec"])
@pytest.mark.parametrize("alias", ["sec", "sec_edgar", "sec_filing"])
def test_corporate_capture_alias_must_match_the_legacy_parser(product, alias):
    workspace = ROOT / "tmp/source-updates/alias-preflight-never-written"
    selected = {
        "version": 1,
        "items": [
            {
                "id": "fixture",
                "product": product,
                "source_system": alias,
                "entity": "fixture",
                "period": "2026Q3",
                "purpose": "data",
                "url": "https://www.sec.gov/Archives/synthetic-fixture.htm",
                "extension": "htm",
                "mode": "manual",
                "local_file": "fixture.htm",
                "sha256": "0" * 64,
            }
        ],
    }
    assert describe(product)["bronze_source_systems"] == ["sec"]
    if alias == "sec":
        assert selection_plan(selected, workspace)["base_requests"] == 0
    else:
        with pytest.raises(ValueError, match="parser-compatible Bronze alias"):
            selection_plan(selected, workspace)
    assert not workspace.exists()


@pytest.mark.parametrize("alias", ["afac", "afac_datatur"])
def test_afac_bronze_alias_is_distinct_from_its_datatur_output(alias):
    from src.source_updates.catalog import bronze_aliases, load_catalog

    assert "afac_datatur" in load_catalog()["afac"]["source_systems"]
    assert (alias in bronze_aliases("afac_carriers")) == (alias == "afac")


@pytest.mark.parametrize(
    "step,predecessor",
    [
        ("transform.stage6", "transform.validate_silver"),
        ("transform.validate_stage6", "transform.stage6"),
        ("parse.sec", "parse.peer_discovery"),
    ],
)
def test_existing_files_cannot_replace_required_pipeline_predecessors(step, predecessor):
    workspace = ROOT / "tmp/source-updates" / ("unvalidated-" + uuid4().hex)
    try:
        silver = workspace / "data/silver"
        silver.mkdir(parents=True)
        (silver / "unvalidated.parquet").write_bytes(b"unvalidated fixture")
        with pytest.raises(ValueError, match=predecessor):
            build(workspace, [step], execute=True)
        assert not (workspace / "config").exists()
        assert not (workspace / "receipts").exists()
        assert not (workspace / "data/gold").exists()
    finally:
        shutil.rmtree(workspace)


def test_complete_explicit_parser_chain_has_no_writes():
    workspace = ROOT / "tmp/source-updates/dependency-preflight-never-written"
    result = build(workspace, ["parse.peer_discovery", "parse.sec"])
    assert result["required_predecessors"]["parse.sec"] == ("parse.peer_discovery",)
    assert result["network_requests"] == 0
    assert not workspace.exists()


def test_predecessor_must_be_before_its_consumer():
    with pytest.raises(ValueError, match="parse.peer_discovery"):
        build(ROOT / "tmp/source-updates/dependency-preflight", ["parse.sec", "parse.peer_discovery"])


def test_unavailable_composite_parser_is_not_silently_omitted():
    with pytest.raises(ValueError, match="unavailable.*parse.complementary"):
        build(ROOT / "tmp/source-updates/dependency-preflight", ["parse.afac", "transform.stage4"])


def test_worker_cannot_bypass_dependency_preflight():
    workspace = ROOT / "tmp/source-updates/dependency-preflight-never-written"
    with pytest.raises(ValueError, match="transform.validate_silver"):
        worker(workspace, ["transform.stage6"], workspace / "receipts/fixture.json")
    assert not workspace.exists()


def test_parser_alias_cannot_drift_outside_the_institution_catalogue(monkeypatch):
    import src.source_updates.catalog as catalog

    sources = catalog.load_catalog()
    sources["sec_edgar"]["source_systems"] = ["sec_edgar", "sec_filing"]
    monkeypatch.setattr(catalog, "load_catalog", lambda: sources)
    with pytest.raises(ValueError, match="absent from the institution catalogue"):
        catalog.bronze_aliases("am_sec")
