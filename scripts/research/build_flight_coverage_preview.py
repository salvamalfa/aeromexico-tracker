"""Build a private flight-coverage preview; never creates publication receipts.

Requires committed build inputs and retained local Gold. Does not fetch data,
fit estimators, change analysis approvals, or deploy either service.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import shutil
import subprocess
from pathlib import Path

from src.config import PATHS
from src.dashboard.flights import build_flight_payload
from src.publish.manifest import BUILD_INPUT_PATHS, refuse_if_build_inputs_dirty
from src.publish.verify import verify_site
from src.transform.stage6_warehouse import build_warehouse
from src.web_export.flights import export_flights


def identities(directory: Path) -> dict[str, str]:
    return {p.relative_to(directory).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in directory.rglob("*") if p.is_file() and "flights" not in p.relative_to(directory).parts}


def committed_preview_inputs() -> str:
    refuse_if_build_inputs_dirty(root=PATHS.root, paths=BUILD_INPUT_PATHS + (
        "scripts/research/build_flight_coverage_preview.py",
        "sql",
    ))
    return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=PATHS.root, text=True).strip()


def retained_gold_hashes() -> dict[str, str]:
    return {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(PATHS.gold.glob("*.parquet"))}


def refresh_retained_warehouse() -> dict[str, str]:
    inputs = retained_gold_hashes()
    build_warehouse(max_stage=9)
    if retained_gold_hashes() != inputs:
        raise ValueError("Gold changed while rebuilding the preview warehouse")
    return inputs


def load_us_admission(path: Path | None, *, enabled: bool) -> tuple[dict | None, dict]:
    """An opt-in preview must name its frozen, reviewable cell screen."""
    if enabled != (path is not None):
        raise ValueError("US estimates require both explicit opt-in and a cell admission policy")
    if path is None:
        return None, {}
    raw = path.read_bytes()
    policy = json.loads(raw)
    if policy.get("default_enabled") is not False or policy.get("review_or_rejected_cells_included") != 0:
        raise ValueError("US admission policy must exclude review/rejected cells and remain default-off")
    if policy.get("new_calls") != 0 or policy.get("fits") != 0 or policy.get("activates_analysis") is not False:
        raise ValueError("US admission policy cannot authorize calls, fits or analysis activation")
    cells, total = {}, 0.0
    for row in policy.get("cells", []):
        key = (row["carrier_key"], row["period_id"], row["origin_iata"], row["destination_iata"])
        if key[0] not in {"AEROMEXICO", "AEROMEXICO_CONNECT", "VOLARIS", "VIVA_AEROBUS"}:
            raise ValueError("Unknown US admission operator")
        if not re.fullmatch(r"\d{4}M(?:0[1-9]|1[0-2])", key[1]):
            raise ValueError("Invalid US admission month")
        if any(not re.fullmatch(r"[A-Z]{3}", value) for value in key[2:]) or key[2] == key[3]:
            raise ValueError("Invalid US admission directional route")
        value = row["estimated_flights_retained"]
        if type(value) not in (int, float) or not math.isfinite(value) or value <= 0 or key in cells:
            raise ValueError("Invalid or duplicate US admission cell")
        cells[key] = float(value)
        total += value
    declared_total = policy.get("retained_estimated_flights")
    if (not cells or type(declared_total) not in (int, float)
            or not math.isfinite(declared_total) or abs(total - declared_total) > 1e-8):
        raise ValueError("US admission total does not match its cells")
    return cells, {
        "us_estimate_admission_sha256": hashlib.sha256(raw).hexdigest(),
        "admitted_us_estimate_cell_count": len(cells),
        "retained_us_frequencies_admitted": total,
    }


def validate_us_admission(cells: dict | None, gold: Path) -> None:
    """Require the exact screened value once per retained operator/direction/month.

    Validate Gold before rebuilding or writing preview files. Unrelated cells
    and later BTS observations cannot change the frozen frequency screen.
    """
    if cells is None:
        return
    import pandas as pd

    keys = ("carrier_key", "period_id", "origin_iata", "destination_iata")
    frame = pd.read_parquet(
        gold / "fact_route_carrier_international_estimate.parquet",
        columns=[*keys, "departures_estimated"],
    )
    found = set()
    for row in frame.itertuples(index=False):
        key = tuple(str(getattr(row, field)) for field in keys)
        if key not in cells:
            continue
        if key in found:
            raise ValueError("Duplicate retained US admission cell")
        found.add(key)
        value = row.departures_estimated
        if pd.isna(value) or isinstance(value, bool) or not math.isfinite(value) or value != cells[key]:
            raise ValueError("Retained US admission value differs from the frozen cell screen")
    if found != set(cells):
        raise ValueError("Retained US admission cell is missing from Gold")


def build_preview(out: Path, *, include_existing_us_estimates: bool = False,
                  us_estimate_admission: Path | None = None) -> dict:
    out = out.resolve()
    if out.exists():
        raise ValueError("Preview destination already exists; preserve it and choose a fresh path")
    if out.is_relative_to(PATHS.root) and not out.is_relative_to(PATHS.root / "analysis_runs/research"):
        raise ValueError("A private preview cannot replace a tracked site or another repository path")
    code_commit = committed_preview_inputs()
    allowed_cells, admission = load_us_admission(us_estimate_admission, enabled=include_existing_us_estimates)
    validate_us_admission(allowed_cells, PATHS.gold)
    baseline = PATHS.root / "site"
    problems = verify_site(baseline)
    if problems:
        raise ValueError(f"Published baseline is invalid: {problems[:3]}")
    gold_inputs = refresh_retained_warehouse()
    before = identities(baseline / "data/v1")
    data = PATHS.root / "web/public/data/v1"
    if data.exists():
        shutil.rmtree(data)
    shutil.copytree(baseline / "data/v1", data)
    shutil.rmtree(data / "flights")
    payload = build_flight_payload(include_existing_us_estimates=include_existing_us_estimates,
                                   allowed_us_estimate_cells=allowed_cells)
    written = export_flights(payload, data)
    if identities(data) != before:
        raise ValueError("Preview changed financial data or an approved analysis")
    subprocess.run(["npm", "run", "check"], cwd=PATHS.root / "web", check=True)
    subprocess.run(["npm", "run", "build"], cwd=PATHS.root / "web", check=True)
    dist = PATHS.root / "web/dist"
    if identities(dist / "data/v1") != before:
        raise ValueError("Frontend build changed financial data or an approved analysis")
    if retained_gold_hashes() != gold_inputs or committed_preview_inputs() != code_commit:
        raise ValueError("Preview inputs changed during the build")
    if us_estimate_admission is not None and load_us_admission(us_estimate_admission, enabled=True)[1] != admission:
        raise ValueError("US admission policy changed during the build")
    shutil.copytree(dist, out)
    if (out / "publication_manifest.json").exists():
        raise ValueError("An unapproved preview must not carry a production publication manifest")
    metadata = {
        "schema_version": 1, "production_ready": False, "owner_approval_required": True,
        "provider_calls": 0, "new_model_fits": 0, "new_capture_only_months": False,
        "include_existing_us_estimates": include_existing_us_estimates,
        "code_commit": code_commit,
        "preview_builder_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "warehouse_rebuilt_from_gold": True,
        "map_file_count": len(written), "nonflight_data_sha256": before,
        "retained_gold_sha256": gold_inputs,
        **admission,
    }
    (out / "preview-metadata.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n")
    return metadata


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--include-existing-us-estimates", action="store_true",
                        help="Preview screened retained US cells where no observed cell wins")
    parser.add_argument("--us-estimate-admission", type=Path,
                        help="Private, frozen admission JSON required with the explicit US opt-in")
    args = parser.parse_args()
    result = build_preview(args.out, include_existing_us_estimates=args.include_existing_us_estimates,
                           us_estimate_admission=args.us_estimate_admission)
    print(f"Private preview: {result['map_file_count']} map files; no publication or new model activation")


if __name__ == "__main__":
    main()
