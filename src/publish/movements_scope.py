"""Verify the reviewed Aerocivil semantic correction over an intact released site.

Private preparation replays retained originals. Pages verifies their reviewed
projection pins and the exact historical delta; it never invents source approval.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from datetime import datetime
from pathlib import Path

from src.config import PATHS
from src.source_updates.aerocivil_operational import outputs_valid

from . import editorial as transport
from . import manifest as manifests
from .issuer_scope import encoded as encoded
from .issuer_scope import sha, verify_historical_baseline

ANCHOR = "config/publish/aerocivil-movements-release.json"
PROOF = "aerocivil-movements-publication.json"
PERIODS = tuple(
    [f"2025M{m:02d}" for m in range(1, 13)]
    + [f"2026M{m:02d}" for m in range(1, 8)]
    + [f"2025Q{q}" for q in range(1, 5)]
    + [f"2026Q{q}" for q in range(1, 4)]
)
NETWORK_TARGETS = tuple(
    sorted(
        [f"data/v1/flights/international/{period}.json" for period in PERIODS]
        + [
            f"data/v1/flights/entities/{entity}/international/{period}.json"
            for entity in ("VIVA_AEROBUS", "VOLARIS", "INDUSTRY")
            for period in ("2026M04", "2026M05", "2026M06", "2026Q2")
        ]
    )
)
TARGETS = tuple(sorted([*NETWORK_TARGETS, "data/v1/flights/quarters.json"]))


def _pins(entries, *, frontend=False):
    names = []
    for entry in entries:
        name = entry["path"]
        if (
            set(entry) != {"path", "sha256", "bytes"}
            or not re.fullmatch("[a-f0-9]{64}", entry["sha256"])
            or type(entry["bytes"]) is not int
            or entry["bytes"] <= 0
            or (
                frontend
                and name != "index.html"
                and not re.fullmatch(r"assets/[A-Za-z0-9_.-]+\.(js|css)", name)
            )
        ):
            raise ValueError("Invalid reviewed movement output pin")
        names.append(name)
    if names != sorted(set(names)) or (frontend and "index.html" not in names):
        raise ValueError("Duplicate, unordered or incomplete movement output pins")
    return set(names)


def anchor(repo=PATHS.root):
    raw = (repo / ANCHOR).read_bytes()
    if raw != transport._git(repo, "show", f"HEAD:{ANCHOR}"):
        raise ValueError("Movement release anchor must be committed")
    spec = json.loads(raw)
    fields = {
        "schema_version",
        "product",
        "period_id",
        "stage",
        "baseline_commit",
        "baseline_manifest_sha256",
        "producer_code_version",
        "source_binding",
        "source_evidence",
        "projection_rows",
        "network_files",
        "frontend_files",
        "flights_contract_sha256",
        "authorization_sha256",
    }
    if set(spec) != fields or (spec["schema_version"], spec["product"], spec["period_id"], spec["stage"]) != (
        "aerocivil_movements_release_v1",
        "aerocivil",
        "2026Q3",
        "movements",
    ):
        raise ValueError("Unsupported movement correction profile")
    for field in (
        "baseline_manifest_sha256",
        "producer_code_version",
        "flights_contract_sha256",
        "authorization_sha256",
    ):
        if not re.fullmatch("[a-f0-9]{64}", spec[field]):
            raise ValueError("Invalid reviewed movement digest")
    if not re.fullmatch("[a-f0-9]{40}", spec["baseline_commit"]):
        raise ValueError("Invalid movement baseline commit")
    transport._git(repo, "merge-base", "--is-ancestor", spec["baseline_commit"], "HEAD")
    binding = spec["source_binding"]
    if (
        set(binding) != {"product", "period", "receipt_id", "candidate_as_of", "output_sha256"}
        or binding["product"] != "aerocivil"
        or binding["period"] != "2026M07"
        or not re.fullmatch("[a-f0-9]{32}", binding["receipt_id"])
        or not outputs_valid(binding["output_sha256"])
    ):
        raise ValueError("Movement source binding must name the physically checked July source")
    cutoff = datetime.fromisoformat(binding["candidate_as_of"])
    if cutoff.tzinfo is None:
        raise ValueError("Movement source cutoff must retain its timezone")
    if _pins(spec["network_files"]) != set(TARGETS):
        raise ValueError(
            "Movement correction requires exactly the reviewed 38 networks and their coverage summary"
        )
    _pins(spec["frontend_files"], frontend=True)
    contract = repo / "contracts/web/flights.schema.json"
    if sha(contract.read_bytes()) != spec["flights_contract_sha256"]:
        raise ValueError("Movement contract differs from reviewed pin")
    return spec


def _witness(repo, spec, old, proof):
    if (
        set(proof) != {"schema_version", "anchor_sha256", "remote_witness"}
        or proof["schema_version"] != "aerocivil_movements_publication_v1"
        or proof["anchor_sha256"] != sha((repo / ANCHOR).read_bytes())
    ):
        raise ValueError("Movement proof differs from its committed reviewed anchor")
    w = proof["remote_witness"]
    if (
        w["baseline_commit"] != spec["baseline_commit"]
        or w["manifest_sha256"] != spec["baseline_manifest_sha256"]
        or w["files_verified"] != len(old["files"])
        or w["origin"] != transport.ORIGIN
        or type(w["deployment_run"]) is not int
    ):
        raise ValueError("Movement proof does not identify the actual served baseline")
    transport._git(repo, "merge-base", "--is-ancestor", w["deployment_commit"], spec["baseline_commit"])
    if transport._git(
        repo, "diff", "--name-only", w["deployment_commit"], spec["baseline_commit"], "--", "site"
    ):
        raise ValueError("Movement witness has another published site tree")


def require_no_observed_aerocivil(site):
    """Check all served international periods, including entity namespaces."""
    for path in (site / "data/v1/flights").rglob("*.json"):
        doc = json.loads(path.read_bytes())
        for route in doc.get("routes", []):
            for component in route.get("flight_components", []):
                if "Aerocivil" in component.get("source_label", ""):
                    raise ValueError(f"Aerocivil remains in flight components: {path.name}")
            if (
                "Aerocivil" in route.get("source_label", "")
                and route.get("operation_status") != "recorded_movements_provisional"
            ):
                raise ValueError("Aerocivil route still claims a flight operation status")


def preserved_files(site: Path, repo: Path, spec: dict):
    from .movements_projection import project_file, projection_frame

    old, _ = transport.baseline(repo, spec)
    current = manifests.load_manifest(site)
    _witness(repo, spec, old, json.loads((site / PROOF).read_bytes()))
    if len(old["analysis_manifest"]) != 7 or current["analysis_manifest"] != old["analysis_manifest"]:
        raise ValueError("Movement correction must preserve all seven financial thesis approvals")
    expected_contracts = {**old["contracts"], "flights.schema.json": spec["flights_contract_sha256"]}
    if current["contracts"] != expected_contracts:
        raise ValueError("Movement correction changed an unrelated contract")
    old_names = {p["path"] for p in old["files"]}
    new_names = {p["path"] for p in current["files"]}
    frontend = {p["path"] for p in spec["frontend_files"]}
    if new_names != old_names | frontend | {PROOF} or not set(TARGETS) <= old_names:
        raise ValueError("Movement release added or removed an unrelated surface")
    if any(p.is_symlink() for p in site.rglob("*")):
        raise ValueError("Movement site cannot contain symlinks")
    actual_names = {p.relative_to(site).as_posix() for p in site.rglob("*") if p.is_file()}
    if actual_names != new_names | {manifests.MANIFEST_NAME}:
        raise ValueError("Movement site contains unmanifested files")
    if spec["source_evidence"].get("source_binding") != spec["source_binding"]:
        raise ValueError("Historical movement projection is not bound to its current July source")
    frame = projection_frame(spec["projection_rows"], spec["source_evidence"])
    if transport.frontend_entries(site) != spec["frontend_files"]:
        raise ValueError("Movement frontend pins differ from the reachable dashboard closure")
    for pin in spec["network_files"] + spec["frontend_files"]:
        raw = (site / pin["path"]).read_bytes()
        if sha(raw) != pin["sha256"] or len(raw) != pin["bytes"]:
            raise ValueError("Movement output differs from reviewed pins")
    for name in TARGETS:
        before = json.loads(transport._git(repo, "show", f"{spec['baseline_commit']}:site/{name}"))
        after = json.loads((site / name).read_bytes())
        if after != project_file(name, before, frame):
            raise ValueError(f"Movement correction changed an unrelated count or field: {name}")
    preserved = set()
    for pin in old["files"]:
        name = pin["path"]
        if name == "index.html" or name in TARGETS:
            continue
        raw = (site / name).read_bytes()
        if sha(raw) != pin["sha256"] or len(raw) != pin["bytes"]:
            raise ValueError(f"Movement correction changed historical bytes: {name}")
        preserved.add(name)
    require_no_observed_aerocivil(site)
    return frozenset(preserved)


def verify_movements(site: Path, repo: Path = PATHS.root):
    from src.analysis_agent.entity_adapter import code_version

    from .verify import _verify_site

    try:
        spec = anchor(repo)
        if code_version() != spec["producer_code_version"]:
            raise ValueError("Movement runtime differs from reviewed producer")
        verify_historical_baseline(repo, spec, site)
        return _verify_site(site, preserved_approval_files=preserved_files(site, repo, spec))
    except (ValueError, KeyError, OSError, TypeError, subprocess.SubprocessError) as error:
        return [f"Invalid Aerocivil movement publication: {error}"]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("site", type=Path)
    args = parser.parse_args(argv)
    problems = verify_movements(args.site)
    print(json.dumps({"valid": not problems, "problems": problems}))
    return int(bool(problems))


if __name__ == "__main__":
    raise SystemExit(main())
