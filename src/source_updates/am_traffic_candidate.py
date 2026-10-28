"""Offline certification CLI for one selected Aeromexico monthly IR traffic PDF."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pandas as pd

from src.pipeline.offline import block_network
from src.source_updates.am_traffic import ENTRY, parse, pdf_text, validate
from src.source_updates.calendar import local_time
from src.source_updates.catalog import ROOT
from src.source_updates.checks import period_end, require_replay_cutoff, verify_bronze
from src.source_updates.collection import safe_workspace, validate_url, writer
from src.transform.stage6_contracts import validate_table
from src.transform.stage6_dimensions import CURATED_CARRIERS, build_dim_metric, gregorian_easter
from src.transform.stage6_facts import _standard_source
from src.transform.stage9_lineage import (
    LineageSpec,
    add_record_ids,
    build_bridge_record_lineage,
    build_dim_source_artifact,
)
from src.transform.validate_stage9 import validate_lineage_frames

OUTPUTS = (
    "silver/aeromexico_ir_monthly_metrics",
    "gold/fact_carrier_metrics",
    "gold/dim_period",
    "gold/dim_carrier",
    "gold/dim_metric",
    "gold/dim_source_artifact",
    "gold/bridge_record_lineage",
)


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def period_dimension(periods) -> pd.DataFrame:
    rows = []
    for period in sorted(periods):
        end = period_end(period)
        first = end.replace(day=1)
        previous = pd.Period(first, freq="M") - 1
        easter = gregorian_easter(end.year)
        window = [easter + timedelta(days=offset) for offset in range(-7, 2)]
        rows.append(
            {
                "period_id": period,
                "period_type": "month",
                "period_start_date": first,
                "period_end_date": end,
                "year": end.year,
                "quarter": (end.month - 1) // 3 + 1,
                "month": end.month,
                "days_in_period": end.day,
                "is_covid_period": first <= date(2021, 12, 31) and end >= date(2020, 3, 1),
                "prior_period_id": f"{previous.year}M{previous.month:02d}",
                "prior_year_period_id": f"{end.year - 1}M{end.month:02d}",
                "calendar_period_id": period,
                "fiscal_period_id": period,
                "easter_date": easter,
                "easter_quarter": (easter.month - 1) // 3 + 1,
                "easter_days_in_q1": sum(day.month <= 3 for day in window),
                "easter_days_in_q2": sum(4 <= day.month <= 6 for day in window),
            }
        )
    return validate_table("dim_period", pd.DataFrame(rows))


def original(workspace: Path, period: str, collection: str, as_of: str) -> tuple[bytes, dict, str]:
    if not re.fullmatch(r"[a-f0-9]{32}", collection):
        raise ValueError("Expected a preserved collection receipt ID")
    receipt_path = workspace / "receipts" / f"collection-{collection}.json"
    receipt = json.loads(receipt_path.read_text())
    if (
        receipt.get("status") != "collected_unvalidated"
        or receipt.get("run_id") != collection
        or receipt.get("mode") != "collection"
        or receipt.get("activation") != "none"
        or receipt.get("publication") != "not_authorized"
    ):
        raise ValueError("Select one successfully collected monthly IR PDF")
    rows = receipt["items"]
    data = [r for r in rows if r.get("status") == "collected_unvalidated"]
    indexes = [r for r in rows if r.get("status") == "collected_catalog"]
    if (
        len(data) != 1
        or len(indexes) > 1
        or len(rows) != len(data) + len(indexes)
        or len({r["id"] for r in rows}) != len(rows)
        or any(r.get("product") != "am_traffic_ir" for r in rows)
        or any(r.get("source_url") != ENTRY or r.get("response_url") != ENTRY for r in indexes)
    ):
        raise ValueError("Select one IR PDF and at most its official traffic index")
    item = data[0]
    manifest = workspace / "data/bronze/_manifest.jsonl"
    manifest_rows = [json.loads(line) for line in manifest.read_text().splitlines()]
    if len(manifest_rows) != len(rows) or len({r["source_file"] for r in manifest_rows}) != len(rows):
        raise ValueError("Traffic manifest requires unique acquisition records; no duplicate revisions")
    records = verify_bronze(workspace)
    if set(records) != {r.get("source_file") for r in rows} or len(records) != len(rows):
        raise ValueError("Traffic manifest must match the exact selected acquisition items")
    for acquired in rows:
        record = records[acquired["source_file"]]
        path = workspace / "data/bronze" / acquired["source_file"]
        meta = json.loads(path.with_suffix(path.suffix + ".meta.json").read_text())
        if local_time(record["downloaded_at"]) > local_time(as_of):
            raise ValueError("Traffic capture is after the requested cutoff")
        if (
            meta != record
            or any(record.get(k) != acquired.get(k) for k in ("sha256", "source_url", "http_status"))
            or record.get("http_status") != 200
            or record.get("download_method") != "httpx"
            or acquired.get("bytes") != path.stat().st_size
            or not local_time(receipt["started_at"])
            <= local_time(record["downloaded_at"])
            <= local_time(receipt["finished_at"])
            <= local_time(as_of)
        ):
            raise ValueError("Traffic acquisition receipt, source sidecar or chronology differs")
    if any(row["source_system"] != "aeromexico_ir" for row in records.values()):
        raise ValueError("Monthly IR candidate cannot contain other Bronze sources")
    row = records.get(item.get("source_file"))
    if row is None or row["sha256"] != item.get("sha256") or row["source_url"] != item["source_url"]:
        raise ValueError("Traffic receipt differs from the verified Bronze manifest")
    html = row["logical_key"] == "aeromexico_ir|am_traffic_ir_2026M09_6K|2026M09|html"
    if (
        row["source_system"] != "aeromexico_ir"
        or item.get("product") != "am_traffic_ir"
        or not (
            row["logical_key"] == f"aeromexico_ir|am_traffic_ir|{period}|pdf" or html and period == "2026M09"
        )
        or item.get("http_status") != 200
        or item.get("status") != "collected_unvalidated"
    ):
        raise ValueError("Wrong source/product/month or unsuccessful traffic capture")
    validate_url(row["source_url"], ["aeromexico.com"])
    validate_url(item.get("response_url", ""), ["aeromexico.com"])
    if html and (
        row.get("source_url") != "https://ir.aeromexico.com/node/9131/html"
        or item.get("requested_period") != period
    ):
        raise ValueError("Traffic HTML requires its reviewed exact official IR6-K URL")
    if html and item.get("response_url") != row["source_url"]:
        raise ValueError("Traffic HTML response must preserve its official IR6-K identity")
    if local_time(row["downloaded_at"]) > local_time(as_of):
        raise ValueError("Traffic capture is after the requested cutoff")
    path = workspace / "data/bronze" / row["source_file"]
    meta = json.loads(path.with_suffix(path.suffix + ".meta.json").read_text())
    if any(meta.get(key) != row[key] for key in ("sha256", "logical_key", "source_url", "downloaded_at")):
        raise ValueError("Traffic Bronze sidecar differs from its manifest")
    return path.read_bytes(), row, sha(receipt_path)


def frames(workspace: Path, period: str, as_of: str, collection: str) -> tuple[dict, dict]:
    content, provenance, receipt_hash = original(workspace, period, collection, as_of)
    if provenance["logical_key"].endswith("|html"):
        from src.source_updates.am_traffic_html import parse as parse_html

        silver, details = parse_html(content, period, provenance)
    else:
        silver, details = parse(pdf_text(content), period, provenance)
    if date.fromisoformat(details["published_date"]) > min(
        local_time(as_of).date(), local_time(provenance["downloaded_at"]).date()
    ):
        raise ValueError("Traffic report publication is after its capture or requested cutoff")
    validate(silver)
    facts = validate_table(
        "fact_carrier_metrics",
        add_record_ids(
            _standard_source(silver),
            table_name="fact_carrier_metrics",
            natural_key_columns=[
                "carrier_key",
                "period_id",
                "metric_key",
                "segment",
                "source_system",
                "valid_from",
            ],
        ),
    )
    periods = period_dimension(set(silver.period_id))
    carrier = validate_table(
        "dim_carrier",
        pd.DataFrame(
            [
                {
                    "carrier_key": "AEROMEXICO",
                    **CURATED_CARRIERS["AEROMEXICO"],
                    "valid_from": date(1900, 1, 1),
                    "valid_to": None,
                    "is_current": True,
                }
            ]
        ),
    )
    # Arrow persists an empty nullable DATE column as None, rather than pandas NaT.
    carrier["valid_to"] = pd.Series([None], dtype="object")
    metrics = build_dim_metric(set(silver.metric_key))
    lf = metrics.metric_key.eq("load_factor_total")
    metrics.loc[lf, "formula"] = (
        "Reported itinerary-only RPM/ASM (equivalent to RPK/ASK); "
        "not derived from itinerary-plus-charter RPM/ASM"
    )
    metrics.loc[lf, "caveats"] = (
        "Source-reported, unaudited itinerary-only load factor. Other traffic metrics include charter; "
        "their RPM/ASM ratio is a different universe."
    )
    metrics = validate_table(
        "dim_metric", metrics.loc[metrics.metric_key.isin(silver.metric_key)].reset_index(drop=True)
    )
    for column, dimension in (("period_id", periods), ("carrier_key", carrier), ("metric_key", metrics)):
        if not facts[column].isin(dimension[column]).all():
            raise ValueError(f"Traffic candidate foreign key not resolved: {column}")
    artifacts = validate_table(
        "dim_source_artifact",
        build_dim_source_artifact(
            workspace / "data/bronze/_manifest.jsonl",
            catalog_path=ROOT / "config/source_catalog.yaml",
            verify_files=True,
        ),
    )
    identifiers = tuple(artifacts.loc[artifacts.source_file.eq(provenance["source_file"]), "artifact_id"])
    if len(identifiers) != 1:
        raise ValueError("Traffic original does not resolve to exactly one artifact")
    bridge = validate_table(
        "bridge_record_lineage",
        build_bridge_record_lineage(
            [
                LineageSpec(
                    record_id=record,
                    table_name="fact_carrier_metrics",
                    lineage_type="direct_artifact",
                    artifact_ids=identifiers,
                    lineage_note=(
                        "IR monthly/comparative columns only. LF itinerary; "
                        "other metrics itinerary+charter. Unaudited."
                        + (
                            " Native preliminary status is not stated; Gold false is only the existing "
                            "predicate source-marks-preliminary, not confirmation of finality."
                            if details.get("source_format") == "official_IR_HTML_6K_Ex99.4"
                            else ""
                        )
                    ),
                )
                for record in facts.record_id
            ],
            artifacts,
        ),
    )
    lineage = validate_lineage_frames(
        tables={"fact_carrier_metrics": facts}, artifacts=artifacts, bridge=bridge
    )
    outputs = dict(zip(OUTPUTS, (silver, facts, periods, carrier, metrics, artifacts, bridge), strict=True))
    return outputs, {
        **details,
        "lineage": lineage,
        "collection_receipt_sha256": receipt_hash,
        "source_sha256": provenance["sha256"],
        "source_file": provenance["source_file"],
        "latest_validated_period": period,
        "latest_published_period": None,
        "complete_month_certified": True,
        "completeness_basis": (
            "all_12_company_reported_monthly_cells_and_12_prior_year_comparatives_not_operator_census"
        ),
        "scope": "one_IR_month_and_its_reported_prior_year_comparative_not_corporate_family",
        "revisions": {"status": "not_compared_no_prior_candidate"},
        "silver_contract": (
            "established operating-observation grain plus explicit IR product domain; candidate-only table"
        ),
        "quarterly_aggregation": "not_built",
        "activation": "none",
        "publication": "not_authorized",
    }


def run(workspace: Path, period: str, as_of: str, collection: str, *, execute=False, check=False) -> dict:
    workspace = safe_workspace(workspace)
    if (
        not re.fullmatch(r"20\d{2}M(?:0[1-9]|1[0-2])", period)
        or period_end(period) >= local_time(as_of).date()
    ):
        raise ValueError("Select one closed monthly period")
    if not re.fullmatch(r"[a-f0-9]{32}", collection):
        raise ValueError("Expected a preserved collection receipt ID")
    accepted = workspace / "receipts" / f"am-traffic-{period}.json"
    allowed = {workspace / "data" / (name + ".parquet") for name in OUTPUTS}
    for layer in ("silver", "gold"):
        if set((workspace / "data" / layer).glob("*.parquet")) - allowed:
            raise ValueError("Use an isolated monthly IR candidate")
    if not execute and not check:
        return {
            "mode": "dry_run",
            "outputs": list(OUTPUTS),
            "network_requests": 0,
            "paid_requests": 0,
            "input": f"receipts/collection-{collection}.json",
            "activation": "none",
            "publication": "not_authorized",
        }
    if execute and accepted.exists():
        raise ValueError("Accepted traffic candidate is immutable; use a new workspace")
    if not accepted.exists() and any(path.exists() for path in allowed):
        raise ValueError("Existing output without acceptance; use a new workspace, preserve prior files")
    previous = json.loads(accepted.read_text()) if check else None
    if check:
        require_replay_cutoff(previous, as_of)
    with block_network():
        outputs, result = frames(workspace, period, as_of, collection)
    result.update(
        status="checks_passed",
        period=period,
        collection_run_id=collection,
        effective_as_of=as_of,
        checked_at=datetime.now(UTC).isoformat(),
        code_head=subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        code_files={
            p.relative_to(ROOT).as_posix(): sha(p)
            for p in sorted((ROOT / "src/source_updates").glob("am_traffic*.py"))
        },
    )
    if check:
        if (
            previous["collection_run_id"] != collection
            or previous["collection_receipt_sha256"] != result["collection_receipt_sha256"]
        ):
            raise ValueError("Accepted traffic collection receipt changed")
        for name, frame in outputs.items():
            try:
                pd.testing.assert_frame_equal(
                    pd.read_parquet(workspace / "data" / (name + ".parquet")), frame, check_exact=True
                )
            except AssertionError as exc:
                raise ValueError(f"Traffic output differs from its original: {name}") from exc
        result["output_sha256"] = {name: sha(workspace / "data" / (name + ".parquet")) for name in outputs}
        if result["output_sha256"] != previous["output_sha256"]:
            raise ValueError("Accepted traffic artifact hash changed")
        return result
    from src.ingest.stage4_common import write_parquet_atomic

    with writer(workspace):
        if accepted.exists():
            raise ValueError("Accepted traffic candidate is immutable; use a new workspace")
        if any(path.exists() for path in allowed):
            raise ValueError("Existing output without acceptance; use a new workspace, preserve prior files")
        for name, frame in outputs.items():
            write_parquet_atomic(frame, workspace / "data" / (name + ".parquet"))
        result["output_sha256"] = {name: sha(workspace / "data" / (name + ".parquet")) for name in outputs}
        serialized = json.dumps(result, indent=2, ensure_ascii=False) + "\n"
        (workspace / "receipts" / f"am-traffic-{uuid4().hex}.json").write_text(serialized)
        accepted.write_text(serialized)
    return result


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--period", required=True)
    parser.add_argument("--as-of", required=True)
    parser.add_argument("--collection", required=True)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--execute", action="store_true")
    mode.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    try:
        result = run(
            args.workspace, args.period, args.as_of, args.collection, execute=args.execute, check=args.check
        )
    except (ValueError, OSError, KeyError) as exc:
        print(json.dumps({"status": "blocked", "reason": str(exc), "activation": "none"}))
        return 1
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
