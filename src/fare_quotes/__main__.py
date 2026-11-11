"""Rebuild private Silver/Gold from retained, read-back Google Sheets Bronze snapshots."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from src.fare_quotes.normalize import amount, decode_snapshot, digest


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8"
    )
    temporary.replace(path)


def rebuild(bronze: Path, silver: Path, gold: Path) -> dict:
    observations, rejected, snapshots = {}, [], []
    field_reviews = {}
    for path in sorted((bronze.parent / "fare_quote_field_reviews").glob("*.json")):
        raw = path.read_bytes()
        review = json.loads(raw)
        if review.get("schema_version") != "fare_quote_field_review_v1":
            raise ValueError("Unknown field review schema")
        reviewed_at = datetime.fromisoformat(review["reviewed_at"].replace("Z", "+00:00"))
        if reviewed_at.tzinfo is None:
            raise ValueError("Field review timestamp needs a timezone")
        key = (review["provider"], review["capture_id"], review["source_snapshot_sha256"])
        prior = field_reviews.setdefault(key, [])
        if any(timestamp == reviewed_at and value != review for timestamp, value in prior):
            raise ValueError("Ambiguous field reviews at the same timestamp")
        if (reviewed_at, review) not in prior:
            prior.append((reviewed_at, review))
        snapshots.append(
            dict(path=str(path.resolve()), sha256=hashlib.sha256(raw).hexdigest(), kind="field_review")
        )
    verifications = {}
    for path in sorted((bronze.parent / "fare_quote_verifications").glob("*.json")):
        raw = path.read_bytes()
        entry = json.loads(raw)
        verifications[(entry["provider"], entry["capture_key"])] = entry["verification"]
        snapshots.append(
            dict(
                path=str(path.resolve()),
                sha256=hashlib.sha256(raw).hexdigest(),
                kind="selected_flight_verification",
            )
        )
    capture_ids = {}
    conflicts = set()
    for path in sorted(bronze.rglob("*.json")):
        raw = path.read_bytes()
        snapshot = json.loads(raw)
        rows, errors = decode_snapshot(snapshot, verifications)
        snapshots.append(
            dict(
                path=str(path.resolve()),
                sha256=hashlib.sha256(raw).hexdigest(),
                provider=snapshot["provider"],
                fetched_at=snapshot["fetched_at"],
            )
        )
        rejected.extend(errors)
        for row in rows:
            for source in row["sources"]:
                source.update(
                    snapshot_sha256=hashlib.sha256(raw).hexdigest(), snapshot_path=str(path.resolve())
                )
            identity = row["observation_id"]
            capture_id = row["capture_id"]
            if capture_id:
                key = (row["provider"], capture_id)
                prior = capture_ids.get(key)
                if prior and prior != identity:
                    conflicts.update((prior, identity))
                capture_ids[key] = identity
            if identity in observations:
                for source in row["sources"]:
                    if source not in observations[identity]["sources"]:
                        observations[identity]["sources"].append(source)
            else:
                observations[identity] = row
    applied_reviews = set()
    # A snapshot is a read of an observation. Merge identical reads before a
    # hash-anchored review changes the effective fields of that observation.
    for row in observations.values():
        candidates = []
        for source in row["sources"]:
            key = (row["provider"], row["capture_id"], source["snapshot_sha256"])
            if key in field_reviews:
                applied_reviews.add(key)
                candidates.extend(field_reviews[key])
        if candidates:
            by_time = {}
            for timestamp, review in candidates:
                if timestamp in by_time and by_time[timestamp] != review:
                    raise ValueError("Ambiguous latest reviews for an observation")
                by_time[timestamp] = review
            # Later review of another field must not resurrect a disputed cash
            # price. Replay append-only decisions in time, retaining every event.
            reviews = [review for _, review in sorted(by_time.items())]
            for review in reviews:
                _apply_field_review(row, review)
            row["field_review_history"] = reviews
            row["observation_id"] = digest(
                {k: v for k, v in row.items() if k not in {"sources", "raw_source_row", "observation_id"}}
            )
    if set(field_reviews) != applied_reviews:
        raise ValueError("Field review has no matching snapshot identity and fingerprint")
    for identity in conflicts:
        rejected.append(
            dict(
                reason="Conflicting reused capture_id; both versions quarantined",
                observation=observations.pop(identity),
            )
        )
    rows = sorted(observations.values(), key=lambda r: (r["query_date"], r["provider"], r["observation_id"]))

    def quote_identity(row):
        return tuple(
            row.get(k)
            for k in (
                "provider",
                "query_date",
                "origin",
                "destination",
                "departure_date",
                "return_date",
                "fare",
                "outbound_departure_time",
                "return_departure_time",
            )
        )

    verified = {
        quote_identity(row): row["observation_id"]
        for row in rows
        if row["status"] in {"ok", "partial_redemption"}
    }
    for row in rows:
        if row["status"] == "legacy_unverified" and quote_identity(row) in verified:
            row["superseded_by_verified"] = verified[quote_identity(row)]
    write_json(silver / "observations.json", rows)
    write_json(silver / "quarantine.json", rejected)
    effective = [row for row in rows if "superseded_by_verified" not in row]
    display_rows = [{k: v for k, v in row.items() if k != "raw_source_row"} for row in effective]
    counts = {}
    for provider in ("AMR", "DOTERS", "VOLARIS"):
        selected = [row for row in effective if row["provider"] == provider]
        counts[provider] = dict(
            observations=len(selected),
            statuses=dict(Counter(r["status"] for r in selected)),
            verified_cash=sum(
                r["status"] in {"ok", "partial_redemption"} and r["cash_final_mxn"] is not None
                for r in selected
            ),
            complete=sum(r["status"] == "ok" and r["cash_final_mxn"] is not None for r in selected),
        )
    payload = dict(
        schema_version="local_fare_quotes_v1",
        private=True,
        built_at=datetime.now(timezone.utc).isoformat(),
        period_basis="query_date_America_Mexico_City",
        periods=sorted({r["period_id"] for r in rows}),
        snapshots=snapshots,
        rows=display_rows,
        counts=counts,
        quarantine_count=len(rejected),
    )
    payload["dataset_version"] = digest(dict(rows=display_rows, snapshots=snapshots))
    write_json(gold, payload)
    return payload


def _apply_field_review(row, review):
    for field, value in review["effective_overrides"].items():
        if field not in {"points", "redemption_taxes_mxn", "cash_final_mxn"}:
            raise ValueError("Field review attempts an unauthorized override")
        if field == "cash_final_mxn" and value is not None:
            raise ValueError("A cash correction requires explicit observed_correction evidence")
        row[field] = amount(value, integer=field == "points")
    if "observed_correction" in review:
        correction = review["observed_correction"]
        evidence = review.get("correction_evidence", {})
        observed_at = datetime.fromisoformat(evidence.get("observed_at", "").replace("Z", "+00:00"))
        if (
            review.get("verified") is not True
            or evidence.get("verified") is not True
            or observed_at.tzinfo is None
            or not evidence.get("evidence_url", "").startswith("https://")
            or not re.fullmatch(r"[a-f0-9]{64}", evidence.get("dom_sha256", ""))
        ):
            raise ValueError("Observed cash correction lacks verified, timestamped DOM evidence")
        if not isinstance(correction, dict) or set(correction) != {"cash_final_mxn"}:
            raise ValueError("Observed cash correction attempts an unauthorized field")
        if observed_at.astimezone(ZoneInfo("America/Mexico_City")).date().isoformat() != row["query_date"]:
            raise ValueError("Cash correction crosses the Mexico City query date; capture a new observation")
        final_cash = amount(correction["cash_final_mxn"])
        if final_cash is None:
            raise ValueError("Observed cash correction requires a final MXN amount")
        row["cash_final_mxn"] = final_cash
    if review.get("observed_supplement"):
        evidence = review.get("supplement_evidence", {})
        observed_at = datetime.fromisoformat(evidence["observed_at"].replace("Z", "+00:00"))
        if (
            review.get("verified") is not True
            or observed_at.tzinfo is None
            or not evidence.get("evidence_url", "").startswith(("https://", "http://"))
            or not re.fullmatch(r"[a-f0-9]{64}", evidence.get("dom_sha256", ""))
        ):
            raise ValueError("Observed supplement lacks verified, timestamped DOM evidence")
        for field, value in review["observed_supplement"].items():
            if field not in {"redemption_cash_mxn", "redemption_carrier_mxn"}:
                raise ValueError("Observed supplement attempts an unauthorized field")
            row[field] = amount(value)
    row["field_review"] = review
    row.setdefault("source_observation_id", row["observation_id"])
    row["observation_id"] = digest(
        {k: v for k, v in row.items() if k not in {"sources", "raw_source_row", "observation_id"}}
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bronze", type=Path, default=Path("data/bronze/fare_quotes"))
    parser.add_argument("--silver", type=Path, default=Path("data/silver/fare_quotes"))
    parser.add_argument("--gold", type=Path, default=Path("data/gold/local_fare_quotes.json"))
    parser.add_argument(
        "--public-out", type=Path, help="Export only contracted aggregate means; no publication"
    )
    args = parser.parse_args()
    if not args.bronze.exists():
        parser.error("Bronze directory missing; capture and read back the source books first")
    payload = rebuild(args.bronze, args.silver, args.gold)
    if args.public_out:
        from src.web_export.fare_averages import export_fare_averages

        export_fare_averages(payload, args.public_out)
    print(json.dumps(dict(counts=payload["counts"], quarantine_count=payload["quarantine_count"])))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
