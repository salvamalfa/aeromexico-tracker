"""Actual SOURCE selector and verifier execute in the manifest's Git worktree."""

import json
import shutil
import subprocess
import sys

import pytest

from src.fare_quotes.aggregate import build_averages
from src.publish import fare_scope, issuer_scope, manifest, presentation_release
from src.web_export.writer import write_json
from tests._fare_pinned_source_fixture import commit, create_source_release
from tests.test_fare_averages import observation, private


@pytest.fixture(scope="module")
def source_release(tmp_path_factory):
    repo = tmp_path_factory.mktemp("pinned-source") / "repo"
    deployed = create_source_release(repo)
    # This release is valid with its real public verifier before code drift.
    checked = subprocess.run([
        sys.executable, "-B", "scripts/check_pages_publication.py", str(repo / "site"),
    ], cwd=repo, capture_output=True, text=True)
    assert checked.returncode == 0, checked.stdout + checked.stderr
    with (repo / "src/config.py").open("a", encoding="utf-8") as stream:
        stream.write("\n# An unrelated, later runtime edition.\n")
    changed = subprocess.run([
        sys.executable, "-B", "-m", "src.publish.source_data_scope", str(repo / "site"),
    ], cwd=repo, capture_output=True, text=True)
    assert changed.returncode == 1
    assert "Source runtime differs from its reviewed producer" in changed.stdout
    # The current selector must never be used to reinterpret the old release.
    (repo / "scripts/check_pages_publication.py").write_text("raise RuntimeError('current selector used')\n")
    current = commit(repo, "unrelated later runtime and selector")
    return repo, deployed, current


def test_pinned_original_source_selector_and_verifier_accept_exact_baseline(source_release):
    repo, deployed, _ = source_release
    spec = {"baseline_commit": deployed,
            "baseline_manifest_sha256": fare_scope.sha((repo / "site" / manifest.MANIFEST_NAME).read_bytes())}
    checked = issuer_scope.verify_historical_baseline(repo, spec, repo / "site", require_site_match=True)
    assert checked == manifest.load_manifest(repo / "site")


def test_original_strong_source_rejection_never_falls_back_to_generic(source_release, tmp_path):
    repo, _, current = source_release
    checkout = tmp_path / "invalid-source"
    subprocess.run(["git", "worktree", "add", "--detach", str(checkout), current], cwd=repo, check=True, capture_output=True)
    try:
        site = checkout / "site"
        before = manifest.load_manifest(site)
        path = site / "data/v1/executive.json"
        path.write_bytes(path.read_bytes() + b" ")
        manifest.write_manifest(site, manifest.build_manifest(
            site, before["analysis_manifest"], contracts=before["contracts"], code_commit=before["code_commit"],
        ))
        invalid_commit = commit(checkout, "invalid SOURCE with a self-consistent manifest")
        spec = {"baseline_commit": invalid_commit,
                "baseline_manifest_sha256": fare_scope.sha((site / manifest.MANIFEST_NAME).read_bytes())}
        with pytest.raises(ValueError, match="own released verifier rejected its site"):
            issuer_scope.verify_historical_baseline(repo, spec, site, require_site_match=True)
        reports = [json.loads(p.read_bytes()) for p in (repo / "tmp/approval-replay-diagnostics").glob("*.json")]
        assert any("Source data update changed historical bytes" in r["stdout"] for r in reports)
    finally:
        subprocess.run(["git", "worktree", "remove", str(checkout)], cwd=repo, check=True, capture_output=True)


def test_fare_overlay_replays_real_source_without_inventing_afac_producer(source_release, tmp_path):
    repo, deployed, current = source_release
    candidate = tmp_path / "site"
    shutil.copytree(repo / "site", candidate)
    write_json(candidate / fare_scope.DATA, build_averages(private(observation())))
    proof = {
        "schema_version": fare_scope.SCHEMA, "baseline_commit": deployed,
        "baseline_manifest_sha256": fare_scope.sha((repo / "site" / manifest.MANIFEST_NAME).read_bytes()),
        "aggregate_sha256": fare_scope.sha((candidate / fare_scope.DATA).read_bytes()),
        "private_input_sha256": "0" * 64,
        "policy_sha256": fare_scope.sha((repo / fare_scope.POLICY).read_bytes()),
        "public_contract_sha256": fare_scope.sha((repo / "contracts/web/fare-averages.schema.json").read_bytes()),
    }
    write_json(candidate / fare_scope.PROOF, proof)
    before = manifest.load_manifest(candidate)
    manifest.write_manifest(candidate, manifest.build_manifest(
        candidate, before["analysis_manifest"],
        contracts={**before["contracts"], "fare-averages.schema.json": proof["public_contract_sha256"]},
        code_commit=current,
    ))
    assert fare_scope.verify_fare_site(candidate, repo) == []
    assert presentation_release.presentation_receipt(repo, candidate, deployed, manifest.load_manifest(candidate)) is None
    assert presentation_release.embed_presentation_receipt(b"<head></head>", None) == b"<head></head>"
    path = candidate / "data/v1/executive.json"
    path.write_bytes(path.read_bytes() + b" ")
    manifest.write_manifest(candidate, manifest.build_manifest(
        candidate, before["analysis_manifest"], contracts=manifest.load_manifest(candidate)["contracts"], code_commit=current,
    ))
    assert "protected public data" in str(fare_scope.verify_fare_site(candidate, repo))


@pytest.mark.parametrize("mutation", ["payload", "manifest", "extra"])
def test_exact_historical_input_cannot_nominate_other_bytes(source_release, tmp_path, mutation):
    repo, deployed, _ = source_release
    candidate = tmp_path / "site"
    shutil.copytree(repo / "site", candidate)
    spec = {"baseline_commit": deployed,
            "baseline_manifest_sha256": fare_scope.sha((candidate / manifest.MANIFEST_NAME).read_bytes())}
    target = candidate / {"payload": "index.html", "manifest": manifest.MANIFEST_NAME, "extra": "unmanifested.json"}[mutation]
    target.write_bytes(target.read_bytes() + b" " if target.exists() else b"{}")
    with pytest.raises(ValueError, match="exact committed manifest"):
        issuer_scope.verify_historical_baseline(repo, spec, candidate, require_site_match=True)
