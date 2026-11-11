"""Fare-only release must not bless changes to a verified inherited public snapshot."""

import json
import shutil
import subprocess
from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.fare_quotes.aggregate import build_averages
from src.publish import fare_scope, manifest
from src.publish import presentation_release as presentation
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


def test_new_fare_release_delegates_to_intervening_data_profile(fare_release, monkeypatch):
    from scripts import check_pages_publication as routing

    repo, candidate = fare_release
    shutil.copytree(candidate, repo / "site", dirs_exist_ok=True)
    git(repo, "add", ".")
    git(repo, "commit", "-qm", "published fare fixture")
    fare_commit = git(repo, "rev-parse", "HEAD")
    git(repo, "commit", "--allow-empty", "-qm", "subsequent data producer")
    source_code = git(repo, "rev-parse", "HEAD")
    # Model a subsequently approved source edition. Its strong producer is
    # stubbed below; the fare wrapper must delegate to it and preserve its bytes.
    path = repo / "site/data/v1/executive.json"
    path.write_bytes(path.read_bytes() + b" ")
    write_json(repo / "site/issuer-publication.json", {"remote_witness": {"baseline_commit": fare_commit}})
    current = manifest.load_manifest(repo / "site")
    manifest.write_manifest(
        repo / "site",
        manifest.build_manifest(
            repo / "site",
            current["analysis_manifest"],
            contracts=current["contracts"],
            code_commit=source_code,
        ),
    )
    git(repo, "add", "site")
    git(repo, "commit", "-qm", "published subsequent data fixture")
    data_commit = git(repo, "rev-parse", "HEAD")
    git(repo, "commit", "--allow-empty", "-qm", "next fare producer")
    shutil.copytree(repo / "site", candidate, dirs_exist_ok=True)
    proof = json.loads((candidate / fare_scope.PROOF).read_bytes())
    proof.update(
        baseline_commit=data_commit,
        baseline_manifest_sha256=fare_scope.sha((repo / "site/publication_manifest.json").read_bytes()),
    )
    write_json(candidate / fare_scope.PROOF, proof)
    manifest.write_manifest(
        candidate,
        manifest.build_manifest(
            candidate,
            current["analysis_manifest"],
            contracts=current["contracts"],
            code_commit=git(repo, "rev-parse", "HEAD"),
        ),
    )
    assert routing.verifier_for(repo / "site", repo) == "src.publish.issuer_scope"
    checked = []

    def verify_intervening_source(site, root):
        checked.append(routing.verifier_for(site, root))
        return []  # The separate source producer's approval boundary.

    monkeypatch.setattr(routing, "verify_site", verify_intervening_source)
    assert fare_scope.verify_fare_site(candidate, repo) == []
    assert checked == ["src.publish.issuer_scope"]
    path = candidate / "data/v1/executive.json"
    path.write_bytes(path.read_bytes() + b" ")
    remint(candidate)
    assert fare_scope.verify_fare_site(candidate, repo)


def test_fare_presentation_marker_is_verified_not_treated_as_plain_ui(fare_release, monkeypatch):
    from src.publish import afac_history_scope

    repo, candidate = fare_release
    current = manifest.load_manifest(candidate)
    marker = dict(
        schema_version=presentation.PRESENTATION_RECEIPT_SCHEMA,
        baseline_commit="a" * 40,
        baseline_manifest_sha256="b" * 64,
        source_producer_commit="c" * 40,
        source_producer_code_version="d" * 64,
        frontend_commit=current["code_commit"],
    )
    index = candidate / "index.html"
    index.write_bytes(
        presentation.embed_presentation_receipt(b"<html><head></head><body>fare view</body></html>", marker)
    )
    remint(candidate)
    checked = []
    monkeypatch.setattr(afac_history_scope, "anchor", lambda *_: {"scope": {"pinned": True}})
    monkeypatch.setattr(
        presentation, "verify_presentation_producer_pin", lambda *args: checked.append(args[-1])
    )
    assert fare_scope.verify_fare_site(candidate, repo) == []
    assert checked == [marker]

    def changed_source(*_):
        raise ValueError("inherited producer changed")

    monkeypatch.setattr(presentation, "verify_presentation_producer_pin", changed_source)
    assert "inherited producer changed" in str(fare_scope.verify_fare_site(candidate, repo))


def test_fare_gate_embeds_inherited_producer_for_following_presentation(fare_release, tmp_path, monkeypatch):
    from src import publish as package
    from src.publish import fare_release as publisher

    repo, candidate = fare_release
    marker = dict(
        schema_version=presentation.PRESENTATION_RECEIPT_SCHEMA,
        baseline_commit="a" * 40,
        baseline_manifest_sha256="b" * 64,
        source_producer_commit="c" * 40,
        source_producer_code_version="d" * 64,
        frontend_commit="e" * 40,
    )
    source = tmp_path / "private.json"
    write_json(source, private(observation()))
    web_data = tmp_path / "web/public/data/v1"
    checks = {"replays": 0, "baseline": 0, "candidate": 0}

    def check_baseline(*_, **__):
        checks["baseline"] += 1

    def replay(*_):
        checks["replays"] += 1
        return {"afac": {"authorized": []}}

    def build(_):
        dist = tmp_path / "dist"
        shutil.copytree(web_data, dist / "data/v1")
        (dist / "assets").mkdir()
        (dist / "index.html").write_bytes(b"<html><head></head><body>new fares</body></html>")
        return dist

    def verify_candidate(site, _repo):
        assert presentation.read_presentation_receipt(site) == marker
        checks["candidate"] += 1
        return []

    def assemble(staged, *_args, contracts, validate_candidate):
        validate_candidate(staged)
        return {"contracts": contracts}

    fake_gate = SimpleNamespace(
        PATHS=SimpleNamespace(root=repo),
        flow=SimpleNamespace(ROOT=tmp_path / "ledger", writer=lambda *_: nullcontext()),
        _trusted_site_commit=lambda *_: "a" * 40,
        require_trusted_site_baseline=check_baseline,
        WEB_DATA_V1=web_data,
        WEB_DIR=tmp_path / "web",
        build_web=build,
        assemble_site=assemble,
        write_receipt=lambda *_args, **_kwargs: {},
    )
    monkeypatch.setattr(package, "gate", fake_gate, raising=False)
    monkeypatch.setattr(manifest, "refuse_if_build_inputs_dirty", lambda **_: None)
    monkeypatch.setattr(presentation, "_replay_release", replay)
    monkeypatch.setattr(presentation, "presentation_receipt", lambda *_: marker)
    monkeypatch.setattr(fare_scope, "verify_fare_site", verify_candidate)
    publisher.publish_fares_only([], source, repo / "site")
    assert checks == {"replays": 2, "baseline": 2, "candidate": 1}
