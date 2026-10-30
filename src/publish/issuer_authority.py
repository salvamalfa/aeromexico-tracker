"""Private, exact data-exposure authority separate from thesis approval."""

from __future__ import annotations

import json
import os
from pathlib import Path

from src.config import PATHS

from .issuer_scope import EXECUTIVE, encoded, sha


def binding(package, spec):
    return {
        "entity_key": package["entity_key"],
        "period_id": package["period_id"],
        "package_id": package["package_id"],
        "evidence_fingerprint": package["evidence_fingerprint"],
        "source_binding": package["source_binding"],
        "baseline_commit": spec["baseline_commit"],
        "baseline_manifest_sha256": spec["baseline_manifest_sha256"],
        "producer_code_version": spec["producer_code_version"],
        "executive_sha256": spec["executive_sha256"],
        "executive_bytes": spec["executive_bytes"],
    }


def authority(package, spec, repo=PATHS.root):
    """Replay both private approvals without creating or changing either one."""
    directory = repo / "analysis_runs/dashboard_updates"
    path = directory / "authorizations" / (spec["authorization_sha256"] + ".json")
    if any(p.is_symlink() for p in [path, *path.parents]):
        raise ValueError("Data authorization cannot traverse a symlink")
    raw = path.read_bytes()
    if sha(raw) != spec["authorization_sha256"]:
        raise ValueError("Data authorization changed")
    auth = json.loads(raw)
    expected = binding(package, spec)
    consent = auth.get("owner_consent", {})
    if (
        auth.get("schema_version") != "issuer_data_authorization_v1"
        or auth.get("state") != "authorized"
        or auth.get("binding") != expected
        or not all(
            isinstance(consent.get(k), str) and consent[k]
            for k in ("source_reference", "instruction", "received_at")
        )
        or auth.get("constraints") != {"theses": False, "other_entities": False, "industry": False}
    ):
        raise ValueError("Data exposure lacks exact owner authority or has been revoked")
    review_sha = auth.get("source_audit_sha256", "")
    if len(review_sha) != 64 or any(c not in "0123456789abcdef" for c in review_sha):
        raise ValueError("Data authority must retain its exact independent source audit")
    review_path = directory / "audits" / (review_sha + ".json")
    if any(p.is_symlink() for p in [review_path, *review_path.parents]):
        raise ValueError("Data audit cannot be a symlink")
    review_raw = review_path.read_bytes()
    if sha(review_raw) != review_sha:
        raise ValueError("Data source audit changed")
    review = json.loads(review_raw)
    if (
        review.get("schema_version") != "issuer_data_audit_v1"
        or review.get("status") != "passed"
        or review.get("binding") != expected
        or review.get("unresolved_findings") != []
        or not isinstance(review.get("reviewer_reference"), str)
        or not review["reviewer_reference"]
    ):
        raise ValueError("Independent source audit does not cover this exact output")
    return auth, review


def verified_data(package, spec, baseline, repo=PATHS.root):
    from src.analysis_agent.issuer_quarter import verify

    from .issuer_projection import executive_projection

    verify(package)
    for key in ("entity_key", "period_id", "package_id", "evidence_fingerprint", "source_binding"):
        if package[key] != spec[key]:
            raise ValueError("Issuer data handoff differs from its verified source version")
    executive = executive_projection(json.loads((baseline / EXECUTIVE).read_bytes()), package)
    raw = encoded(executive)
    if sha(raw) != spec["executive_sha256"] or len(raw) != spec["executive_bytes"]:
        raise ValueError("Issuer data projection differs from its reviewed output")
    approvals = authority(package, spec, repo)
    return raw, approvals


def input_snapshot(record_paths, spec, package_path=None, repo=PATHS.root):
    """Fingerprint only selected source closures after/before slow verification.

    This is an integrity guard, not a substitute for any source or approval replay.
    Unrelated candidate/analysis workspaces do not become publication dependencies.
    """
    files, packages = set(), []

    def add(path):
        path = Path(path).absolute()
        if (
            ".." in path.parts
            or not path.is_relative_to(repo.absolute())
            or any(p.is_symlink() for p in [path, *path.parents])
        ):
            raise ValueError("Issuer snapshot input escapes the checkout or traverses a symlink")
        if not path.is_file():
            raise ValueError("Issuer snapshot input is missing")
        files.add(path)

    selected = [Path(p) for p in record_paths]
    previous = spec.get("previous_entry")
    if previous:
        path = repo / "analysis_runs/drafts"
        if "entity_key" in previous:
            path /= previous["entity_key"]
        selected.append(path / previous["period_id"] / (previous["version"] + ".json"))
    for path in selected:
        add(path)
        draft = json.loads(path.read_bytes())["draft"]
        evidence = repo / "analysis_runs/evidence" / (draft["package_id"] + ".json")
        add(evidence)
        add(repo / "analysis_runs/quantitative" / (draft["calculation_fingerprint"] + ".json"))
        packages.append(json.loads(evidence.read_bytes()))
    if package_path is not None:
        add(package_path)
        packages.append(json.loads(Path(package_path).read_bytes()))
    for package in packages:
        if package.get("source_profile") == "issuer_quarter_v1":
            workspace = repo / package["workspace"]
            if ".." in workspace.parts or not workspace.is_relative_to(repo / "tmp/source-updates"):
                raise ValueError("Issuer snapshot workspace is not a private source candidate")
            for path in workspace.rglob("*"):
                if path.is_symlink():
                    raise ValueError("Issuer source candidate contains a symlink")
                if path.is_file():
                    add(path)
        else:
            for source in package["sources"]:
                for artifact in [source, *source.get("proofs", [])]:
                    path = repo / "data/bronze" / artifact["source_file"]
                    add(path)
                    sidecar = Path(str(path) + ".meta.json")
                    if sidecar.exists() or sidecar.is_symlink():
                        add(sidecar)
            if package.get("capsule_fingerprint"):
                capsule = repo / "analysis_runs/entity_review_bundles" / package["capsule_fingerprint"]
                for name in package["capsule_files"]:
                    add(capsule / name)
    for path in (repo / "analysis_runs/lifecycle").rglob("*.json"):
        if "publications" not in path.relative_to(repo / "analysis_runs/lifecycle").parts:
            add(path)
    if spec.get("authorization_sha256"):
        path = (
            repo / "analysis_runs/dashboard_updates/authorizations" / (spec["authorization_sha256"] + ".json")
        )
        add(path)
        audit_sha = json.loads(path.read_bytes())["source_audit_sha256"]
        add(repo / "analysis_runs/dashboard_updates/audits" / (audit_sha + ".json"))
    return {
        str(p.relative_to(repo)): {
            "sha256": sha(p.read_bytes()),
            "library_identity": {
                key: sha(os.getxattr(p, key))
                for key in getattr(os, "listxattr", lambda _: ())(p)
                if key.startswith("user.library-")
            },
        }
        for p in sorted(files)
    }
