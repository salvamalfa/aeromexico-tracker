"""Physically verify an unchanged monthly view and recover an existing build."""

from __future__ import annotations

import json
from pathlib import Path

from src.config import PATHS

from . import editorial as transport
from . import manifest as manifests
from .approval_cohorts import verify_approval_cohorts
from .source_data_scope import ANCHOR, PROOF, pins, sha, verify_historical_baseline


def _records(repo, old):
    paths = []
    for entry in old["analysis_manifest"]:
        path = repo / "analysis_runs/drafts"
        if "entity_key" in entry:
            path /= entry["entity_key"]
        paths.append(path / entry["period_id"] / (entry["version"] + ".json"))
    return paths


def verify_no_visual_change(profile_path, binding, *, site=None):
    from . import gate
    from .source_data_update import physical_path, replay, snapshot

    repo = PATHS.root
    site = repo / "site" if site is None else Path(site)
    if site != repo / "site":
        raise ValueError("Selective no-change proof targets this checkout's tracked site")
    profile = physical_path(profile_path, repo)
    spec = {
        "baseline_commit": gate._trusted_site_commit(repo),
        "baseline_manifest_sha256": sha((site / manifests.MANIFEST_NAME).read_bytes()),
    }
    gate.require_trusted_site_baseline(site, trusted_commit=spec["baseline_commit"])
    old = verify_historical_baseline(repo, spec, site)
    records = _records(repo, old)
    request = {"product": binding["product"], "period": binding["period"], "authorization": None}
    with gate.flow.writer(gate.flow.ROOT):
        value, outputs = replay(request, profile, site, repo)
        if value["source_binding"] != binding or any(
            (site / name).read_bytes() != raw for name, raw in outputs.items()
        ):
            raise ValueError("Source does not reproduce the currently served monthly view")
        initial = snapshot(profile, request, profile, records, value, repo)
        cohorts = verify_approval_cohorts(records, repo, spec["baseline_commit"], old, gate.flow.ROOT)
        if replay(request, profile, site, repo) != (value, outputs):
            raise ValueError("Source changed during no-visual-change verification")
        if snapshot(profile, request, profile, records, value, repo) != initial:
            raise ValueError("Source or approvals changed during no-visual-change verification")
        gate.require_trusted_site_baseline(site, trusted_commit=spec["baseline_commit"])
        if verify_approval_cohorts(records, repo, spec["baseline_commit"], old, gate.flow.ROOT) != cohorts:
            raise ValueError("An approval changed during no-visual-change verification")
    return {
        "status": "no_visual_change",
        "source_binding": binding,
        "source_profile": {"path": str(profile), "sha256": sha(profile.read_bytes())},
        **spec,
        "data_files": pins(outputs),
    }


def already_built(request_path, request, profile, records, spec, repo):
    """Return verified existing build metadata without another swap or receipt."""
    from src.analysis_agent.entity_adapter import code_version

    from . import gate
    from .source_data_scope import preserved_files
    from .source_data_update import authority, replay, snapshot
    from .verify import _verify_site

    site = repo / "site"
    if not (site / PROOF).is_file():
        return None
    proof = json.loads((site / PROOF).read_bytes())
    if proof.get("anchor_sha256") != sha((repo / ANCHOR).read_bytes()):
        return None
    raw = (site / manifests.MANIFEST_NAME).read_bytes()
    current_ref = gate._trusted_site_commit(repo)
    if (
        current_ref != spec["baseline_commit"]
        and transport._git(repo, "show", f"{current_ref}:site/{manifests.MANIFEST_NAME}") != raw
    ):
        raise ValueError("Existing source build is superseded by another remote publication; reconcile it")
    if code_version() != spec["producer_code_version"]:
        raise ValueError("Existing source build uses another producer")
    old = verify_historical_baseline(repo, spec, site)
    with gate.flow.writer(gate.flow.ROOT):
        authority(request, spec, repo)
        value, outputs = replay(request, profile, site, repo)
        if (
            value["source_binding"] != spec["source_binding"]
            or value.get("additional_sources", []) != spec.get("additional_sources", [])
            or value["projection"] != spec["projection"]
            or pins(outputs) != spec["data_files"]
        ):
            raise ValueError("Existing build consumed another exact source version")
        initial = snapshot(request_path, request, profile, records, value, repo)
        verify_approval_cohorts(records, repo, spec["baseline_commit"], old, gate.flow.ROOT)
        problems = _verify_site(site, preserved_approval_files=preserved_files(site, repo, spec))
        if problems:
            raise ValueError(f"Existing source build is invalid: {problems[:3]}")
        if (
            replay(request, profile, site, repo) != (value, outputs)
            or snapshot(request_path, request, profile, records, value, repo) != initial
        ):
            raise ValueError("Existing source build inputs changed during recovery")
        authority(request, spec, repo)
        if (site / manifests.MANIFEST_NAME).read_bytes() != raw:
            raise ValueError("Existing source manifest changed during recovery")
    return {
        "status": "already_built_verified",
        "manifest": json.loads(raw),
        "manifest_sha256": sha(raw),
        "new_builds": 0,
        "publication_receipts_written": 0,
    }
