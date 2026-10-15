"""Build a private flight-coverage preview; never creates publication receipts.

Requires committed build inputs and retained local Gold. Does not fetch data,
fit estimators, change analysis approvals, or deploy either service.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
from pathlib import Path

from src.config import PATHS
from src.dashboard.flights import build_flight_payload
from src.publish.manifest import refuse_if_build_inputs_dirty
from src.publish.verify import verify_site
from src.web_export.flights import export_flights


def identities(directory: Path) -> dict[str, str]:
    return {p.relative_to(directory).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in directory.rglob("*") if p.is_file() and "flights" not in p.relative_to(directory).parts}


def build_preview(out: Path, *, include_existing_us_estimates: bool = False) -> dict:
    out = out.resolve()
    if out.exists():
        raise ValueError("Preview destination already exists; preserve it and choose a fresh path")
    if out.is_relative_to(PATHS.root) and not out.is_relative_to(PATHS.root / "analysis_runs/research"):
        raise ValueError("A private preview cannot replace a tracked site or another repository path")
    refuse_if_build_inputs_dirty()
    baseline = PATHS.root / "site"
    problems = verify_site(baseline)
    if problems:
        raise ValueError(f"Published baseline is invalid: {problems[:3]}")
    before = identities(baseline / "data/v1")
    data = PATHS.root / "web/public/data/v1"
    if data.exists():
        shutil.rmtree(data)
    shutil.copytree(baseline / "data/v1", data)
    shutil.rmtree(data / "flights")
    payload = build_flight_payload(include_existing_us_estimates=include_existing_us_estimates)
    written = export_flights(payload, data)
    if identities(data) != before:
        raise ValueError("Preview changed financial data or an approved analysis")
    subprocess.run(["npm", "run", "check"], cwd=PATHS.root / "web", check=True)
    subprocess.run(["npm", "run", "build"], cwd=PATHS.root / "web", check=True)
    dist = PATHS.root / "web/dist"
    if identities(dist / "data/v1") != before:
        raise ValueError("Frontend build changed financial data or an approved analysis")
    shutil.copytree(dist, out)
    if (out / "publication_manifest.json").exists():
        raise ValueError("An unapproved preview must not carry a production publication manifest")
    metadata = {
        "schema_version": 1, "production_ready": False, "owner_approval_required": True,
        "provider_calls": 0, "new_model_fits": 0, "new_capture_only_months": False,
        "include_existing_us_estimates": include_existing_us_estimates,
        "code_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=PATHS.root, text=True).strip(),
        "map_file_count": len(written), "nonflight_data_sha256": before,
        "retained_gold_sha256": {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                                 for p in sorted(PATHS.gold.glob("*.parquet"))},
    }
    (out / "preview-metadata.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n")
    return metadata


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--include-existing-us-estimates", action="store_true",
                        help="Preview an explicit policy proposal: retained estimates only where no observed route wins")
    args = parser.parse_args()
    result = build_preview(args.out, include_existing_us_estimates=args.include_existing_us_estimates)
    print(f"Private preview: {result['map_file_count']} map files; no publication or new model activation")


if __name__ == "__main__":
    main()
