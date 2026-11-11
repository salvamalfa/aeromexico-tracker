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
