"""Negative contracts for original-source replacement; no approval shortcuts."""

import hashlib
import json
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from src.publish import quarterly_story_scope as scope
from src.publish import quarterly_story_update as update


def test_analysis_slots_require_exact_entities_quarter_and_no_duplicates():
    good = [dict(entity_key=e, period_id="2026Q3", version=e) for e in scope.ENTITIES]
    scope.analysis_slots(good, scope.ENTITIES, "2026Q3")
    for invalid in (good[:-1], good + good[:1], [{**good[0], "period_id": "2026Q2"}, *good[1:]]):
        with pytest.raises(ValueError, match="slots"):
            scope.analysis_slots(invalid, scope.ENTITIES, "2026Q3")


@pytest.fixture
def site_fixture(tmp_path, monkeypatch):
    site = tmp_path / "site"
    site.mkdir()
    config = tmp_path / scope.ANCHOR
    config.parent.mkdir(parents=True)
    config.write_text("{}")
    retained = [dict(entity_key=e, period_id="2026Q2", version=e) for e in scope.ENTITIES]
    superseded = [
        dict(entity_key=e, period_id="2026Q3", version="old" + e) for e in scope.ENTITIES - {"INDUSTRY"}
    ]
    new = [dict(entity_key=e, period_id="2026Q3", version="new" + e) for e in scope.ENTITIES]
    old = dict(analysis_manifest=retained + superseded, files=[])
    spec = dict(
        baseline_commit="a" * 40,
        baseline_manifest_sha256="b" * 64,
        analysis_manifest=new,
        retained_analysis_manifest=retained,
        superseded_analysis_manifest=superseded,
        contracts={},
        data_files=[],
        frontend_files=[dict(path="index.html", sha256=hashlib.sha256(b"new").hexdigest(), bytes=3)],
    )
    (site / "index.html").write_bytes(b"new")
    witness = dict(
        baseline_commit="a" * 40,
        manifest_sha256="b" * 64,
        files_verified=0,
        origin=scope.transport.ORIGIN,
        deployment_run=123,
        deployment_commit="c" * 40,
    )
    proof = dict(
        schema_version="quarterly_story_publication_v1",
        anchor_sha256=scope.sha(config.read_bytes()),
        remote_witness=witness,
        historical_source_status="superseded_Q3_source_not_replayed_not_consumed",
    )
    (site / scope.PROOF).write_text(json.dumps(proof))
    manifest = dict(
        analysis_manifest=sorted(retained + new, key=scope.manifests.analysis_sort_key),
        contracts={},
        files=[],
    )
    (site / scope.manifests.MANIFEST_NAME).write_text(json.dumps(manifest))
    monkeypatch.setattr(scope.transport, "baseline", lambda *a: (old, b"{}"))
    monkeypatch.setattr(scope.transport, "_git", lambda *a: b"")
    monkeypatch.setattr(scope.transport, "frontend_entries", lambda *a: spec["frontend_files"])
    return site, tmp_path, spec, proof


@pytest.mark.parametrize(
    "field,value",
    [
        ("origin", "https://untrusted.invalid"),
        ("files_verified", 1),
        ("deployment_run", "not-a-run"),
        ("deployment_run", 0),
        ("deployment_commit", "unknown"),
        ("baseline_commit", "f" * 40),
        ("manifest_sha256", "f" * 64),
    ],
)
def test_false_remote_witness_is_not_accepted(site_fixture, field, value):
    site, repo, spec, proof = site_fixture
    scope.preserved_files(site, repo, spec)
    proof["remote_witness"][field] = value
    (site / scope.PROOF).write_text(json.dumps(proof))
    with pytest.raises(ValueError, match="proof|witness"):
        scope.preserved_files(site, repo, spec)


def test_witness_site_tree_must_equal_baseline(site_fixture, monkeypatch):
    site, repo, spec, _ = site_fixture
    monkeypatch.setattr(scope.transport, "_git", lambda *a: b"site/changed.json" if "diff" in a else b"")
    with pytest.raises(ValueError, match="deployment differs"):
        scope.preserved_files(site, repo, spec)


def retain(root, category, value):
    raw = json.dumps(value, sort_keys=True).encode()
    digest = hashlib.sha256(raw).hexdigest()
    path = root / "analysis_runs/dashboard_updates" / category / (digest + ".json")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)
    return dict(path=str(path), sha256=digest)


def test_new_authority_requires_exact_scope_and_independent_audit(tmp_path, monkeypatch):
    monkeypatch.setattr(update, "PATHS", SimpleNamespace(root=tmp_path))
    inspected = dict(
        records=[dict(version="new-version")], data_files=["exact"], source_packages=["original"]
    )
    audit = dict(
        schema_version="quarterly_story_source_audit_v1",
        status="passed",
        scope=inspected,
        unresolved_findings=[],
        reviewer_reference="independent-task/exact-review",
    )
    authority = dict(
        schema_version="quarterly_story_authorization_v1",
        state="authorized",
        scope=inspected,
        source_audit=retain(tmp_path, "audits", audit),
        owner_consent=dict(
            source_reference="actual-owner-message",
            instruction="Publish this exact replacement",
            received_at=datetime.now(UTC).isoformat(),
        ),
    )
    request = dict(authorization=retain(tmp_path, "authorizations", authority))
    assert update.authority(request, inspected)
    with pytest.raises(ValueError, match="another source"):
        update.authority(request, {**inspected, "source_packages": ["other"]})
    authority["state"] = "revoked"
    with pytest.raises(ValueError, match="revoked"):
        update.authority(dict(authorization=retain(tmp_path, "authorizations", authority)), inspected)
    with pytest.raises(ValueError, match="new exact-scope"):
        update.authority(dict(authorization=None), inspected)


def test_unresolved_source_findings_cannot_authorize(tmp_path, monkeypatch):
    monkeypatch.setattr(update, "PATHS", SimpleNamespace(root=tmp_path))
    inspected = dict(records=["exact"])
    audit = dict(
        schema_version="quarterly_story_source_audit_v1",
        status="passed",
        scope=inspected,
        unresolved_findings=["blocking"],
        reviewer_reference="independent-task",
    )
    authority = dict(
        schema_version="quarterly_story_authorization_v1",
        state="authorized",
        scope=inspected,
        source_audit=retain(tmp_path, "audits", audit),
        owner_consent=dict(
            source_reference="actual-message",
            instruction="Approve this scope",
            received_at=datetime.now(UTC).isoformat(),
        ),
    )
    with pytest.raises(ValueError, match="independent audit"):
        update.authority(dict(authorization=retain(tmp_path, "authorizations", authority)), inspected)
