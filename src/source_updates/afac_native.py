"""Prepare verified native AFAC annual inputs for the ordinary candidate pipeline.

No downloads, approvals, site files or financial facts are created here.
Existing Gold/Silver must be restored separately into the isolated workspace.
"""

import argparse
import hashlib
import json
import shutil
from datetime import UTC, datetime
from pathlib import Path

from src.parse.afac.annual_series import native_metadata
from src.parse.afac.market_scope import market_cells
from src.parse.afac.monthly_stats import _load_crosswalk, parse_annual_passenger_workbook
from src.source_updates.collection import safe_workspace, writer


def prepare(workspace, inputs, effective_at, *, execute=False):
    workspace = safe_workspace(Path(workspace))
    effective = datetime.fromisoformat(effective_at)
    if effective.tzinfo is None:
        raise ValueError("Native AFAC effective time requires an explicit timezone")
    if effective > datetime.now(UTC):
        raise ValueError("Native AFAC effective time cannot be in the future")
    observations = []
    copies = []
    for item in inputs:
        if set(item) != {"year", "through", "workbook"}:
            raise ValueError("Native AFAC inputs require exact year, through and workbook")
        path = Path(item["workbook"])
        metadata = native_metadata(path)
        if datetime.fromisoformat(metadata["downloaded_at"]) > effective:
            raise ValueError("Native AFAC effective time cannot precede capture")
        facts, checks = parse_annual_passenger_workbook(path, item["year"])
        market_cells(facts, checks, item["year"], item["through"], _load_crosswalk())
        destination = (workspace / "data/bronze" / metadata["source_file"]).resolve()
        destination.relative_to((workspace / "data/bronze").resolve())
        observations.append(
            {k: item[k] for k in ("year", "through")}
            | {"source_file": metadata["source_file"], "sha256": metadata["sha256"]}
        )
        copies.append((path, destination, metadata))
    if not observations or len({row["year"] for row in observations}) != len(observations):
        raise ValueError("Select one verified native workbook for every requested year")
    planned = dict(
        workspace=str(workspace),
        network_requests=0,
        paid_requests=0,
        observations=observations,
        effective_at=effective_at,
        activation="none",
    )
    if not execute:
        return {**planned, "mode": "dry_run"}
    with writer(workspace):
        manifest = workspace / "data/bronze/_manifest.jsonl"
        existing = (
            [json.loads(line) for line in manifest.read_text().splitlines()] if manifest.exists() else []
        )
        known = {row["source_file"]: row for row in existing}
        for source, destination, metadata in copies:
            if (
                destination.exists()
                and hashlib.sha256(destination.read_bytes()).hexdigest() != metadata["sha256"]
            ):
                raise ValueError("AFAC native capture path already contains different bytes")
            sidecar = destination.with_suffix(destination.suffix + ".meta.json")
            if sidecar.exists() and json.loads(sidecar.read_bytes()) != metadata:
                raise ValueError("AFAC native sidecar differs; preserve the original capture")
            if metadata["source_file"] in known and known[metadata["source_file"]] != metadata:
                raise ValueError("AFAC native manifest capture differs")
        for source, destination, metadata in copies:
            destination.parent.mkdir(parents=True, exist_ok=True)
            if not destination.exists():
                shutil.copyfile(source, destination)
            sidecar = destination.with_suffix(destination.suffix + ".meta.json")
            if not sidecar.exists():
                shutil.copyfile(source.with_suffix(source.suffix + ".meta.json"), sidecar)
            if metadata["source_file"] not in known:
                existing.append(metadata)
        manifest.write_text(
            "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in existing), encoding="utf-8"
        )
        selection = {"schema_version": "afac_native_annual_inputs_v1", "observations": observations}
        update = {"schema_version": "afac_native_update_v1", "effective_at": effective_at}
        for name, value in (
            ("afac_native_annual_inputs.json", selection),
            ("afac_native_update.json", update),
        ):
            (workspace / "data" / name).write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
    return {**planned, "mode": "prepared_candidate"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--inputs", type=Path, required=True)
    parser.add_argument("--effective-at", required=True)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    print(
        json.dumps(
            prepare(
                args.workspace, json.loads(args.inputs.read_bytes()), args.effective_at, execute=args.execute
            ),
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
