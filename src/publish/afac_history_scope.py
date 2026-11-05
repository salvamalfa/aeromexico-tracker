"""Strong public verification for a closed native history composition.

Private source/ledger/owner checks run in inspect/publish. This verifier replays
the public deterministic projections, original public parent verifier and exact
preservation boundary; it never claims the upstream candidate was served.
"""

from __future__ import annotations

import json
import re
import subprocess
from datetime import UTC, datetime
from pathlib import Path

from src.config import PATHS

from . import afac_history_members as members
from . import editorial as transport
from . import manifest as manifests
from .afac_history_contract import (
    ANCHOR,
    PROOF,
    SCHEMA,
    encoded,
    hex_digest,
    parent_public,
    pins,
    proof_parent,
    require_keys,
    sha,
    site_tree,
)

SCOPE_FIELDS = {
    "schema_version",
    "baseline_commit",
    "baseline_manifest_sha256",
    "candidate_parent",
    "producer_code_version",
    "source_bindings",
    "native_profile_sha256",
    "parent_inventory_sha256",
    "parent_request_sha256",
    "input_fingerprint",
    "projection_sha256",
    "data_files",
}


def producer_version(repo=PATHS.root):
    """Bind runtime plus every first-party script/contract, never relabel B602."""
    from src.analysis_agent.entity_adapter import code_version

    repo = Path(repo)
    paths = [*(repo / "scripts").rglob("*.py"), *(repo / "contracts").rglob("*")]
    return sha(
        encoded(
            {
                "runtime": code_version(),
                "support": {
                    p.relative_to(repo).as_posix(): sha(p.read_bytes()) for p in sorted(paths) if p.is_file()
                },
            }
        )
    )


def validate_scope(scope):
    require_keys(scope, SCOPE_FIELDS, "history authority scope")
    if scope["schema_version"] != "afac_history_authority_scope_v2":
        raise ValueError("Unknown native history authority scope")
    hex_digest(scope["baseline_commit"], 40)
    for key in SCOPE_FIELDS - {
        "schema_version",
        "baseline_commit",
        "candidate_parent",
        "source_bindings",
        "native_profile_sha256",
        "data_files",
    }:
        hex_digest(scope[key])
    if [b["product"] for b in scope["source_bindings"]] != list(members.ORDER):
        raise ValueError("Authority must name both exact native correction bindings")
    if set(scope["native_profile_sha256"]) != set(members.ORDER):
        raise ValueError("Missing native correction profile identity")
    for value in scope["native_profile_sha256"].values():
        hex_digest(value)
    for pin in scope["data_files"]:
        from .afac_history_contract import file_pin

        file_pin(pin)
    if [p["path"] for p in scope["data_files"]] != sorted(set(members.BTS_TARGETS) | set(members.TARGETS)):
        raise ValueError("History scope must pin each of the four reviewed output files exactly once")


def anchor(repo=PATHS.root):
    raw = (Path(repo) / ANCHOR).read_bytes()
    if raw != transport._git(repo, "show", f"HEAD:{ANCHOR}"):
        raise ValueError("History composition anchor must be committed")
    value = json.loads(raw)
    require_keys(
        value,
        {"schema_version", "scope", "members", "contracts", "authorization_sha256", "source_audit_sha256"},
        "history anchor",
    )
    if value["schema_version"] != SCHEMA:
        raise ValueError("Unknown history release profile")
    validate_scope(value["scope"])
    for key in ("authorization_sha256", "source_audit_sha256"):
        hex_digest(value[key])
    if (
        sha(encoded(value["members"])) != value["scope"]["projection_sha256"]
        or [u["source_binding"] for u in value["members"]] != value["scope"]["source_bindings"]
    ):
        raise ValueError("History member projections differ from their inspected scope")
    return value


def witness(repo, value, scope):
    require_keys(
        value,
        {
            "baseline_commit",
            "manifest_sha256",
            "files_verified",
            "origin",
            "deployment_commit",
            "deployment_run",
            "verified_at",
        },
        "actual remote witness",
    )
    at = datetime.fromisoformat(value["verified_at"].replace("Z", "+00:00"))
    if at.tzinfo is None or at > datetime.now(UTC):
        raise ValueError("Remote witness lacks its actual zoned observation time")
    old, raw, _ = site_tree(repo, scope["baseline_commit"])
    if (
        sha(raw) != scope["baseline_manifest_sha256"]
        or value["baseline_commit"] != scope["baseline_commit"]
        or value["manifest_sha256"] != scope["baseline_manifest_sha256"]
        or type(value["files_verified"]) is not int
        or value["files_verified"] != len(old["files"])
        or value["origin"] != transport.ORIGIN
        or type(value["deployment_run"]) is not int
        or value["deployment_run"] <= 0
        or not re.fullmatch("[a-f0-9]{40}", value["deployment_commit"])
    ):
        raise ValueError("History proof lacks the exact physically witnessed served baseline")
    transport._git(repo, "merge-base", "--is-ancestor", value["deployment_commit"], scope["baseline_commit"])
    if transport._git(
        repo, "diff", "--name-only", value["deployment_commit"], scope["baseline_commit"], "--", "site"
    ):
        raise ValueError("Remote deployment differs from its recorded served baseline")


def verify_parent_public(repo, parent):
    """Use B's original public verifier and its original historical baseline."""
    from .issuer_scope import verify_historical_baseline

    manifest, raw, files, _ = parent_public(repo, parent)
    # The helper materializes this exact Git tree in its own released code;
    # it does not assert this tree is origin/master or a served publication.
    verify_historical_baseline(
        repo,
        {
            "baseline_commit": parent["site_commit"],
            "baseline_manifest_sha256": parent["manifest_sha256"],
        },
        None,
    )
    return manifest, raw, files


def preserved_files(site, repo, spec):
    scope = spec["scope"]
    parent, _, before, parent_spec = parent_public(repo, scope["candidate_parent"])
    if (
        scope["baseline_commit"] != parent_spec["baseline_commit"]
        or scope["baseline_manifest_sha256"] != parent_spec["baseline_manifest_sha256"]
        or spec["contracts"] != parent["contracts"]
    ):
        raise ValueError("Composition changed the actual served baseline or parent's contracts")
    manifest = manifests.load_manifest(site)
    proof = json.loads((site / PROOF).read_bytes())
    proof_parent(repo, site, manifest, proof)
    if (
        proof["anchor_sha256"] != sha((Path(repo) / ANCHOR).read_bytes())
        or proof["candidate_parent"] != scope["candidate_parent"]
        or manifest["analysis_manifest"] != parent["analysis_manifest"]
        or manifest["contracts"] != parent["contracts"]
    ):
        raise ValueError("Composition changed an approval, upstream edge or contract")
    witness(repo, proof["remote_witness"], scope)
    outputs = members.compose(before, spec["members"])
    if pins(outputs) != scope["data_files"]:
        raise ValueError("History composition differs from its deterministic inspected output pins")
    expected = {**before, **outputs}
    declared = {p["path"]: p for p in manifest["files"]}
    actual = manifests.file_entries(site)
    if (
        set(declared) != set(expected) | {PROOF}
        or len(declared) != len(manifest["files"])
        or {p["path"]: p for p in actual} != declared
        or any(p.is_symlink() for p in Path(site).rglob("*"))
    ):
        raise ValueError("History candidate has unmanifested, missing, duplicate or symlink files")
    for name, raw in expected.items():
        if (Path(site) / name).read_bytes() != raw:
            raise ValueError(f"History composition changed an undeclared byte: {name}")
    # Every thesis is replayed against the actual ledger by the private gate;
    # its public bytes must additionally remain exactly B's originals here.
    return frozenset(name for name in before if name not in outputs)


def verify_afac_history(site, repo=PATHS.root):
    from .verify import _verify_site

    try:
        spec = anchor(repo)
        if producer_version(repo) != spec["scope"]["producer_code_version"]:
            raise ValueError("Current history producer differs from its inspected fingerprint")
        verify_parent_public(repo, spec["scope"]["candidate_parent"])
        return _verify_site(site, preserved_approval_files=preserved_files(Path(site), repo, spec))
    except (ValueError, KeyError, TypeError, OSError, subprocess.SubprocessError) as error:
        return [f"Invalid native history composition: {error}"]


def replay_retained_approvals(repo, site, parent_inputs, ledger_root):
    """Private continuity API; no old-three cohort inference or new approval.

    The caller verifies its actually served baseline with that release's own
    verifier first. Current runtime changes do not relabel the original B602.
    """
    from .afac_history_parent import replay_parent

    spec = anchor(repo)
    scope = spec["scope"]
    if (
        parent_inputs["inventory"]["sha256"] != scope["parent_inventory_sha256"]
        or parent_inputs["request"]["sha256"] != scope["parent_request_sha256"]
    ):
        raise ValueError("Retained approval inputs differ from their composed release")
    value = replay_parent(repo, scope["candidate_parent"], parent_inputs, ledger_root)
    if value["analysis_manifest"] != manifests.load_manifest(site)["analysis_manifest"]:
        raise ValueError("Current publication no longer has the exact retained eight approvals")
    return value


def main(argv=None):
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("site", type=Path)
    args = parser.parse_args(argv)
    problems = verify_afac_history(args.site)
    print(json.dumps({"valid": not problems, "problems": problems}))
    return int(bool(problems))


if __name__ == "__main__":
    raise SystemExit(main())
