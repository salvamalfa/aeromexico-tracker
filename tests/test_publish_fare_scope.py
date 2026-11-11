"""Fare-only release must not bless changes to a verified inherited public snapshot."""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from src.fare_quotes.aggregate import build_averages
from src.publish import fare_scope, manifest
from src.web_export.writer import write_json
from tests.test_fare_averages import observation, private


def git(repo, *args):
    return subprocess.check_output(["git", *args], cwd=repo, text=True).strip()


@pytest.fixture
def fare_release(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init", "-q")
    git(repo, "config", "user.name", "Fare release test")
    git(repo, "config", "user.email", "fixture@example.invalid")
    git(repo, "config", "core.autocrlf", "false")
    source = Path(__file__).parent / "fixtures/site/valid"
    shutil.copytree(source, repo / "site")
    git(repo, "add", "site")
    git(repo, "commit", "-qm", "verified baseline fixture")
    baseline_commit = git(repo, "rev-parse", "HEAD")
    git(repo, "commit", "--allow-empty", "-qm", "fare exporter fixture")
    code = git(repo, "rev-parse", "HEAD")
    for name in [fare_scope.POLICY, "contracts/web/fare-averages.schema.json"]:
        target = repo / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(manifest.PATHS.root / name, target)
    candidate = tmp_path / "candidate"
    shutil.copytree(repo / "site", candidate)
    averages = build_averages(private(observation()))
    write_json(candidate / fare_scope.DATA, averages)
    before = manifest.load_manifest(repo / "site")
    proof = dict(
        schema_version=fare_scope.SCHEMA,
        baseline_commit=baseline_commit,
        baseline_manifest_sha256=fare_scope.sha((repo / "site/publication_manifest.json").read_bytes()),
        aggregate_sha256=fare_scope.sha((candidate / fare_scope.DATA).read_bytes()),
        private_input_sha256="0" * 64,
        policy_sha256=fare_scope.sha((repo / fare_scope.POLICY).read_bytes()),
        public_contract_sha256=fare_scope.sha(
            (repo / "contracts/web/fare-averages.schema.json").read_bytes()
        ),
    )
    write_json(candidate / fare_scope.PROOF, proof)
    contracts = {**before["contracts"], "fare-averages.schema.json": proof["public_contract_sha256"]}
    manifest.write_manifest(
        candidate,
        manifest.build_manifest(
            candidate, before["analysis_manifest"], contracts=contracts, code_commit=code
        ),
    )
    return repo, candidate


def remint(candidate):
    current = manifest.load_manifest(candidate)
    manifest.write_manifest(
        candidate,
        manifest.build_manifest(
            candidate,
            current["analysis_manifest"],
            contracts=current["contracts"],
            code_commit=current["code_commit"],
        ),
    )


def test_additive_fare_release_replays_its_baseline(fare_release):
    repo, candidate = fare_release
    assert fare_scope.verify_fare_site(candidate, repo) == []


@pytest.mark.parametrize("mutation", ["financial_byte", "extra_data", "analysis_identity", "aggregate_byte"])
def test_self_consistent_new_manifest_cannot_hide_unauthorized_changes(fare_release, mutation):
    repo, candidate = fare_release
    if mutation == "financial_byte":
        path = candidate / "data/v1/executive.json"
        path.write_bytes(path.read_bytes() + b" ")
    elif mutation == "extra_data":
        write_json(candidate / "data/v1/not-authorized.json", {})
    elif mutation == "analysis_identity":
        value = manifest.load_manifest(candidate)
        value["analysis_manifest"][0]["content_hash"] = "0" * 64
        manifest.write_manifest(candidate, value)
    else:
        value = json.loads((candidate / fare_scope.DATA).read_bytes())
        value["groups"][0]["metrics"]["points"]["mean"] += 1
        write_json(candidate / fare_scope.DATA, value)
    remint(candidate)
    assert fare_scope.verify_fare_site(candidate, repo)
