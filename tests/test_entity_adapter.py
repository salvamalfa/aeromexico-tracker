"""Boundary checks for source-replayed capsules; no production approvals."""

from __future__ import annotations

import hashlib
import json
from types import SimpleNamespace

import pytest

from src.analysis_agent import entity_adapter as adapter


@pytest.mark.parametrize(
    "field,value",
    [
        ("package_id", "../../other"),
        ("calculation_fingerprint", "../other"),
        ("entity_key", "../VOLARIS"),
        ("period_id", "2026H1"),
    ],
)
def test_invalid_input_identity_rejected_before_read(monkeypatch, field, value):
    draft = {
        "entity_key": "VOLARIS",
        "period_id": "2026Q2",
        "package_id": "VOLARIS_2026Q2_" + "a" * 64,
        "calculation_fingerprint": "b" * 64,
    }
    draft[field] = value
    monkeypatch.setattr(adapter, "read", lambda path: pytest.fail("Untrusted path read"))
    with pytest.raises(ValueError):
        adapter.verified_inputs({"draft": draft})


def test_unreviewed_extractor_cannot_execute(tmp_path, monkeypatch):
    (tmp_path / "prepare.py").write_text("raise RuntimeError('unexpected execution')")
    monkeypatch.setattr(adapter.subprocess, "run", lambda *a, **k: pytest.fail("Unreviewed code executed"))
    with pytest.raises(ValueError, match="Unreviewed extractor"):
        adapter._replay({"entity_key": "VOLARIS"}, tmp_path)


@pytest.mark.parametrize(
    "change", ["original", "capture_hash", "capture_url", "late_capture", "http_failure"]
)
def test_original_and_capture_proof_fail_closed(tmp_path, monkeypatch, change):
    bronze = tmp_path / "bronze"
    bronze.mkdir()
    original = bronze / "source.pdf"
    raw = b"synthetic source bytes for a boundary test"
    original.write_bytes(raw)
    digest = hashlib.sha256(raw).hexdigest()
    source = {
        "artifact_id": "test_artifact",
        "source_file": "source.pdf",
        "source_url": "https://www.sec.gov/Archives/test.pdf",
        "artifact_sha256": digest,
    }
    meta = {
        "sha256": digest,
        "source_url": source["source_url"],
        "http_status": 200,
        "downloaded_at": "2026-08-24T03:15:17+00:00",
    }
    if change == "original":
        original.write_bytes(b"changed")
    elif change == "capture_hash":
        meta["sha256"] = "a" * 64
    elif change == "capture_url":
        meta["source_url"] = "https://example.com/different"
    elif change == "late_capture":
        meta["downloaded_at"] = "2026-10-14T00:00:00+00:00"
    else:
        meta["http_status"] = 404
    (bronze / "source.pdf.meta.json").write_text(json.dumps(meta))
    monkeypatch.setattr(adapter, "PATHS", SimpleNamespace(root=tmp_path, bronze=bronze))
    with pytest.raises(ValueError):
        adapter._sources({"artifacts": [source]})


@pytest.mark.parametrize(
    "filename", ["analyst.py", "evidence.py", "lifecycle_identity.py", "entities.py", "uv.lock"]
)
def test_shared_validation_change_invalidates_entity_presentation(monkeypatch, filename):
    from src.analysis_agent.analyst import SKILL

    baseline = adapter.code_version()
    original_sha = adapter.sha
    record = {"code_version": baseline, "prompt_version": original_sha(SKILL)}
    monkeypatch.setattr(
        adapter, "sha", lambda path: "0" * 64 if path.name == filename else original_sha(path)
    )
    with pytest.raises(ValueError, match="implementation changed"):
        adapter.require_current_presentation(record)


@pytest.mark.parametrize("format_fields", [{"formatted": "1,0"}, {"formatted_value": "1,0"}])
def test_normalization_accepts_either_reviewed_format_field(format_fields):
    package = {
        "entity_key": "VOLARIS",
        "period_id": "2026Q2",
        "sources": [],
        "package_id": "synthetic",
        "evidence_fingerprint": "test",
    }
    node = {
        "calculation_id": "calc_test",
        "value": 1.0,
        "unit": "USD",
        "period_id": "2026Q2",
        **format_fields,
    }
    _, calculated, _ = adapter._normalize(
        package, {"inputs": [], "calculations": {"calc_test": node}}, {"excerpts": []}, {"claims": []}
    )
    assert calculated["nodes"][0]["formatted_value"] == "1,0"
