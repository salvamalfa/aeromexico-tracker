"""Disposable, genuinely verified SOURCE release using unmodified project code."""

import json
import shutil
import subprocess
import sys
from pathlib import Path

from src.publish import editorial, fare_scope, manifest, source_data_scope
from src.publish.am_monthly_projection import public_outputs
from tests.test_am_monthly_projection import series


def git(repo, *args):
    return subprocess.check_output(["git", *args], cwd=repo, text=True).strip()


def commit(repo, message):
    git(repo, "add", ".")
    git(repo, "commit", "-qm", message)
    return git(repo, "rev-parse", "HEAD")


def create_source_release(repo):
    repo.mkdir()
    root = manifest.PATHS.root
    for name in ("src", "scripts", "contracts"):
        shutil.copytree(root / name, repo / name, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    shutil.copyfile(root / "uv.lock", repo / "uv.lock")
    shutil.copyfile(root / ".gitignore", repo / ".gitignore")
    shutil.copytree(Path(__file__).parent / "fixtures/site/valid", repo / "site")
    policy = repo / fare_scope.POLICY
    policy.parent.mkdir(parents=True)
    shutil.copyfile(root / fare_scope.POLICY, policy)
    git(repo, "init", "-q")
    git(repo, "config", "user.name", "Pinned SOURCE fixture")
    git(repo, "config", "user.email", "fixture@example.invalid")
    git(repo, "config", "core.autocrlf", "false")
    generic_code = commit(repo, "real generic verifier")
    site = repo / "site"
    previous = manifest.load_manifest(site)
    manifest.write_manifest(site, manifest.build_manifest(
        site, previous["analysis_manifest"], contracts=previous["contracts"], code_commit=generic_code,
    ))
    parent = commit(repo, "generic public fixture")
    previous = manifest.load_manifest(site)
    previous_raw = (site / manifest.MANIFEST_NAME).read_bytes()
    target = "data/v1/flights/quarters.json"
    outputs = public_outputs({target: (site / target).read_bytes()}, series())
    fingerprint = subprocess.check_output([
        sys.executable, "-B", "-c",
        "from src.analysis_agent.entity_adapter import code_version; print(code_version())",
    ], cwd=repo, text=True).strip()
    contract_name = "flights.schema.json"
    spec = {
        "schema_version": "source_data_release_v1", "product": "am_traffic_ir",
        "period_id": "2026M09", "baseline_commit": parent,
        "baseline_manifest_sha256": fare_scope.sha(previous_raw),
        "producer_code_version": fingerprint,
        "source_binding": {
            "product": "am_traffic_ir", "period": "2026M09", "receipt_id": "1" * 32,
            "candidate_as_of": "2026-10-28T00:00:00Z", "output_sha256": {"fixture": "2" * 64},
        },
        "projection": series(), "data_files": source_data_scope.pins(outputs),
        "frontend_files": editorial.frontend_entries(site),
        "contract_changes": {contract_name: fare_scope.sha((repo / "contracts/web" / contract_name).read_bytes())},
        "authorization_sha256": "3" * 64,
    }
    anchor = repo / source_data_scope.ANCHOR
    anchor.write_text(json.dumps(spec), encoding="utf-8")
    source_code = commit(repo, "reviewed SOURCE fixture producer")
    for name, raw in outputs.items():
        (site / name).write_bytes(raw)
    proof = {
        "schema_version": "source_data_publication_v1", "anchor_sha256": fare_scope.sha(anchor.read_bytes()),
        "remote_witness": {
            "baseline_commit": parent, "manifest_sha256": fare_scope.sha(previous_raw),
            "files_verified": len(previous["files"]), "origin": editorial.ORIGIN,
            "deployment_run": 1, "deployment_commit": parent,
        },
    }
    (site / source_data_scope.PROOF).write_text(json.dumps(proof), encoding="utf-8")
    manifest.write_manifest(site, manifest.build_manifest(
        site, previous["analysis_manifest"],
        contracts={**previous["contracts"], **spec["contract_changes"]}, code_commit=source_code,
    ))
    deployed = commit(repo, "verified SOURCE public fixture")
    return deployed
