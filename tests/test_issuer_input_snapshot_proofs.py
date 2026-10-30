"""A historical SEC header is a physical approval dependency, not optional text."""

import json
from pathlib import Path

import pytest

from src.publish.issuer_authority import input_snapshot


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value))
    return path


def test_snapshot_retains_proof_original_and_sidecar_and_rejects_missing_proof(tmp_path):
    record = write(
        tmp_path / "analysis_runs/drafts/test.json",
        {"draft": {"package_id": "p", "calculation_fingerprint": "c"}},
    )
    write(
        tmp_path / "analysis_runs/evidence/p.json",
        {"sources": [{"source_file": "document.html", "proofs": [{"source_file": "sec/header.txt"}]}]},
    )
    write(tmp_path / "analysis_runs/quantitative/c.json", {})
    write(tmp_path / "data/bronze/document.html", {"body": "source"})
    with pytest.raises(ValueError, match="missing"):
        input_snapshot([record], {}, repo=tmp_path)
    header = write(tmp_path / "data/bronze/sec/header.txt", {"body": "SEC header"})
    sidecar = write(Path(str(header) + ".meta.json"), {"hash": "fixture"})
    snap = input_snapshot([record], {}, repo=tmp_path)
    assert str(header.relative_to(tmp_path)) in snap
    assert str(sidecar.relative_to(tmp_path)) in snap
    header.write_text("changed")
    assert input_snapshot([record], {}, repo=tmp_path) != snap
