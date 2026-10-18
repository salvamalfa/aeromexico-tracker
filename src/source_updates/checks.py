"""Candidate evidence checks: actual periods, contracts, hashes, grain and revisions."""

from __future__ import annotations

import hashlib
import json
from datetime import date, timedelta
from pathlib import Path

from src.source_updates.calendar import local_time
from src.source_updates.catalog import load_catalog, product_map
from src.source_updates.collection import safe_workspace


def verify_bronze(workspace: Path) -> dict[str, dict]:
    root = workspace / "data/bronze"
    manifest = root / "_manifest.jsonl"
    if not manifest.is_file():
        raise ValueError("No Bronze acquisition manifest; Gold freshness is not source collection")
    verified = {}
    for line in manifest.read_text().splitlines():
        row = json.loads(line)
        path = (root / row["source_file"]).resolve()
        if not path.is_relative_to(root.resolve()) or not path.is_file():
            raise ValueError("Bronze source file missing or outside candidate")
        if hashlib.sha256(path.read_bytes()).hexdigest() != row["sha256"]:
            raise ValueError("Bronze SHA-256 mismatch; preserve and investigate")
        verified[row["source_file"]] = row
    if not verified:
        raise ValueError("Empty Bronze manifest")
    return verified


def row_changes(before, after, keys: list[str], values: list[str]) -> dict:
    """Compare natural keys/values; never confuse capture hash changes with row revisions."""
    import pandas as pd

    if not keys or not values:
        raise ValueError("Revision comparison requires natural keys and value columns")

    def records(frame):
        if frame.duplicated(keys).any():
            raise ValueError("Duplicate revision grain; filter the current vintage explicitly")
        return {
            tuple(None if pd.isna(row[k]) else row[k] for k in keys): tuple(
                None if pd.isna(row[v]) else row[v] for v in values
            )
            for _, row in frame.iterrows()
        }

    left, right = records(before), records(after)
    return {
        "added": len(right.keys() - left.keys()),
        "removed": len(left.keys() - right.keys()),
        "changed": sum(left[key] != right[key] for key in left.keys() & right.keys()),
        "unchanged": sum(left[key] == right[key] for key in left.keys() & right.keys()),
    }


def period_end(period: str) -> date:
    if len(period) == 7 and period[4] == "M":
        first = date(int(period[:4]), int(period[5:]), 1)
    elif len(period) == 6 and period[4] == "Q" and period[-1] in "1234":
        first = date(int(period[:4]), int(period[-1]) * 3, 1)
    else:
        raise ValueError("Period must be YYYYMmm or YYYYQn")
    return (first.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)


def check_candidate(workspace: Path, specification: dict) -> dict:
    import pandas as pd

    workspace = safe_workspace(workspace)
    artifacts = verify_bronze(workspace)
    sources, products = load_catalog(), product_map()
    cutoff = local_time(specification["as_of"])
    checks = specification.get("checks", [])
    if not checks:
        raise ValueError("Explicit source/product/period checks are required")
    results = []
    for item in checks:
        result = {
            "product": item["product"],
            "layer": item["layer"],
            "table": item["table"],
            "expected_period": item["expected_period"],
            "latest_published_period": None,
        }
        try:
            product = products[item["product"]]
            if item["layer"] not in {"silver", "gold"} or not item["table"].replace("_", "").isalnum():
                raise ValueError("Use an explicit Silver/Gold table")
            frame = pd.read_parquet(workspace / "data" / item["layer"] / f"{item['table']}.parquet")
            if item["layer"] == "silver":
                from src.transform.silver_contracts import validate_silver_table

                validate_silver_table(item["table"], frame)
            else:
                from src.transform.stage6_contracts import validate_table

                validate_table(item["table"], frame)
            filters = dict(item.get("filters", {}))
            required_entity = {
                "am_sec": "AEROMEXICO",
                "volaris_sec": "VOLARIS",
                "delta_sec": "DELTA",
                "ryanair_sec": "RYANAIR",
                "am_financials": "AEROMEXICO",
                "viva_financials": "VIVA_AEROBUS",
            }.get(item["product"])
            if required_entity and filters.get("carrier_key") != required_entity:
                raise ValueError("Entity-specific product requires its exact carrier_key filter")
            selected = frame.copy()
            for column, value in filters.items():
                selected = selected.loc[selected[column].eq(value)]
            aliases = sources[product["source_key"]]["source_systems"]
            selected = selected.loc[selected["source_system"].isin(aliases)]
            if selected.empty:
                raise ValueError("No rows for the requested source/product/entity")
            # Periods come from parsed rows, never from requested filename or mtime.
            if item.get("period_column") == "year_month":
                periods = (
                    selected["year"].astype(int).astype(str)
                    + "M"
                    + selected["month"].astype(int).map(lambda value: f"{value:02d}")
                )
            elif item.get("period_column") in {"date", "published_at"}:
                timestamps = pd.to_datetime(selected[item["period_column"]])
                if item["period_column"] == "published_at":
                    timestamps = pd.to_datetime(timestamps, utc=True).dt.tz_convert("America/Mexico_City")
                periods = timestamps.dt.strftime("%YM%m")
            else:
                periods = selected[item.get("period_column", "period_id")].astype(str)
            target_end = period_end(item["expected_period"])
            if target_end >= cutoff.date():
                raise ValueError("Expected observation period must be closed before the cutoff")
            observed = sorted(set(periods))
            expected = item["expected_period"]
            if expected not in observed:
                raise ValueError(f"Requested period absent; actual periods end at {max(observed)}")
            selected = selected.loc[periods.eq(expected)]
            for row in selected[["source_file", "source_hash"]].drop_duplicates().itertuples(index=False):
                # Aggregated hashes need the established lineage bridge; never
                # approve them merely because a source_hash string is present.
                artifact = artifacts.get(str(row.source_file))
                if (
                    artifact is None
                    or artifact["sha256"] != row.source_hash
                    or artifact["source_system"] not in aliases
                ):
                    raise ValueError(
                        "Direct Bronze lineage not verified; inherited Gold needs existing lineage gate"
                    )
            values = item["value_columns"]
            if not values or selected[values].notna().sum().sum() == 0:
                raise ValueError("Expected-period rows contain no observed values")
            revision = {"status": "not_compared_no_baseline"}
            if item.get("baseline_file"):
                baseline = (workspace / item["baseline_file"]).resolve()
                if not baseline.is_relative_to(workspace):
                    raise ValueError("Baseline must remain in candidate workspace")
                before = pd.read_parquet(baseline)
                for column, value in filters.items():
                    before = before.loc[before[column].eq(value)]
                # Baseline scope must match the exact selected period and source.
                before = before.loc[before["source_system"].isin(aliases)]
                if item.get("period_column") in {"date", "published_at"}:
                    timestamps = pd.to_datetime(before[item["period_column"]])
                    if item["period_column"] == "published_at":
                        timestamps = pd.to_datetime(timestamps, utc=True).dt.tz_convert("America/Mexico_City")
                    before = before.loc[timestamps.dt.strftime("%YM%m").eq(expected)]
                elif item.get("period_column") == "year_month":
                    before = before.loc[
                        before["year"].eq(int(expected[:4])) & before["month"].eq(int(expected[5:]))
                    ]
                else:
                    before = before.loc[before[item.get("period_column", "period_id")].eq(expected)]
                revision = row_changes(before, selected, item["revision_keys"], values)
            publication = item.get("published_at")
            lag = None
            if publication:
                stamp = local_time(publication)
                if stamp > cutoff or stamp.date() < target_end:
                    raise ValueError("Publication timestamp inconsistent with period/cutoff")
                lag = (stamp.date() - target_end).days
            captured = [
                local_time(row["downloaded_at"])
                for row in artifacts.values()
                if row["source_file"] in set(selected["source_file"])
            ]
            if max(captured) > cutoff:
                raise ValueError("Source captured after the requested historical cutoff")
            result.update(
                status="checks_passed",
                rows=len(selected),
                latest_available_period=max(observed),
                latest_validated_period=expected,
                release_lag_days=lag,
                observation_age_days=(cutoff.date() - target_end).days,
                capture_age_days=(cutoff.date() - max(captured).date()).days,
                null_values=int(selected[values].isna().sum().sum()),
                revisions=revision,
            )
        except Exception as exc:
            result.update(status="blocked", reason=str(exc), error_type=type(exc).__name__)
        results.append(result)
    return {
        "version": 1,
        "mode": "candidate_checks",
        "as_of": cutoff.isoformat(),
        "checks": results,
        "status": "checks_passed" if all(row["status"] == "checks_passed" for row in results) else "blocked",
        "scope": "only_explicit_checks_not_complete_round_certification",
        "approval": "human_review_required",
        "activation": "none",
        "publication": "not_authorized",
    }
