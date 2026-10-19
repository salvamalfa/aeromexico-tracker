"""Offline retention preserves capture identity and enforces immutable certification."""

from datetime import UTC, datetime
import json
import shutil
from uuid import uuid4

import httpx
import pandas as pd
import pytest

from src.common.storage import save_bronze
from src.source_updates import retained
from src.source_updates.catalog import ROOT
from tests.test_source_update_afac_airports import workbook


@pytest.fixture
def candidate(tmp_path, monkeypatch):
    workspace = ROOT / "tmp/source-updates" / ("test-retained-" + uuid4().hex)
    source = tmp_path / "bronze"
    path = save_bronze(
        workbook(),
        "afac",
        "airport",
        "2026M07",
        "xlsx",
        "https://www.gob.mx/cms/uploads/attachment/file/1100275/producto-aeropuerto-2006-2026-jul-27082026.xlsx",
        "manual",
        bronze_root=source,
        downloaded_at=datetime(2026, 9, 13, tzinfo=UTC),
    )

    def denied(*args, **kwargs):
        raise AssertionError("No HTTP allowed")

    monkeypatch.setattr(httpx.Client, "send", denied)
    try:
        yield workspace, source, {"workbook": path.relative_to(source).as_posix()}
    finally:
        shutil.rmtree(workspace, ignore_errors=True)


def test_dry_run_writes_nothing_and_retention_preserves_source_capture(candidate):
    workspace, source, selected = candidate
    result = retained.retain(workspace, source, "afac_airports", selected)
    assert result["network_requests"] == 0 and not workspace.exists()
    stored = retained.retain(workspace, source, "afac_airports", selected, execute=True)
    original = stored["originals"]["workbook"]
    assert original["downloaded_at"].startswith("2026-09-13")
    assert original["source_system"] == "afac" and not stored["new_source_capture"]
    inputs, _ = retained.originals(workspace, "afac_airports", stored["run_id"], "2026-10-19T12:00:00-06:00")
    assert inputs["workbook"][0] == (source / selected["workbook"]).read_bytes()
    with pytest.raises(ValueError, match="new candidate"):
        retained.retain(workspace, source, "afac_airports", selected, execute=True)


def test_certification_lineage_replay_and_immutable_guard(candidate):
    workspace, source, selected = candidate
    saved = retained.retain(workspace, source, "afac_airports", selected, execute=True)
    args = (workspace, "afac_airports", "2026M07", "2026-10-19T12:00:00-06:00", saved["run_id"])
    dry = retained.run(*args)
    assert dry["mode"] == "dry_run" and not (workspace / "data/gold").exists()
    result = retained.run(*args, execute=True)
    assert result["rows"] == 42 and result["lineage"]["status"] == "passed"
    before = {p: retained.digest(p) for p in workspace.rglob("*") if p.is_file()}
    check = retained.run(*args, check=True)
    assert check["output_sha256"] == result["output_sha256"]
    assert before == {p: retained.digest(p) for p in workspace.rglob("*") if p.is_file()}
    with pytest.raises(ValueError, match="immutable"):
        retained.run(*args, execute=True)
    path = workspace / "data/gold/fact_afac_airport_observations.parquet"
    frame = pd.read_parquet(path)
    frame.loc[0, "value"] += 1
    frame.to_parquet(path, index=False)
    with pytest.raises(ValueError, match="Output differs"):
        retained.run(*args, check=True)


@pytest.mark.parametrize("kind", ["bytes", "sidecar", "manifest", "traversal", "absolute", "unknown_role"])
def test_original_tampering_and_path_escape_block(candidate, kind):
    workspace, source, selected = candidate
    path = source / selected["workbook"]
    if kind == "bytes":
        path.write_bytes(b"changed")
    elif kind == "sidecar":
        meta = path.with_name(path.name + ".meta.json")
        data = json.loads(meta.read_text())
        data["downloaded_at"] = "2026-01-01T00:00:00Z"
        meta.write_text(json.dumps(data))
    elif kind == "manifest":
        manifest = source / "_manifest.jsonl"
        data = json.loads(manifest.read_text())
        data["source_system"] = "aerodatabox"
        manifest.write_text(json.dumps(data) + "\n")
    elif kind == "traversal":
        selected["workbook"] = "../bronze/" + selected["workbook"]
    elif kind == "absolute":
        selected["workbook"] = str(path)
    else:
        selected = {"other": selected["workbook"]}
    with pytest.raises(ValueError):
        retained.retain(workspace, source, "afac_airports", selected, execute=True)
    assert not workspace.exists()


def test_retention_manifest_and_cutoff_are_reverified(candidate):
    workspace, source, selected = candidate
    saved = retained.retain(workspace, source, "afac_airports", selected, execute=True)
    with pytest.raises(ValueError, match="after requested cutoff"):
        retained.originals(workspace, "afac_airports", saved["run_id"], "2026-09-12T12:00:00Z")
    manifest = workspace / "data/bronze/_manifest.jsonl"
    manifest.write_text(manifest.read_text() + "\n")
    with pytest.raises(ValueError, match="manifest changed"):
        retained.originals(workspace, "afac_airports", saved["run_id"], "2026-10-19T12:00:00Z")


def test_baseline_hash_is_pinned_and_replayed(candidate):
    workspace, source, selected = candidate
    saved = retained.retain(workspace, source, "afac_airports", selected, execute=True)
    args = (workspace, "afac_airports", "2026M07", "2026-10-19T12:00:00-06:00", saved["run_id"])
    outputs, _ = retained.frames(*args)
    baseline = workspace / "baselines/prior.parquet"
    baseline.parent.mkdir()
    next(iter(outputs.values())).to_parquet(baseline, index=False)
    result = retained.run(*args, execute=True, baseline="baselines/prior.parquet")
    assert result["revisions"]["unchanged"] == 42
    retained.run(*args, check=True)
    frame = pd.read_parquet(baseline)
    frame.loc[0, "value"] += 1
    frame.to_parquet(baseline, index=False)
    with pytest.raises(ValueError, match="baseline or revisions changed"):
        retained.run(*args, check=True)
