"""Private, exact data-exposure authority separate from thesis approval."""

from __future__ import annotations

import json

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
