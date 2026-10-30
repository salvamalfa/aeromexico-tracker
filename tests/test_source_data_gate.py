"""Adversarial guards for the shared selective source gate, with no live writes."""

import hashlib
import json
from copy import deepcopy

import pytest

from src.publish import source_data_scope as scope
from src.publish import source_data_update as update


def reference(path):
    return {"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def test_physical_reference_rejects_tamper_symlink_and_escape(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    p = repo / "source.json"
    p.write_text("original")
    ref = reference(p)
    assert update.file_ref(ref, repo) == p
    p.write_text("changed")
    with pytest.raises(ValueError):
        update.file_ref(ref, repo)
    link = repo / "linked.json"
    link.symlink_to(p)
    with pytest.raises(ValueError):
        update.file_ref(reference(link), repo)
    outside = tmp_path / "outside.json"
    outside.write_text("private")
    with pytest.raises(ValueError):
        update.file_ref(reference(outside), repo)


def grant(tmp_path):
    spec = {
        k: k
        for k in (
            "product",
            "period_id",
            "source_binding",
            "baseline_commit",
            "data_files",
            "frontend_files",
            "producer_code_version",
            "contract_changes",
        )
    }
    value = {
        "schema_version": "source_data_authorization_v1",
        "status": "authorized",
        "scope": scope.scope(spec),
        "owner_consent": {
            "source_reference": "unit-test-only",
            "instruction": "Synthetic fixture, never publication authority",
            "received_at": "2026-10-01T00:00:00Z",
        },
    }
    p = tmp_path / "analysis_runs/dashboard_updates/authorizations"
    p.mkdir(parents=True)
    raw = (json.dumps(value) + "\n").encode()
    digest = hashlib.sha256(raw).hexdigest()
    file = p / (digest + ".json")
    file.write_bytes(raw)
    spec["authorization_sha256"] = digest
    return spec, {"authorization": reference(file)}, file


def test_inspection_is_not_an_exposure_authority(tmp_path):
    with pytest.raises(ValueError, match="retained owner consent"):
        update.authority({"authorization": None}, {}, tmp_path)


def test_exact_source_exposure_authority_is_bound_to_scope_and_canonical_file(tmp_path):
    spec, request, file = grant(tmp_path)
    assert update.authority(request, spec, tmp_path) == file
    other = deepcopy(spec)
    other["period_id"] = "another-period"
    with pytest.raises(ValueError, match="another exact release"):
        update.authority(request, other, tmp_path)
    renamed = file.with_name("renamed.json")
    renamed.write_bytes(file.read_bytes())
    with pytest.raises(ValueError, match="canonical"):
        update.authority({"authorization": reference(renamed)}, spec, tmp_path)


def test_unknown_source_fails_before_importing_or_publishing():
    with pytest.raises(ValueError, match="no reviewed"):
        scope.adapter("unreviewed_source")


def test_snapshot_preserves_physical_source_changes_and_library_metadata(tmp_path, monkeypatch):
    monkeypatch.setattr(update, "input_snapshot", lambda *a, **k: {})
    p = tmp_path / "source.json"
    p.write_text("original")
    request = {"authorization": None}
    first = update.snapshot(p, request, p, [], {"input_files": [str(p)]}, tmp_path)
    p.write_text("changed")
    second = update.snapshot(p, request, p, [], {"input_files": [str(p)]}, tmp_path)
    assert first != second
