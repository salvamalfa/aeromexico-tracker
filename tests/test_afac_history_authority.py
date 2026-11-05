"""Only synthetic temporary decisions; no real consent, ledger or source mutation."""

import copy
import json
from types import SimpleNamespace

import pytest

from src.publish import afac_history_contract as contract
from src.publish import afac_history_update as update


def retained(tmp_path, folder, value):
    raw = contract.encoded(value)
    path = tmp_path / "analysis_runs/dashboard_updates" / folder / (contract.sha(raw) + ".json")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)
    return {"path": path.relative_to(tmp_path).as_posix(), "sha256": contract.sha(raw)}


def decision(tmp_path, *, audit_change=None, authority_change=None):
    # This minimal scope is a fixture boundary for authority equality. Production
    # evaluate/anchor separately validate its full closed contract and physical replay.
    scope = {"fixture_exact_scope": "current"}
    audit = {
        "schema_version": "afac_history_source_audit_v2",
        "status": "passed",
        "scope": scope,
        "unresolved_findings": [],
        "reviewer_reference": "synthetic pytest audit",
    }
    if audit_change:
        audit_change(audit)
    audit_ref = retained(tmp_path, "audits", audit)
    value = {
        "schema_version": "afac_history_authorization_v2",
        "status": "authorized",
        "scope": scope,
        "source_audit": audit_ref,
        "owner_consent": {
            "source_reference": "synthetic pytest only",
            "instruction": "Fixture data decision; never a real approval",
            "received_at": "2026-01-01T00:00:00Z",
        },
    }
    if authority_change:
        authority_change(value)
    return {"authorization": retained(tmp_path, "authorizations", value)}, scope


def test_exact_data_authority_and_independent_audit_are_both_required(tmp_path):
    request, scope = decision(tmp_path)
    authority_sha, audit_sha = update.authority(tmp_path, request, scope)
    assert authority_sha == request["authorization"]["sha256"]
    assert len(audit_sha) == 64
    with pytest.raises(ValueError, match="retained consent"):
        update.authority(tmp_path, {"authorization": None}, scope)


@pytest.mark.parametrize(
    "field,value",
    [
        ("schema_version", "quarterly_story_authorization_v1"),
        ("status", "revoked"),
        ("scope", {"fixture_exact_scope": "earlier_708"}),
        (
            "owner_consent",
            {"source_reference": "", "instruction": "fixture", "received_at": "2026-01-01T00:00:00Z"},
        ),
        (
            "owner_consent",
            {"source_reference": "fixture", "instruction": "fixture", "received_at": "2999-01-01T00:00:00Z"},
        ),
        (
            "owner_consent",
            {"source_reference": "fixture", "instruction": "fixture", "received_at": "2026-01-01T00:00:00"},
        ),
    ],
)
def test_prior_editorial_decision_is_never_transferred(tmp_path, field, value):
    request, scope = decision(tmp_path, authority_change=lambda decision: decision.update({field: value}))
    with pytest.raises(ValueError):
        update.authority(tmp_path, request, scope)


@pytest.mark.parametrize(
    "field,value",
    [
        ("status", "failed"),
        ("scope", {"fixture_exact_scope": "another"}),
        ("unresolved_findings", ["unresolved source identity"]),
        ("reviewer_reference", ""),
        ("schema_version", "quarterly_story_source_audit_v1"),
    ],
)
def test_failed_unresolved_or_wrong_scope_audit_blocks_even_fixture_owner_consent(tmp_path, field, value):
    request, scope = decision(tmp_path, audit_change=lambda audit: audit.update({field: value}))
    with pytest.raises(ValueError, match="passing independent audit"):
        update.authority(tmp_path, request, scope)


def test_authority_hash_and_canonical_location_cannot_be_bypassed(tmp_path):
    request, scope = decision(tmp_path)
    path = tmp_path / request["authorization"]["path"]
    other = tmp_path / "tmp/decision.json"
    other.parent.mkdir()
    other.write_bytes(path.read_bytes())
    request["authorization"]["path"] = other.relative_to(tmp_path).as_posix()
    with pytest.raises(ValueError, match="canonical hash path"):
        update.authority(tmp_path, request, scope)
    request["authorization"]["path"] = path.relative_to(tmp_path).as_posix()
    path.write_bytes(path.read_bytes() + b" ")
    with pytest.raises(ValueError, match="retained hash"):
        update.authority(tmp_path, request, scope)


def test_prepare_fixture_is_idempotent_and_cannot_overwrite_unrelated_edit(tmp_path, monkeypatch):
    request, scope = decision(tmp_path)
    reviewed = {"scope": scope, "members": [], "contracts": {}}
    monkeypatch.setattr(update, "PATHS", SimpleNamespace(root=tmp_path))
    monkeypatch.setattr(update, "inspect", lambda _: copy.deepcopy(reviewed))
    monkeypatch.setattr(update, "request_inputs", lambda *_: (None, copy.deepcopy(request)))
    # Only the historical/native inspection is a fixture here; real authority,
    # canonical file pins and the actual prepare writer execute unchanged.
    first = update.prepare("fixture")
    path = tmp_path / contract.ANCHOR
    before = path.read_bytes()
    assert update.prepare("fixture") == first
    assert path.read_bytes() == before
    assert not list(path.parent.glob("*.tmp"))
    path.write_bytes(contract.encoded({"unrelated": True}))
    with pytest.raises(ValueError, match="unrelated local edit"):
        update.prepare("fixture")
    assert json.loads(path.read_bytes()) == {"unrelated": True}


def test_private_inspection_retains_only_exact_review_bytes_without_any_decision(tmp_path):
    outputs = {name: b"synthetic candidate" for name in [*contract.TARGETS, *update.members.BTS_TARGETS]}
    reviewed = {"status": "scope_inspected_not_published", "scope": {"data_files": contract.pins(outputs)}}
    destination = tmp_path / "tmp/inspected"
    update.retain_inspection(tmp_path, destination, reviewed, outputs)
    assert json.loads((destination / "inspection.json").read_bytes()) == reviewed
    assert {name: (destination / name).read_bytes() for name in outputs} == outputs
    assert not (tmp_path / contract.ANCHOR).exists()
    assert not (tmp_path / "analysis_runs").exists()
    with pytest.raises(ValueError, match="new physical private"):
        update.retain_inspection(tmp_path, destination, reviewed, outputs)


@pytest.mark.parametrize("out", ["site", "analysis_runs/authorizations", "tmp/../site", "../outside"])
def test_inspection_cannot_replace_runtime_or_authority(tmp_path, out):
    with pytest.raises(ValueError):
        update.retain_inspection(tmp_path, out, {"scope": {"data_files": []}}, {})
