"""Prepare/check an immutable offline official-route review package, never publish or approve."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from src.config import PATHS
from src.dashboard.official_routes_contract import PUBLIC_PATH, encoded
from src.source_updates.official_routes_sources import digest, replay
from src.web_export.official_routes import export_official_routes

CODE_FILES = (
    "src/dashboard/official_routes.py", "src/dashboard/official_routes_contract.py",
    "src/dashboard/official_routes_geo.py", "src/source_updates/official_routes.py",
    "src/source_updates/official_routes_sources.py", "src/source_updates/official_routes_geography.py",
    "src/source_updates/afac_margins.py", "src/source_updates/afac_airports.py",
    "src/source_updates/bts_native.py", "src/web_export/official_routes.py",
    "contracts/web/official-routes.schema.json", "config/carrier_crosswalk.csv",
    "data/reference/official_route_cities.csv",
)


def fingerprints(root=PATHS.root) -> dict:
    return {name: digest(root / name) for name in CODE_FILES}


def prepare(selection_path: Path, *, execute=False, check=False, repo=PATHS.root) -> dict:
    selection_path = selection_path.resolve()
    workspace = selection_path.parent
    workspace.relative_to((repo / "tmp").resolve())
    selection = json.loads(selection_path.read_bytes())
    if not execute and not check:
        return dict(status="official_routes_dry_run", output=str(workspace / PUBLIC_PATH),
                    network_requests=0, paid_requests=0, activation="none", publication="not_authorized")
    payload, evidence, files = replay(selection, workspace)
    profile = dict(schema_version="official_route_profile_v1", period=max(i["period"] for i in selection["afac"]),
                   selection={"path": selection_path.relative_to(repo).as_posix(), "sha256": digest(selection_path)},
                   code_sha256=fingerprints(repo), dataset_version=payload["dataset_version"],
                   output_sha256=__import__("hashlib").sha256(encoded(payload)).hexdigest(),
                   activation="none", publication="not_authorized")
    evidence.update(input_files={str(p.relative_to(workspace)): digest(p) for p in sorted(set(files))},
                    code_sha256=profile["code_sha256"])
    outputs = {workspace / PUBLIC_PATH: encoded(payload), workspace / "certification.json": encoded(evidence),
               workspace / "profile.json": encoded(profile)}
    for path, raw in outputs.items():
        if path.exists() and path.read_bytes() != raw:
            raise ValueError(f"Immutable candidate output differs; use a new workspace: {path.name}")
        if check and not path.exists():
            raise ValueError(f"Candidate output absent: {path.name}")
    if execute:
        export_official_routes(payload, workspace / "data/v1")
        for path, raw in outputs.items():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(raw)
    return dict(status="official_routes_checked" if check else "official_routes_prepared_not_authorized",
                dataset_version=payload["dataset_version"], output_sha256=profile["output_sha256"],
                networks=len(payload["networks"]), profile=str(workspace / "profile.json"),
                network_requests=0, paid_requests=0, activation="none", publication="not_authorized")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--selection", required=True, type=Path)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--execute", action="store_true")
    modes.add_argument("--check", action="store_true")
    modes.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    print(json.dumps(prepare(args.selection, execute=args.execute, check=args.check), ensure_ascii=False))


if __name__ == "__main__":
    main()
