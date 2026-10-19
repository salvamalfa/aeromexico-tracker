"""Versioned airport-reference checks, without inventing a monthly observation date."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from src.source_updates.calendar import local_time
from src.source_updates.checks import row_changes


def check_snapshot(workspace: Path, item: dict, selected: pd.DataFrame, artifacts: dict, cutoff) -> dict:
    if item["product"] != "airports_reference" or item["table"] != "dim_airport" or item["layer"] != "gold":
        raise ValueError("Reference adapter only supports the direct OurAirports dimension")
    digest = item.get("sha256", "")
    if len(digest) != 64 or set(selected.source_hash) != {digest}:
        raise ValueError("Reference check requires the exact captured SHA-256")
    captures = []
    for row in selected[["source_file", "source_hash"]].drop_duplicates().itertuples(index=False):
        artifact = artifacts.get(row.source_file)
        if (
            artifact is None
            or artifact["sha256"] != row.source_hash
            or artifact["source_system"] != "ourairports"
        ):
            raise ValueError("Reference Bronze lineage mismatch")
        captures.append(local_time(artifact["downloaded_at"]))
    if not captures or max(captures) > cutoff:
        raise ValueError("Reference capture is absent or after the requested cutoff")
    required = item.get("required_codes", [])
    if not required or set(required) - set(selected.airport_iata):
        raise ValueError("Explicit required airport codes are missing or not declared")
    for column, lower, upper in (("latitude", -90, 90), ("longitude", -180, 180)):
        if not selected[column].dropna().between(lower, upper).all():
            raise ValueError(f"Reference {column} outside geographic bounds")
        if selected.loc[selected.airport_iata.isin(required), column].isna().any():
            raise ValueError(f"Required airport has missing {column}")
    for code, country in item.get("countries", {}).items():
        if selected.loc[selected.airport_iata.eq(code), "country"].tolist() != [country]:
            raise ValueError(f"Reference country mismatch for {code}")
    revisions = {"status": "not_compared_no_baseline"}
    if item.get("baseline_file"):
        path = (workspace / item["baseline_file"]).resolve()
        if not path.is_relative_to(workspace):
            raise ValueError("Reference baseline must remain inside the candidate")
        before = pd.read_parquet(path)
        before = before.loc[before.source_system.eq("ourairports")]
        revisions = row_changes(
            before,
            selected,
            ["airport_iata"],
            ["airport_icao", "name", "country", "latitude", "longitude", "operator_group"],
        )
    return {
        "status": "checks_passed",
        "rows": len(selected),
        "validated_snapshot_sha256": digest,
        "captured_at": max(captures).isoformat(),
        "capture_age_days": (cutoff.date() - max(captures).date()).days,
        "required_codes": sorted(set(required)),
        "revisions": revisions,
        "latest_available_period": None,
        "latest_parsed_period": None,
        "latest_validated_period": None,
        "release_lag_days": None,
        "scope": "Reference snapshot at capture time; no traffic/month completeness or country-safety inference",
    }
