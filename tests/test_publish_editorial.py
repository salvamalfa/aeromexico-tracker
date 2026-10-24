"""Adversarial scope tests use only disposable Git and in-memory HTTP/CI answers."""

from __future__ import annotations

import copy
import hashlib
import json
import shutil
import subprocess

import pytest

from src.publish import editorial as e


def encoded(value):
    return json.dumps(value, sort_keys=True).encode()


def put(path, raw):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)


def git(root, *args):
    return subprocess.check_output(["git", *args], cwd=root).decode().strip()


@pytest.fixture
def release(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init", "-q")
    git(repo, "config", "user.name", "Fixture")
    git(repo, "config", "user.email", "fixture@example.invalid")
    historic = {
        "index.html": b"old index",
        "assets/old.js": b"old js",
        "data/v1/news.json": b'{"news":[]}',
        "data/v1/business_metrics.json": b'{"metrics":[]}',
        "data/v1/business_metrics.approval.json": b'{"receipt":"frozen"}',
        "data/v1/analysis/2026Q2.json": b'{"version":"historic"}',
        "data/v1/executive.json": b'{"financial_period":"2026Q2"}',
    }
    files = [
        {"path": p, "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}
        for p, raw in historic.items()
    ]
    old = {
        "files": files,
        "contracts": {"privacy.yaml": "a" * 64},
        "analysis_manifest": [{"period_id": "2026Q2", "version": "historic"}],
    }
    for name, raw in historic.items():
        put(repo / "site" / name, raw)
    baseline_raw = encoded(old)
    put(repo / "site/publication_manifest.json", baseline_raw)
    git(repo, "add", ".")
    git(repo, "commit", "-qm", "baseline")
    commit = git(repo, "rev-parse", "HEAD")
    newraw = b'{"period_id":"2026Q3","version":"new"}'
    contract = (e.PATHS.root / "contracts/web" / e.manifests.EDITORIAL_ANALYSIS_CONTRACT).read_bytes()
    contract_sha = hashlib.sha256(contract).hexdigest()
    put(repo / "contracts/web" / e.manifests.EDITORIAL_ANALYSIS_CONTRACT, contract)
    spec = {
        "schema_version": "editorial_release_v1",
        "baseline_commit": commit,
        "baseline_manifest_sha256": hashlib.sha256(baseline_raw).hexdigest(),
        "frontend_files": [
            {
                "path": "index.html",
                "bytes": len(b"new index"),
                "sha256": hashlib.sha256(b"new index").hexdigest(),
            }
        ],
        "analysis_entry": {"period_id": "2026Q3", "version": "new"},
        "analysis_contract_sha256": contract_sha,
        "analysis_sha256": hashlib.sha256(newraw).hexdigest(),
        "analysis_bytes": len(newraw),
    }
    put(repo / e.ANCHOR, encoded(spec))
    git(repo, "add", ".")
    git(repo, "commit", "-qm", "reviewed anchor")
    site = tmp_path / "candidate"
    for name, raw in historic.items():
        put(site / name, raw)
    put(site / "index.html", b"new index")
    put(site / e.ANALYSIS, newraw)
    witness = {
        "baseline_commit": commit,
        "manifest_sha256": spec["baseline_manifest_sha256"],
        "files_verified": len(files),
        "deployment_run": 17,
        "deployment_commit": commit,
        "origin": e.ORIGIN,
        "verified_at": "2026-10-24T00:00:00+00:00",
    }
    proof = {
        "schema_version": "editorial_publication_v1",
        "anchor_sha256": hashlib.sha256((repo / e.ANCHOR).read_bytes()).hexdigest(),
        "baseline_commit": commit,
        "baseline_manifest_sha256": spec["baseline_manifest_sha256"],
        "remote_witness": witness,
        "analysis_entry": spec["analysis_entry"],
    }
    put(site / e.PROOF, encoded(proof))
    current = copy.deepcopy(old)
    current["contracts"][e.manifests.EDITORIAL_ANALYSIS_CONTRACT] = contract_sha
    current["analysis_manifest"].append(spec["analysis_entry"])
    put(site / "publication_manifest.json", encoded(current))
    return {
        "repo": repo,
        "site": site,
        "spec": spec,
        "old": old,
        "raw": baseline_raw,
        "historic": historic,
        "proof": proof,
        "witness": witness,
    }


def resign_site(site):
    """Attacker can regenerate their own inventory; this must grant no authority."""
    p = site / "publication_manifest.json"
    m = json.loads(p.read_bytes())
    m["files"] = [
        {
            "path": x.relative_to(site).as_posix(),
            "bytes": len(x.read_bytes()),
            "sha256": hashlib.sha256(x.read_bytes()).hexdigest(),
        }
        for x in site.rglob("*")
        if x.is_file() and x.name != "publication_manifest.json"
    ]
    put(p, encoded(m))


def test_exact_frozen_bytes_are_eligible(release):
    r = release
    allowed = e.preserved_files(r["site"], r["repo"], e.anchor(r["repo"]))
    assert allowed == frozenset(set(r["historic"]) - {"index.html"})


@pytest.mark.parametrize(
    "name",
    [
        "data/v1/news.json",
        "data/v1/business_metrics.json",
        "data/v1/business_metrics.approval.json",
        "data/v1/analysis/2026Q2.json",
        "data/v1/executive.json",
        "assets/old.js",
    ],
)
def test_selfhashed_manifest_cannot_authorize_historical_mutation(release, name):
    r = release
    put(r["site"] / name, b'{"tampered":true}')
    resign_site(r["site"])
    with pytest.raises(ValueError, match="changed preserved file"):
        e.preserved_files(r["site"], r["repo"], r["spec"])


def test_contract_mutation_is_rejected_even_with_new_manifest(release):
    r = release
    p = r["site"] / "publication_manifest.json"
    m = json.loads(p.read_bytes())
    m["contracts"]["privacy.yaml"] = "b" * 64
    put(p, encoded(m))
    with pytest.raises(ValueError, match="changed contracts"):
        e.preserved_files(r["site"], r["repo"], r["spec"])


@pytest.mark.parametrize(
    "name",
    ["data/v1/monthly.json", "data/v1/reading-periods.json", "unexpected.txt", "assets/executable.html"],
)
def test_out_of_scope_additions_rejected(release, name):
    r = release
    put(r["site"] / name, b"new")
    resign_site(r["site"])
    with pytest.raises(ValueError, match="out-of-scope"):
        e.preserved_files(r["site"], r["repo"], r["spec"])


def test_new_analysis_payload_pin_cannot_be_self_resigned(release):
    r = release
    put(r["site"] / e.ANALYSIS, b'{"version":"forged"}')
    resign_site(r["site"])
    with pytest.raises(ValueError, match="approved pin"):
        e.preserved_files(r["site"], r["repo"], r["spec"])


def test_uncommitted_anchor_is_not_authority(release):
    r = release
    s = copy.deepcopy(r["spec"])
    s["analysis_sha256"] = "f" * 64
    put(r["repo"] / e.ANCHOR, encoded(s))
    with pytest.raises(ValueError, match="not committed"):
        e.anchor(r["repo"])


@pytest.mark.parametrize(
    "field,value",
    [
        ("anchor_sha256", "f" * 64),
        ("baseline_commit", "f" * 40),
        ("analysis_entry", {"period_id": "2026Q3", "version": "forged"}),
    ],
)
def test_forged_proof_identity_rejected(release, field, value):
    r = release
    p = copy.deepcopy(r["proof"])
    p[field] = value
    put(r["site"] / e.PROOF, encoded(p))
    with pytest.raises(ValueError, match="reviewed anchor"):
        e.preserved_files(r["site"], r["repo"], r["spec"])


def remote_fixture(monkeypatch, r, *, remote=None, runs=None, served=None):
    original = e._git

    def fake_git(repo, *args):
        if args[0] == "ls-remote":
            return ((remote or r["spec"]["baseline_commit"]) + "\trefs/heads/master\n").encode()
        return original(repo, *args)

    monkeypatch.setattr(e, "_git", fake_git)
    original_output = subprocess.check_output

    def output(args, **kwargs):
        if args[0] == "gh":
            return encoded(
                runs
                if runs is not None
                else [
                    {
                        "databaseId": 17,
                        "headSha": r["spec"]["baseline_commit"],
                        "conclusion": "success",
                        "url": "https://example.invalid/run/17",
                    }
                ]
            )
        return original_output(args, **kwargs)

    monkeypatch.setattr(e.subprocess, "check_output", output)
    responses = {"publication_manifest.json": r["raw"], **r["historic"]}
    responses.update(served or {})
    monkeypatch.setattr(e, "_get", lambda name: responses[name])


def test_remote_success_requires_every_served_byte(monkeypatch, release):
    remote_fixture(monkeypatch, release)
    assert e.witness_remote(release["repo"], release["spec"])["files_verified"] == len(release["historic"])


def test_remote_master_divergence_rejected(monkeypatch, release):
    remote_fixture(monkeypatch, release, remote="f" * 40)
    with pytest.raises(ValueError, match="Remote master diverged"):
        e.witness_remote(release["repo"], release["spec"])


@pytest.mark.parametrize("name", ["publication_manifest.json", "data/v1/news.json", "assets/old.js"])
def test_served_mismatch_rejected(monkeypatch, release, name):
    remote_fixture(monkeypatch, release, served={name: b"tampered"})
    with pytest.raises(ValueError, match="Served"):
        e.witness_remote(release["repo"], release["spec"])


def test_successful_run_with_wrong_site_tree_rejected(monkeypatch, release):
    r = release
    put(r["repo"] / "site/index.html", b"other deployment")
    git(r["repo"], "add", ".")
    git(r["repo"], "commit", "-qm", "other tree")
    wrong = git(r["repo"], "rev-parse", "HEAD")
    remote_fixture(
        monkeypatch,
        r,
        runs=[
            {
                "databaseId": 19,
                "headSha": wrong,
                "conclusion": "success",
                "url": "https://example.invalid/run/19",
            }
        ],
    )
    with pytest.raises(ValueError, match="No successful Pages"):
        e.witness_remote(r["repo"], r["spec"])


def test_removed_historical_file_rejected(release):
    r = release
    (r["site"] / "data/v1/news.json").unlink()
    resign_site(r["site"])
    with pytest.raises(ValueError):
        e.preserved_files(r["site"], r["repo"], r["spec"])


def test_symlink_rejected(release):
    r = release
    (r["site"] / "assets/link.js").symlink_to(r["site"] / "assets/old.js")
    with pytest.raises(ValueError, match="symlinks"):
        e.preserved_files(r["site"], r["repo"], r["spec"])


def test_unreviewed_javascript_cannot_be_added_by_resigning_manifest(release):
    r = release
    put(r["site"] / "assets/injected.js", b'alert("unreviewed")')
    resign_site(r["site"])
    with pytest.raises(ValueError):
        e.preserved_files(r["site"], r["repo"], r["spec"])


def test_frontend_index_cannot_differ_from_reviewed_build_pin(release):
    r = release
    put(r["site"] / "index.html", b"forged new index")
    resign_site(r["site"])
    with pytest.raises(ValueError):
        e.preserved_files(r["site"], r["repo"], r["spec"])


@pytest.mark.parametrize(
    "failure",
    [
        "revocation",
        "remote_change",
        "baseline_change",
        "source_dirty",
        "head_change",
        "anchor_change",
        "during_approval_baseline",
        "during_approval_head",
        "during_approval_remote",
        "during_candidate_baseline",
        "during_candidate_head",
        "during_candidate_remote",
    ],
)
def test_publish_rechecks_before_swap_without_writing_output(monkeypatch, release, failure):
    """Exercise publication control flow; lifecycle rejection itself stays authoritative."""
    from types import SimpleNamespace

    from src.publish import gate

    r = release
    repo = r["repo"]
    dist = repo / "build-output"
    dist.mkdir()
    put(dist / "index.html", b"new index")
    newraw = (r["site"] / e.ANALYSIS).read_bytes()
    payload = json.loads(newraw)
    # Serializer in gate uses compact UTF8 exactly, as the reviewed fixture pin.
    spec = copy.deepcopy(r["spec"])
    spec["analysis_bytes"] = len(json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode())
    spec["analysis_sha256"] = hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode()
    ).hexdigest()
    monkeypatch.setattr(e, "PATHS", SimpleNamespace(root=repo))
    anchor_reads = []

    def read_anchor(root):
        anchor_reads.append(True)
        if failure == "anchor_change" and len(anchor_reads) > 1:
            return {**spec, "analysis_bytes": spec["analysis_bytes"] + 1}
        return spec

    monkeypatch.setattr(e, "anchor", read_anchor)
    witness_calls = []

    def witness(*args):
        witness_calls.append(True)
        if failure == "baseline_change" and len(witness_calls) == 2:
            put(repo / "site/data/v1/news.json", b"concurrent local edit")
        return r["witness"]

    monkeypatch.setattr(e, "witness_remote", witness)
    source_checks = []

    def check_source():
        source_checks.append(True)
        if failure == "source_dirty" and len(source_checks) > 1:
            raise RuntimeError("Build inputs changed during publication")

    monkeypatch.setattr(gate.manifest_mod, "refuse_if_build_inputs_dirty", check_source)
    monkeypatch.setattr(gate, "_trusted_site_commit", lambda root: spec["baseline_commit"])
    if failure in ("baseline_change", "during_approval_baseline", "during_candidate_baseline"):
        git(repo, "update-ref", "refs/remotes/origin/master", spec["baseline_commit"])
        original_baseline = gate.require_trusted_site_baseline

        def real_baseline(*args, **kwargs):
            return original_baseline(*args, root=repo, **kwargs)

        monkeypatch.setattr(gate, "require_trusted_site_baseline", real_baseline)
    else:
        monkeypatch.setattr(gate, "require_trusted_site_baseline", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        gate, "load_records", lambda paths: [{"draft": {"source_profile": "quarterly_release_v1"}}]
    )
    monkeypatch.setattr(gate.flow, "ROOT", repo / "isolated-ledger")
    monkeypatch.setattr(gate, "WEB_DATA_V1", repo / "build-data")

    def build():
        shutil.copytree(repo / "build-data", dist / "data/v1")
        return dist

    monkeypatch.setattr(gate, "build_web", build)
    monkeypatch.setattr(gate, "_analysis_payload", lambda *args: payload)
    monkeypatch.setattr(gate, "_analysis_manifest_entry", lambda authorized: spec["analysis_entry"])
    calls = []
    changed_during_approval = []

    def recheck(*args):
        calls.append("verify")
        if len(calls) == 2 and failure == "revocation":
            raise ValueError("Exact approval revoked during build")
        if len(calls) == 2 and failure.startswith("during_approval_"):
            changed_during_approval.append(True)
            if failure == "during_approval_baseline":
                put(repo / "site/data/v1/news.json", b"edit during slow source verification")
        return [("record", "authorized", "package", "calculations")]

    monkeypatch.setattr(gate, "_verify_under_lock", recheck)
    original = e._git

    head_reads = []

    def git_read(root, *args):
        if args == ("rev-parse", "HEAD"):
            head_reads.append(True)
            if (failure == "head_change" and len(head_reads) > 1) or (
                failure in ("during_approval_head", "during_candidate_head") and changed_during_approval
            ):
                return b"f" * 40 + b"\n"
        if args[0] == "ls-remote":
            return (
                (
                    "f" * 40
                    if failure == "remote_change"
                    or (
                        failure in ("during_approval_remote", "during_candidate_remote")
                        and changed_during_approval
                    )
                    else spec["baseline_commit"]
                )
                + "\trefs/heads/master\n"
            ).encode()
        return original(root, *args)

    monkeypatch.setattr(e, "_git", git_read)
    if failure.startswith("during_"):
        # Structural scope has independent adversarial tests above. Here isolate
        # the last slow-source-check -> candidate validation -> swap ordering.
        def candidate_verification(*args):
            if failure.startswith("during_candidate_"):
                changed_during_approval.append(True)
                if failure == "during_candidate_baseline":
                    put(repo / "site/data/v1/news.json", b"edit during candidate verification")
            return []

        monkeypatch.setattr(e, "verify_editorial", candidate_verification)

        def assemble(*args, **kwargs):
            kwargs["validate_candidate"](r["site"])
            pytest.fail("Swap must not run after concurrent change")
    else:

        def assemble(*args, **kwargs):
            pytest.fail("Swap must not run after concurrent change")

    monkeypatch.setattr(gate, "assemble_site", assemble)
    monkeypatch.setattr(
        gate, "write_receipt", lambda *args: pytest.fail("No successful publication receipt allowed")
    )
    with pytest.raises(
        (ValueError, RuntimeError, gate.PublicationRefused),
        match="revoked|Remote master changed|uncommitted|Build inputs changed|code or anchor changed",
    ):
        e.publish_editorial([repo / "synthetic-record.json"], repo / "output")
    assert not (repo / "output").exists()
    assert not (repo / "isolated-ledger/writer.lock").exists()
    assert len(calls) == (2 if failure == "revocation" or failure.startswith("during_") else 1)
    if failure == "source_dirty":
        assert len(source_checks) == 2


def test_remote_master_changes_during_all_file_verification(monkeypatch, release):
    remote_fixture(monkeypatch, release)
    previous = e._git
    reads = []

    def moving_master(repo, *args):
        if args[0] == "ls-remote":
            reads.append(True)
            commit = release["spec"]["baseline_commit"] if len(reads) == 1 else "f" * 40
            return (commit + "\trefs/heads/master\n").encode()
        return previous(repo, *args)

    monkeypatch.setattr(e, "_git", moving_master)
    with pytest.raises(ValueError, match="changed during verification"):
        e.witness_remote(release["repo"], release["spec"])
    assert len(reads) == 2


@pytest.mark.parametrize("field,value", [("files_verified", 0), ("origin", "https://attacker.invalid/")])
def test_incomplete_or_wrong_origin_witness_rejected(release, field, value):
    r = release
    proof = copy.deepcopy(r["proof"])
    proof["remote_witness"][field] = value
    put(r["site"] / e.PROOF, encoded(proof))
    with pytest.raises(ValueError, match="Incomplete remote witness"):
        e.preserved_files(r["site"], r["repo"], r["spec"])


def test_baseline_manifest_digest_is_checked_against_git(release):
    spec = copy.deepcopy(release["spec"])
    spec["baseline_manifest_sha256"] = "f" * 64
    with pytest.raises(ValueError, match="Baseline manifest differs"):
        e.baseline(release["repo"], spec)


@pytest.mark.parametrize("mutation", ["missing", "wrong_hash", "extra_contract"])
def test_contract_addition_is_exactly_the_reviewed_one(release, mutation):
    r = release
    path = r["site"] / "publication_manifest.json"
    current = json.loads(path.read_bytes())
    name = e.manifests.EDITORIAL_ANALYSIS_CONTRACT
    if mutation == "missing":
        del current["contracts"][name]
    elif mutation == "wrong_hash":
        current["contracts"][name] = "f" * 64
    else:
        current["contracts"]["unreviewed.schema.json"] = "f" * 64
    put(path, encoded(current))
    with pytest.raises(ValueError, match="changed contracts"):
        e.preserved_files(r["site"], r["repo"], r["spec"])


def test_anchor_rejects_unreviewed_editorial_contract_bytes(release):
    r = release
    put(r["repo"] / "contracts/web" / e.manifests.EDITORIAL_ANALYSIS_CONTRACT, b'{"type":"object"}')
    with pytest.raises(ValueError, match="contract"):
        e.anchor(r["repo"])


def test_frontend_graph_reads_utf8_independently_of_platform_default(tmp_path, monkeypatch):
    from pathlib import Path

    put(tmp_path / "index.html", '<script src="assets/app.js"></script>'.encode())
    put(tmp_path / "assets/app.js", 'const label = "✈"; import("./plot.js");'.encode("utf-8"))
    put(tmp_path / "assets/plot.js", 'const label = "";'.encode("utf-8"))
    original = Path.read_text
    reads = []

    def windows_default(path, encoding=None, errors=None, **kwargs):
        reads.append((path.name, encoding))
        return original(path, encoding=encoding or "cp1252", errors=errors, **kwargs)

    monkeypatch.setattr(Path, "read_text", windows_default)
    entries = e.frontend_entries(tmp_path)
    assert {item["path"] for item in entries} == {"index.html", "assets/app.js", "assets/plot.js"}
    assert len(reads) == 3
    assert all(encoding == "utf-8" for _, encoding in reads)
