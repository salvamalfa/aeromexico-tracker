"""Data exposure has independent exact authority; it never invents thesis approval."""

import hashlib
import json

import pytest

from src.publish import issuer_authority as authority
from src.publish import issuer_update as update


def save(directory, value):
    raw = json.dumps(value, sort_keys=True).encode()
    path = directory / (hashlib.sha256(raw).hexdigest() + ".json")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)
    return path


@pytest.fixture
def grant(tmp_path):
    package = {
        "entity_key": "VIVA_AEROBUS",
        "period_id": "2026Q3",
        "package_id": "package-1",
        "evidence_fingerprint": "1" * 64,
        "source_binding": {"product": "viva_financials", "hash": "2" * 64},
    }
    spec = {
        "baseline_commit": "3" * 40,
        "baseline_manifest_sha256": "4" * 64,
        "producer_code_version": "5" * 64,
        "executive_sha256": "6" * 64,
        "executive_bytes": 123,
    }
    bound = authority.binding(package, spec)
    audit = {
        "schema_version": "issuer_data_audit_v1",
        "status": "passed",
        "binding": bound,
        "unresolved_findings": [],
        "reviewer_reference": "independent-tool-session",
    }
    audit_path = save(tmp_path / "analysis_runs/dashboard_updates/audits", audit)
    auth = {
        "schema_version": "issuer_data_authorization_v1",
        "state": "authorized",
        "binding": bound,
        "source_audit_sha256": audit_path.stem,
        "owner_consent": {
            "source_reference": "trusted-user-message",
            "instruction": "Publish validated data",
            "received_at": "2026-10-30T13:02:00Z",
        },
        "constraints": {"theses": False, "other_entities": False, "industry": False},
    }
    auth_path = save(tmp_path / "analysis_runs/dashboard_updates/authorizations", auth)
    spec["authorization_sha256"] = auth_path.stem
    return tmp_path, package, spec, audit, auth


def test_source_data_can_be_authorized_without_any_thesis_record(grant):
    root, package, spec, audit, auth = grant
    assert authority.authority(package, spec, root) == (auth, audit)
    assert not (root / "analysis_runs/drafts").exists()
    assert not (root / "analysis_runs/lifecycle").exists()


@pytest.mark.parametrize("mutation", ["revoked", "missing_consent", "different_output", "wider_scope"])
def test_data_authority_does_not_generalize_permission(grant, mutation):
    root, package, spec, _, auth = grant
    if mutation == "revoked":
        auth["state"] = "revoked"
    elif mutation == "missing_consent":
        del auth["owner_consent"]["source_reference"]
    elif mutation == "different_output":
        auth["binding"] = {**auth["binding"], "executive_sha256": "9" * 64}
    else:
        auth["constraints"]["industry"] = True
    spec["authorization_sha256"] = save(root / "analysis_runs/dashboard_updates/authorizations", auth).stem
    with pytest.raises(ValueError, match="owner authority"):
        authority.authority(package, spec, root)


@pytest.mark.parametrize("mutation", ["wrong_source", "unresolved", "not_passed", "wrong_producer"])
def test_source_audit_must_cover_exact_source_and_producer(grant, mutation):
    root, package, spec, audit, auth = grant
    if mutation == "wrong_source":
        audit["binding"]["source_binding"] = {"product": "volaris_sec"}
    elif mutation == "unresolved":
        audit["unresolved_findings"] = ["mismatched units"]
    elif mutation == "not_passed":
        audit["status"] = "draft"
    else:
        audit["binding"]["producer_code_version"] = "8" * 64
    auth["source_audit_sha256"] = save(root / "analysis_runs/dashboard_updates/audits", audit).stem
    # Copy the original expected binding: the authority's binding must stay exact
    # while an altered audit cannot authorize its mismatched producer/source.
    auth["binding"] = authority.binding(package, spec)
    spec["authorization_sha256"] = save(root / "analysis_runs/dashboard_updates/authorizations", auth).stem
    with pytest.raises(ValueError, match="source audit"):
        authority.authority(package, spec, root)


def test_source_and_authorization_bytes_are_immutable(grant):
    root, package, spec, _, _ = grant
    path = root / "analysis_runs/dashboard_updates/authorizations" / (spec["authorization_sha256"] + ".json")
    path.write_bytes(path.read_bytes() + b" ")
    with pytest.raises(ValueError, match="changed"):
        authority.authority(package, spec, root)


def test_no_change_is_recomputed_not_trusted_from_worker(tmp_path, monkeypatch):
    package = tmp_path / "package.json"
    package.write_text(json.dumps({"source_binding": {"source": "x"}}))
    monkeypatch.setattr(update, "inspect_data", lambda *a: {"status": "data_change"})
    monkeypatch.setattr(
        update, "verify_historical_baseline", lambda *a: pytest.fail("must not bless changed data")
    )
    with pytest.raises(ValueError, match="changes a visible"):
        update.verify_no_visual_change(package, {"source": "x"})
    with pytest.raises(ValueError, match="another source"):
        update.verify_no_visual_change(package, {"source": "different"})


def test_pin_preparation_preserves_other_owners_local_edits(tmp_path, monkeypatch):
    monkeypatch.setattr(update, "PATHS", type("Paths", (), {"root": tmp_path})())
    path = tmp_path / "config/publish/issuer-release.json"
    path.parent.mkdir(parents=True)
    path.write_text('{"other_job": true}')
    monkeypatch.setattr(update.subprocess, "run", lambda *a, **k: type("Result", (), {"returncode": 1})())
    with pytest.raises(ValueError, match="unrelated local edit"):
        update._write_pins([("config/publish/issuer-release.json", {"this_job": True})])
    assert json.loads(path.read_bytes()) == {"other_job": True}
