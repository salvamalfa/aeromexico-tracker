"""Real Fare -> original SOURCE official-map -> exact financial baseline."""

import json
import shutil
import subprocess
import sys

import pytest

from src.fare_quotes.aggregate import build_averages
from src.publish import fare_scope, manifest, source_data_scope
from src.web_export.writer import write_json
from tests._fare_pinned_source_fixture import commit, create_source_release
from tests._site_publication_parity import (
    encoded, official_map_baseline, preserved_financial_projection, sha, verify_current_publication,
)
from tests.test_fare_averages import observation, private


@pytest.fixture(scope="module")
def official_fare(tmp_path_factory):
    repo = tmp_path_factory.mktemp("fare-parity") / "repo"
    source_commit = create_source_release(repo, official=True)
    before = manifest.load_manifest(repo / "site")
    source_spec = json.loads((repo / source_data_scope.ANCHOR).read_bytes())
    checked = subprocess.run([sys.executable, "-B", "scripts/check_pages_publication.py", str(repo / "site")],
                             cwd=repo, capture_output=True, text=True)
    assert checked.returncode == 0, checked.stdout + checked.stderr
    # The parent must be checked using its own committed anchor and producer,
    # not this later pending SOURCE edition or the candidate's Python runtime.
    (repo / source_data_scope.ANCHOR).write_text('{"pending":"another source edition"}')
    with (repo / "src/config.py").open("a", encoding="utf-8") as stream:
        stream.write("\n# Later unrelated runtime.\n")
    code = commit(repo, "fare code over an older reviewed SOURCE release")
    site = repo / "site"
    write_json(site / fare_scope.DATA, build_averages(private(observation())))
    proof = dict(
        schema_version=fare_scope.SCHEMA, baseline_commit=source_commit,
        baseline_manifest_sha256=fare_scope.sha((site / manifest.MANIFEST_NAME).read_bytes()),
        aggregate_sha256=fare_scope.sha((site / fare_scope.DATA).read_bytes()), private_input_sha256="0" * 64,
        policy_sha256=fare_scope.sha((repo / fare_scope.POLICY).read_bytes()),
        public_contract_sha256=fare_scope.sha((repo / "contracts/web/fare-averages.schema.json").read_bytes()),
    )
    write_json(site / fare_scope.PROOF, proof)
    manifest.write_manifest(site, manifest.build_manifest(
        site, before["analysis_manifest"], code_commit=code,
        contracts={**before["contracts"], "fare-averages.schema.json": proof["public_contract_sha256"]},
    ))
    commit(repo, "published Fare fixture")
    return repo, source_spec


def test_real_fare_consumers_authenticate_then_unwrap_original_official_map(official_fare):
    repo, source_spec = official_fare
    never_financial = lambda *_: pytest.fail("financial fallback")
    verify_current_publication(repo / "site", repo, never_financial)
    with official_map_baseline(repo / "site", repo, never_financial) as comparison:
        raw = (comparison / manifest.MANIFEST_NAME).read_bytes()
        assert fare_scope.sha(raw) == source_spec["baseline_manifest_sha256"]
        assert not (comparison / fare_scope.PROOF).exists()
        assert not (comparison / "data/v1/official-routes.json").exists()
        expected = subprocess.check_output([
            "git", "show", f"{source_spec['baseline_commit']}:site/data/v1/executive.json",
        ], cwd=repo)
        assert (comparison / "data/v1/executive.json").read_bytes() == expected
        financial = json.loads(expected)
        spec = {"executive_sha256": sha(encoded(financial)), "executive_bytes": len(encoded(financial))}
        assert preserved_financial_projection(comparison, repo, spec) == financial


def test_snapshot_and_editorial_comparison_use_the_real_fare_chain(official_fare, monkeypatch):
    from types import SimpleNamespace
    from tests import test_editorial_site_parity as editorial
    from tests import test_site_parity as snapshot

    repo, source_spec = official_fare
    monkeypatch.setattr(snapshot, "SITE_DIR", repo / "site")
    monkeypatch.setattr(editorial, "ROOT", repo)
    monkeypatch.setattr(editorial, "SITE", repo / "site")
    request = SimpleNamespace(
        config=SimpleNamespace(getoption=lambda _: None),
        getfixturevalue=lambda _: lambda *_: pytest.fail("financial fallback"),
    )
    snapshot._require_site(request)
    with snapshot._comparison_site() as comparison:
        assert fare_scope.sha((comparison / manifest.MANIFEST_NAME).read_bytes()) == source_spec["baseline_manifest_sha256"]
        financial = json.loads((comparison / "data/v1/executive.json").read_bytes())
    assert snapshot.published_executive.__wrapped__(financial) == financial
    context = editorial.editorial_comparison_site.__wrapped__(request)
    comparison = next(context)
    try:
        assert fare_scope.sha((comparison / manifest.MANIFEST_NAME).read_bytes()) == source_spec["baseline_manifest_sha256"]
    finally:
        context.close()


def _snapshot_fixture(official_fare, monkeypatch):
    from types import SimpleNamespace
    from tests import test_site_parity as snapshot

    repo, spec = official_fare
    subprocess.run(["git", "update-ref", "refs/remotes/origin/master", "HEAD"], cwd=repo, check=True)
    monkeypatch.setattr(snapshot, "SITE_DIR", repo / "site")
    monkeypatch.setattr(snapshot, "DATA_DIR", repo / "site/data/v1")
    snapshot._replay_published_cohorts.cache_clear()
    request = SimpleNamespace(config=SimpleNamespace(getoption=lambda name: name == "--require-local-data"))
    return snapshot, repo, spec, request


def test_snapshot_replay_reaches_original_approval_guard_after_intermediate_config(official_fare, monkeypatch):
    snapshot, _, _, _ = _snapshot_fixture(official_fare, monkeypatch)
    # This synthetic public fixture deliberately has no private approval
    # provenance. Reaching the real refusal proves we opened the historical
    # config without inventing an approval or stubbing any verifier.
    with pytest.raises(ValueError, match="Missing committed approval provenance: config/publish/preserved-analysis.json"):
        snapshot._replay_published_cohorts()


def test_complete_snapshot_after_fare_committed_at_head_and_protected_ref(official_fare, monkeypatch, tmp_path):
    from src.web_export.flights import recombine_flights

    snapshot, repo, _, request = _snapshot_fixture(official_fare, monkeypatch)
    financial = json.loads((repo / "site/data/v1/executive.json").read_bytes())
    payload = json.loads((repo / "site/data/v1/analysis/2026Q2.json").read_bytes())
    entry = manifest.load_manifest(repo / "site")["analysis_manifest"][0]
    readings = []

    def fixture_source_reading(selected):
        # Only private source data reading is deterministic here. Fare/SOURCE,
        # branch selection, Git, exports and the full Snapshot test stay real.
        assert selected == entry
        readings.append(selected)
        return payload

    monkeypatch.setattr(snapshot, "_export_approved_entry", fixture_source_reading)
    published = snapshot.published_executive.__wrapped__(financial)
    snapshot.test_site_flights_and_executive_data_match_a_fresh_export(
        request, tmp_path, recombine_flights(repo / "site/data/v1"), published,
    )
    assert readings == [entry]
    assert (tmp_path / "data/v1/flights/quarters.json").is_file()


def test_snapshot_opens_exact_config_of_authenticated_intermediate_edition(official_fare, monkeypatch):
    from tests._site_publication_parity import _published_approval_config_view

    snapshot, repo, spec, _ = _snapshot_fixture(official_fare, monkeypatch)
    with snapshot._comparison_edition() as (comparison, commit):
        raw = (comparison / manifest.MANIFEST_NAME).read_bytes()
        assert commit == spec["baseline_commit"]
        for ref in ("HEAD", "origin/master"):
            current = subprocess.check_output(["git", "show", f"{ref}:site/publication_manifest.json"], cwd=repo)
            assert current != raw and any(p["path"] == fare_scope.PROOF for p in json.loads(current)["files"])
        with _published_approval_config_view(repo, raw, verified_commit=commit) as (view, trusted):
            assert trusted == commit
            assert subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=view).decode().strip() == commit
            expected = subprocess.check_output(["git", "ls-tree", "-r", "--name-only", commit, "--", "config/publish"], cwd=repo).decode().splitlines()
            assert sorted(p.relative_to(view).as_posix() for p in (view / "config/publish").rglob("*") if p.is_file()) == expected
            for name in expected:
                assert (view / name).read_bytes() == subprocess.check_output(["git", "show", f"{commit}:{name}"], cwd=repo)


@pytest.mark.parametrize("mutation", ["raw", "wrong_edition", "malformed_commit", "nonancestor"])
def test_historical_config_refuses_nominated_commit_or_manifest_changes(official_fare, monkeypatch, mutation):
    from tests._site_publication_parity import _published_approval_config_view

    snapshot, repo, _, _ = _snapshot_fixture(official_fare, monkeypatch)
    with snapshot._comparison_edition() as (comparison, commit):
        raw = (comparison / manifest.MANIFEST_NAME).read_bytes()
        if mutation == "raw":
            raw += b" "
        elif mutation == "wrong_edition":
            commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo).decode().strip()
        elif mutation == "malformed_commit":
            commit = "HEAD"
        else:
            tree = subprocess.check_output(["git", "rev-parse", f"{commit}^{{tree}}"], cwd=repo).decode().strip()
            commit = subprocess.check_output(["git", "commit-tree", tree, "-m", "unrelated identical manifest"], cwd=repo).decode().strip()
            assert subprocess.check_output(["git", "show", f"{commit}:site/publication_manifest.json"], cwd=repo) == raw
        with pytest.raises(ValueError, match="Authenticated publication"):
            with _published_approval_config_view(repo, raw, verified_commit=commit):
                pytest.fail("Unverified historical configuration was accepted")


@pytest.mark.parametrize("mutation", ["financial_bytes", "approval", "source_authority", "fare_policy", "aggregate"])
def test_fare_parity_rejects_changed_data_or_authority_before_yield(official_fare, tmp_path, mutation):
    repo, _ = official_fare
    site = tmp_path / "site"
    shutil.copytree(repo / "site", site)
    policy = repo / fare_scope.POLICY
    original_policy = policy.read_bytes()
    try:
        if mutation == "fare_policy":
            policy.write_bytes(original_policy + b" ")
        elif mutation == "approval":
            value = manifest.load_manifest(site)
            value["analysis_manifest"][0]["content_hash"] = "0" * 64
            manifest.write_manifest(site, value)
        else:
            name = {"financial_bytes": "data/v1/executive.json", "source_authority": source_data_scope.PROOF,
                    "aggregate": fare_scope.DATA}[mutation]
            (site / name).write_bytes((site / name).read_bytes() + b" ")
            value = manifest.load_manifest(site)
            manifest.write_manifest(site, manifest.build_manifest(
                site, value["analysis_manifest"], contracts=value["contracts"], code_commit=value["code_commit"],
            ))
        with pytest.raises(AssertionError):
            with official_map_baseline(site, repo, lambda *_: pytest.fail("financial fallback")):
                pytest.fail("Invalid publication was yielded")
    finally:
        policy.write_bytes(original_policy)
