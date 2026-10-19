"""Original verification provenance cannot authorize new thesis identities."""

import hashlib
import json
import subprocess
from copy import deepcopy

import pytest

from src.publish.approval_anchor import approval_implementation


def git(root, *args):
    return subprocess.check_output(["git", *args], cwd=root, text=True).strip()


@pytest.fixture
def published(tmp_path):
    git(tmp_path, "init", "-q")
    git(tmp_path, "config", "user.name", "Test")
    git(tmp_path, "config", "user.email", "test@example.invalid")
    (tmp_path / "source").write_text("initial")
    git(tmp_path, "add", ".")
    git(tmp_path, "commit", "-qm", "initial")
    initial = git(tmp_path, "rev-parse", "HEAD")
    (tmp_path / "source").write_text("approved implementation")
    git(tmp_path, "commit", "-qam", "approved code")
    code = git(tmp_path, "rev-parse", "HEAD")
    baseline = {
        "code_commit": code,
        "analysis_manifest": [{"period_id": "2026Q2", "version": "a" * 64, "approval_event": "b" * 64}],
        "files": [{"path": "data/v1/analysis/2026Q2.json", "sha256": "c" * 64, "bytes": 12}],
    }
    p = tmp_path / "site/publication_manifest.json"
    p.parent.mkdir()
    raw = json.dumps(baseline).encode()
    p.write_bytes(raw)
    git(tmp_path, "add", ".")
    git(tmp_path, "commit", "-qm", "published site")
    original = git(tmp_path, "rev-parse", "HEAD")
    (tmp_path / "source").write_text("new map implementation")
    git(tmp_path, "commit", "-qam", "new presentation code")
    trusted = git(tmp_path, "rev-parse", "HEAD")
    anchor = {
        "schema_version": "preserved_analysis_anchor_v1",
        "published_site_commit": original,
        "published_manifest_sha256": hashlib.sha256(raw).hexdigest(),
        "implementation_commit": code,
    }
    p = tmp_path / "config/publish/preserved-analysis.json"
    p.parent.mkdir(parents=True)
    p.write_text(json.dumps(anchor))
    return tmp_path, trusted, baseline, anchor, code, initial


def test_new_frontend_commit_retains_original_verifier_without_rewriting_manifest(published):
    root, trusted, baseline, _, code, _ = published
    baseline = {**baseline, "code_commit": trusted}
    before = deepcopy(baseline)
    assert approval_implementation(root, trusted, baseline) == code
    assert baseline == before


@pytest.mark.parametrize(
    "field,value",
    [
        ("published_manifest_sha256", "f" * 64),
        ("implementation_commit", "invalid"),
        ("schema_version", "unknown"),
        ("extra", True),
    ],
)
def test_invalid_or_modified_anchor_is_rejected(published, field, value):
    root, trusted, baseline, anchor, _, _ = published
    anchor[field] = value
    (root / "config/publish/preserved-analysis.json").write_text(json.dumps(anchor))
    with pytest.raises(ValueError):
        approval_implementation(root, trusted, baseline)


def test_anchor_must_be_in_trusted_history_and_code_must_match_original_manifest(published):
    root, trusted, baseline, anchor, code, initial = published
    with pytest.raises(ValueError, match="trusted publication history"):
        approval_implementation(root, code, baseline)
    anchor["implementation_commit"] = initial
    (root / "config/publish/preserved-analysis.json").write_text(json.dumps(anchor))
    with pytest.raises(ValueError, match="implementation differs"):
        approval_implementation(root, trusted, baseline)


@pytest.mark.parametrize("field", ["version", "approval_event", "entity_key"])
def test_another_identity_or_approval_cannot_inherit_anchor(published, field):
    root, trusted, baseline, _, _, _ = published
    baseline["analysis_manifest"][0][field] = "changed"
    with pytest.raises(ValueError, match="another thesis identity"):
        approval_implementation(root, trusted, baseline)


@pytest.mark.parametrize("change", ["sha256", "bytes", "missing", "duplicate"])
def test_changed_missing_or_duplicate_thesis_bytes_cannot_inherit_anchor(published, change):
    root, trusted, baseline, _, _, _ = published
    if change == "missing":
        baseline["files"] = []
    elif change == "duplicate":
        baseline["files"] *= 2
    elif change == "sha256":
        baseline["files"][0][change] = "f" * 64
    else:
        baseline["files"][0][change] += 1
    with pytest.raises(ValueError):
        approval_implementation(root, trusted, baseline)


def test_anchor_does_not_bind_other_independently_published_data(published):
    root, trusted, baseline, _, code, _ = published
    baseline["files"].append({"path": "data/v1/news.json", "sha256": "d" * 64, "bytes": 20})
    assert approval_implementation(root, trusted, baseline) == code


def test_absent_anchor_keeps_existing_verifier_and_symlink_is_rejected(published):
    root, trusted, baseline, _, _, _ = published
    p = root / "config/publish/preserved-analysis.json"
    raw = p.read_bytes()
    p.unlink()
    assert approval_implementation(root, trusted, baseline) == trusted
    other = root / "anchor.json"
    other.write_bytes(raw)
    p.symlink_to(other)
    with pytest.raises(ValueError, match="symlink"):
        approval_implementation(root, trusted, baseline)
