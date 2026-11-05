"""Inspect and publish native AFAC/BTS corrections without renewing any thesis.

Inspect is deliberately nonpublishable. A separate exact data-only source audit
and authentic retained owner decision are required before prepare/publication.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import tempfile
from datetime import UTC, datetime
from pathlib import Path

from src.analysis_agent import lifecycle as flow
from src.config import PATHS

from . import afac_history_members as members
from . import afac_history_scope as verification
from . import afac_history_witness, gate
from . import editorial as transport
from . import manifest as manifests
from .afac_history_contract import (
    ANCHOR,
    PROOF,
    PROOF_SCHEMA,
    SCHEMA,
    encoded,
    materialize_site,
    parent_public,
    pins,
    relative_name,
    require_keys,
    sha,
)
from .afac_history_parent import file_ref, identity, parent_inventory, physical, replay_parent


def committed_inputs(repo):
    manifests.refuse_if_build_inputs_dirty(root=repo, paths=(*manifests.BUILD_INPUT_PATHS, "scripts"))


def request_inputs(repo, path):
    path = Path(path)
    name = path.relative_to(repo).as_posix() if path.is_absolute() else path.as_posix()
    path = physical(repo, name)
    request = json.loads(path.read_bytes())
    require_keys(
        request,
        {"schema_version", "candidate_parent", "parent_inputs", "native_sources", "authorization"},
        "native history request",
    )
    if request["schema_version"] != "afac_history_request_v2":
        raise ValueError("Unknown correction request; v1 is not a fallback")
    members.selections(request)
    for selection in request["native_sources"]:
        file_ref(repo, selection["profile"])
    return path, request


def working_parent(repo, raw_manifest, files):
    site = physical(repo, "site", directory=True)
    if (site / manifests.MANIFEST_NAME).read_bytes() != raw_manifest or manifests.file_entries(site) != pins(
        files
    ):
        raise ValueError("Working site differs from the exact unserved candidate parent")
    if any(p.is_symlink() for p in site.rglob("*")):
        raise ValueError("Candidate parent cannot contain symlinks")


def evaluate(repo, request_path, *, existing=False):
    """One complete private replay epoch; caller holds the authoritative lock."""
    path, request = request_inputs(repo, request_path)
    parent, parent_raw, parent_files, parent_spec = parent_public(repo, request["candidate_parent"])
    if not existing:
        working_parent(repo, parent_raw, parent_files)
    original = parent_inventory(repo, request["parent_inputs"])[2]
    approvals = replay_parent(repo, request["candidate_parent"], request["parent_inputs"], flow.ROOT)
    with tempfile.TemporaryDirectory(prefix="afac-native-parent-") as temporary:
        parent_site = materialize_site(Path(temporary) / "site", parent_raw, parent_files)
        first = members.replay(repo, request, parent_site, parent_files)
        second = members.replay(repo, request, parent_site, parent_files)
    if first != second or parent_inventory(repo, request["parent_inputs"])[2] != original:
        raise ValueError("Native/original physical inputs changed during complete inspection")
    units, outputs, native_inputs = first
    members.original_gold(repo, request["candidate_parent"], units)
    state = {
        "request": identity(path),
        "original_inputs": original,
        "native_inputs": native_inputs,
        "parent_inventory": identity(file_ref(repo, request["parent_inputs"]["inventory"])),
    }
    scope = {
        "schema_version": "afac_history_authority_scope_v2",
        "baseline_commit": parent_spec["baseline_commit"],
        "baseline_manifest_sha256": parent_spec["baseline_manifest_sha256"],
        "candidate_parent": request["candidate_parent"],
        "producer_code_version": verification.producer_version(repo),
        "source_bindings": [u["source_binding"] for u in units],
        "native_profile_sha256": {s["product"]: s["profile"]["sha256"] for s in request["native_sources"]},
        "parent_inventory_sha256": request["parent_inputs"]["inventory"]["sha256"],
        "parent_request_sha256": request["parent_inputs"]["request"]["sha256"],
        # Authorization is intentionally excluded: adding its reference after
        # inspect must not create a circular authority/request hash.
        "input_fingerprint": sha(encoded({k: v for k, v in state.items() if k != "request"})),
        "projection_sha256": sha(encoded(units)),
        "data_files": pins(outputs),
    }
    verification.validate_scope(scope)
    if approvals["analysis_manifest"] != parent["analysis_manifest"]:
        raise ValueError("Original approval replay differs from its exact candidate manifest")
    return {
        "request": request,
        "scope": scope,
        "members": units,
        "outputs": outputs,
        "authorized": approvals["authorized"],
        "state": state,
        "contracts": parent["contracts"],
    }


def require_current_base(repo, scope, *, remote=False):
    commit = (
        transport._git(repo, "ls-remote", "origin", "refs/heads/master").decode().split()[0]
        if remote
        else gate._trusted_site_commit(repo)
    )
    if commit != scope["baseline_commit"]:
        raise ValueError("Actual trusted/remote baseline moved; unserved parent is not a substitute")


def retain_inspection(repo, out, reviewed, outputs):
    """Retain private review bytes, never an authority or publishable site."""
    out = Path(out)
    name = out.relative_to(repo).as_posix() if out.is_absolute() else out.as_posix()
    relative_name(name)
    destination = Path(repo) / name
    if (
        not name.startswith("tmp/")
        or destination.exists()
        or destination.is_symlink()
        or any(p.is_symlink() for p in destination.parents)
        or not destination.resolve().is_relative_to((Path(repo) / "tmp").resolve())
    ):
        raise ValueError("Retain inspection only in a new physical private tmp subdirectory")
    if pins(outputs) != reviewed["scope"]["data_files"]:
        raise ValueError("Inspection review bytes differ from their exact inspected pins")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="inspection-", dir=destination.parent) as temporary:
        staging = Path(temporary) / "review"
        staging.mkdir()
        for name, raw in outputs.items():
            target = staging / relative_name(name)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(raw)
        (staging / "inspection.json").write_bytes(encoded(reviewed))
        staging.rename(destination)


def inspect(request_path, inspection_out=None):
    repo = PATHS.root
    committed_inputs(repo)
    head = manifests.current_commit(repo)
    with flow.writer(flow.ROOT):
        result = evaluate(repo, request_path)
        require_current_base(repo, result["scope"])
    committed_inputs(repo)
    if (
        manifests.current_commit(repo) != head
        or verification.producer_version(repo) != result["scope"]["producer_code_version"]
    ):
        raise ValueError("Correction producer changed during inspection")
    reviewed = {
        "status": "scope_inspected_not_published",
        "scope": result["scope"],
        "members": result["members"],
        "contracts": result["contracts"],
    }
    if inspection_out is not None:
        retain_inspection(repo, inspection_out, reviewed, result["outputs"])
    return reviewed


def authority(repo, request, scope):
    if request["authorization"] is None:
        raise ValueError(
            "Correction publication requires retained consent for the exact inspected data scope"
        )
    path = file_ref(repo, request["authorization"])
    digest = sha(path.read_bytes())
    if path != Path(repo) / "analysis_runs/dashboard_updates/authorizations" / (digest + ".json"):
        raise ValueError("Data correction authority is outside its canonical hash path")
    value = json.loads(path.read_bytes())
    require_keys(
        value, {"schema_version", "status", "scope", "source_audit", "owner_consent"}, "history authority"
    )
    if (
        value["schema_version"] != "afac_history_authorization_v2"
        or value["status"] != "authorized"
        or value["scope"] != scope
    ):
        raise ValueError("History authority is revoked or names another exact source/data scope")
    consent = value["owner_consent"]
    require_keys(consent, {"source_reference", "instruction", "received_at"}, "actual owner consent")
    if any(not isinstance(v, str) or not v.strip() for v in consent.values()):
        raise ValueError("Retain the owner's authentic instruction and provenance")
    at = datetime.fromisoformat(consent["received_at"].replace("Z", "+00:00"))
    if at.tzinfo is None or at > datetime.now(UTC):
        raise ValueError("Owner consent needs its real zoned timestamp")
    audit_path = file_ref(repo, value["source_audit"])
    audit_hash = sha(audit_path.read_bytes())
    if audit_path != Path(repo) / "analysis_runs/dashboard_updates/audits" / (audit_hash + ".json"):
        raise ValueError("Correction source audit is outside its canonical hash path")
    audit = json.loads(audit_path.read_bytes())
    require_keys(
        audit,
        {"schema_version", "status", "scope", "unresolved_findings", "reviewer_reference"},
        "source audit",
    )
    if (
        audit["schema_version"] != "afac_history_source_audit_v2"
        or audit["status"] != "passed"
        or audit["scope"] != scope
        or audit["unresolved_findings"] != []
        or not isinstance(audit["reviewer_reference"], str)
        or not audit["reviewer_reference"].strip()
    ):
        raise ValueError("History publication needs a passing independent audit of this exact scope")
    return digest, audit_hash


def prepare(request_path):
    inspected = inspect(request_path)
    _, request = request_inputs(PATHS.root, request_path)
    approved, audit = authority(PATHS.root, request, inspected["scope"])
    spec = {
        "schema_version": SCHEMA,
        "scope": inspected["scope"],
        "members": inspected["members"],
        "contracts": inspected["contracts"],
        "authorization_sha256": approved,
        "source_audit_sha256": audit,
    }
    path = PATHS.root / ANCHOR
    tracked = subprocess.run(["git", "show", f"HEAD:{ANCHOR}"], cwd=PATHS.root, capture_output=True)
    previous = tracked.stdout if tracked.returncode == 0 else None
    actual = path.read_bytes() if path.exists() else None
    if path.is_symlink() or (actual != previous and (actual is None or json.loads(actual) != spec)):
        raise ValueError("Correction anchor has an unrelated local edit")
    path.parent.mkdir(parents=True, exist_ok=True)
    if actual is None or json.loads(actual) != spec:
        descriptor, temporary = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
        try:
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(encoded(spec))
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
        finally:
            Path(temporary).unlink(missing_ok=True)
    return {"status": "pins_prepared_not_published", "anchor": spec}


def publish(request_path, out):
    repo = PATHS.root
    if Path(out).resolve() != (repo / "site").resolve():
        raise ValueError("History publication targets only this checkout's tracked site")
    committed_inputs(repo)
    head, spec = manifests.current_commit(repo), verification.anchor(repo)
    scope = spec["scope"]
    existing = (Path(out) / PROOF).exists()

    def check():
        result = evaluate(repo, request_path, existing=existing)
        if (
            result["scope"] != scope
            or result["members"] != spec["members"]
            or result["contracts"] != spec["contracts"]
            or authority(repo, result["request"], scope)
            != (spec["authorization_sha256"], spec["source_audit_sha256"])
        ):
            raise ValueError("Correction changed after its exact inspected authority")
        return result

    with flow.writer(flow.ROOT):
        first = check()
        if existing:
            problems = verification.verify_afac_history(Path(out), repo)
            if problems:
                raise ValueError(f"Existing correction is not intact: {problems[:3]}")
            return {
                "status": "already_built_not_a_deployment_claim",
                "manifest": manifests.load_manifest(out),
            }
        require_current_base(repo, scope, remote=True)
    _, raw_parent, parent_files, _ = parent_public(repo, scope["candidate_parent"])
    with tempfile.TemporaryDirectory(prefix="afac-corrected-site-") as temporary:
        candidate = materialize_site(
            Path(temporary) / "site", raw_parent, {**parent_files, **first["outputs"]}
        )
        (candidate / manifests.MANIFEST_NAME).unlink()
        with flow.writer(flow.ROOT):
            remote_witness = afac_history_witness.witness_remote(repo, scope)
            verification.witness(repo, remote_witness, scope)
            if check() != first:
                raise ValueError("Correction input/authority/approval changed during construction")
            (candidate / PROOF).write_bytes(
                encoded(
                    {
                        "schema_version": PROOF_SCHEMA,
                        "anchor_sha256": sha((repo / ANCHOR).read_bytes()),
                        "remote_witness": remote_witness,
                        "candidate_parent": scope["candidate_parent"],
                    }
                )
            )

            def validate(prepared):
                from .verify import _verify_site

                preserved = verification.preserved_files(prepared, repo, spec)
                problems = _verify_site(prepared, preserved_approval_files=preserved)
                if problems:
                    raise ValueError(f"Native correction candidate refused: {problems[:3]}")
                committed_inputs(repo)
                if (
                    manifests.current_commit(repo) != head
                    or verification.anchor(repo) != spec
                    or verification.producer_version(repo) != scope["producer_code_version"]
                ):
                    raise ValueError("Correction producer/anchor/HEAD changed before swap")
                require_current_base(repo, scope, remote=True)
                # Files and consent are checked again after validation, while
                # the same authoritative writer lock still covers the swap.
                if check() != first:
                    raise ValueError("Native correction changed immediately before atomic swap")

            manifest = gate.assemble_site(
                candidate,
                first["authorized"],
                Path(out),
                contracts=spec["contracts"],
                validate_candidate=validate,
            )
    return {
        "status": "site_built_verified_not_served",
        "manifest": manifest,
        "receipt": gate.write_receipt(manifest, first["authorized"], Path(out)),
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group(required=True)
    for name in ("inspect", "prepare", "request"):
        modes.add_argument("--" + name, type=Path)
    parser.add_argument("--out", type=Path, default=PATHS.root / "site")
    parser.add_argument("--inspection-out", type=Path)
    args = parser.parse_args(argv)
    if args.inspection_out is not None and args.inspect is None:
        parser.error("--inspection-out is only valid with --inspect")
    try:
        value = (
            inspect(args.inspect, args.inspection_out)
            if args.inspect
            else prepare(args.prepare)
            if args.prepare
            else publish(args.request, args.out)
        )
        print(json.dumps(value, ensure_ascii=False))
        return 0
    except (ValueError, KeyError, TypeError, OSError, RuntimeError, subprocess.SubprocessError) as error:
        print(f"Native history composition refused: {error}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
