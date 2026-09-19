"""Materialize AICM's Aeromexico slot schedule without calling it flown traffic.

The source is a dated, preserved PDF. Silver keeps one assigned flight/date and
its page locator; Gold aggregates only the domestic MEX legs needed by Vuelos.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
import hashlib
import json
from pathlib import Path

import duckdb
import pandas as pd
import pdfplumber

from src.config import PATHS
from src.ingest.stage4_common import write_parquet_atomic
from src.transform.stage9_lineage import (
    LineageSpec, build_bridge_record_lineage, build_dim_source,
    build_dim_source_artifact, make_record_id,
)


SOURCE = PATHS.bronze / "domestic_routes_research" / "aicm_aeromexico_summer_slots_2026S26_20260913T004629Z.pdf"
SILVER = PATHS.silver / "domestic_slots" / "aicm_amx_assigned_flight_days.parquet"
GOLD = PATHS.gold / "fact_domestic_scheduled_route_movements.parquet"
QUALITY = PATHS.quality / "domestic_slots.json"
QUARTER_START = date(2026, 4, 1)
QUARTER_END = date(2026, 6, 30)
VERSION = "aicm_amx_slots_v1"
TABLE = "fact_domestic_scheduled_route_movements"


def _dates(start: date, end: date, frequency: str):
    if len(frequency) != 7:
        raise ValueError(f"Unexpected frequency: {frequency!r}")
    day = start
    while day <= end:
        if frequency[day.weekday()] == str(day.weekday() + 1):
            yield day
        day += timedelta(days=1)


def run() -> dict:
    content = SOURCE.read_bytes()
    metadata = json.loads(Path(str(SOURCE) + ".meta.json").read_text(encoding="utf-8"))
    source_hash = hashlib.sha256(content).hexdigest()
    if source_hash != metadata["sha256"]:
        raise ValueError("AICM Bronze hash differs from metadata")
    with duckdb.connect(str(PATHS.warehouse), read_only=True) as connection:
        mexican_airports = {
            item[0] for item in connection.execute(
                "SELECT airport_iata FROM dim_airport WHERE country = 'MX'"
            ).fetchall()
        }
    excluded_codes: set[str] = set()
    records: list[dict] = []
    source_rows = 0
    with pdfplumber.open(SOURCE) as pdf:
        for page_number, page in enumerate(pdf.pages, start=1):
            for table_number, table in enumerate(page.extract_tables(), start=1):
                for row_number, row in enumerate(table, start=1):
                    if row[0] not in {"A", "D"}:
                        continue
                    source_rows += 1
                    movement = row[0]
                    counterpart = str(row[7] if movement == "A" else row[9]).strip()
                    if counterpart not in mexican_airports:
                        if len(counterpart) == 3:
                            excluded_codes.add(counterpart)
                        continue
                    origin = counterpart if movement == "A" else "MEX"
                    destination = "MEX" if movement == "A" else counterpart
                    if origin == destination:
                        continue
                    start = datetime.strptime(row[10], "%d/%m/%Y").date()
                    end = datetime.strptime(row[11], "%d/%m/%Y").date()
                    frequency = str(row[12])
                    days = list(_dates(start, end, frequency))
                    if len(days) != int(row[13]):
                        raise ValueError(f"Page {page_number}, row {row_number}: operation count mismatch")
                    for day in days:
                        if QUARTER_START <= day <= QUARTER_END:
                            records.append({
                                "flight_date": str(day),
                                "period_id": f"{day.year}M{day.month:02d}",
                                "origin_iata": origin,
                                "dest_iata": destination,
                                "flight_number": str(row[1]).strip(),
                                "flight_suffix": str(row[2] or "").strip(),
                                "assigned_time_utc": str(row[5]).strip(),
                                "equipment": str(row[4]).strip(),
                                "source_page": page_number,
                                "source_locator": f"page:{page_number}:table:{table_number}:row:{row_number}",
                                "source_hash": source_hash,
                                "source_url": metadata["source_url"],
                                "downloaded_at": metadata["downloaded_at"],
                                "parser_version": VERSION,
                            })
    frame = pd.DataFrame.from_records(records)
    if frame.empty:
        raise ValueError("No AICM domestic flight days in the quarter")
    # The source distinguishes e.g. AM734 and AM734-Z at different UTC times.
    # Deduplicating on the bare number would discard valid separate assignments.
    key = ["flight_date", "origin_iata", "dest_iata", "flight_number", "flight_suffix", "assigned_time_utc"]
    duplicates = int(frame.duplicated(key).sum())
    # A PDF may repeat the same flight/date under overlapping assigned slots.
    frame = frame.drop_duplicates(key, keep="first").sort_values(key).reset_index(drop=True)
    if frame[key].duplicated().any():
        raise ValueError("Duplicate assigned flight-day after resolution")
    # Preserve excluded codes for inspection; most are international airports.
    SILVER.parent.mkdir(parents=True, exist_ok=True)
    write_parquet_atomic(frame, SILVER)
    silver = pd.read_parquet(SILVER)
    gold = silver.groupby(["period_id", "origin_iata", "dest_iata"], as_index=False).agg(
        scheduled_movements=("flight_number", "size"),
        source_pages=("source_page", lambda pages: ",".join(map(str, sorted(set(pages))))),
    )
    gold["carrier_code"] = "AM"
    gold["source_system"] = "aicm"
    gold["observation_status"] = "assigned_slot_not_flown"
    gold["source_hash"] = source_hash
    gold["source_url"] = metadata["source_url"]
    gold["downloaded_at"] = metadata["downloaded_at"]
    gold["parser_version"] = VERSION
    gold["record_id"] = gold.apply(lambda row: make_record_id(TABLE, {
        "source_hash": source_hash, "period_id": row.period_id,
        "origin_iata": row.origin_iata, "dest_iata": row.dest_iata,
        "parser_version": VERSION,
    }), axis=1)
    artifacts = build_dim_source_artifact()
    matched = artifacts[artifacts.artifact_sha256.eq(source_hash)]
    if len(matched) != 1:
        raise ValueError("AICM original does not resolve to one Bronze artifact")
    artifact_id = str(matched.iloc[0].artifact_id)
    gold["artifact_id"] = artifact_id
    bridge = build_bridge_record_lineage([
        LineageSpec(
            record_id=row.record_id, table_name=TABLE, lineage_type="derived",
            artifact_ids=(artifact_id,),
            lineage_note="Monthly count of assigned flight-date slots; not flown traffic",
        )
        for row in gold.itertuples(index=False)
    ], artifacts)
    if int(gold.scheduled_movements.sum()) != len(silver):
        raise ValueError("Gold movements do not reconcile with Silver")
    outputs = {
        TABLE: gold,
        "bridge_domestic_slot_lineage": bridge,
        "dim_source": build_dim_source(),
        "dim_source_artifact": artifacts,
    }
    with duckdb.connect(str(PATHS.warehouse)) as connection:
        connection.execute("BEGIN TRANSACTION")
        for name, frame_out in outputs.items():
            path = PATHS.gold / f"{name}.parquet"
            write_parquet_atomic(frame_out, path)
            connection.execute(
                f"CREATE OR REPLACE TABLE {name} AS SELECT * FROM read_parquet(?)",
                [str(path)],
            )
        connection.execute("COMMIT")
    report = {
        "source": str(SOURCE.relative_to(PATHS.root)).replace("\\", "/"),
        "source_hash": source_hash,
        "source_rows": source_rows,
        "domestic_flight_days": len(records),
        "duplicate_flight_days_removed": duplicates,
        "silver_flight_days": len(silver),
        "gold_month_route_directions": len(gold),
        "lineage_links": len(bridge),
        "routes": len({tuple(sorted((r.origin_iata, r.dest_iata))) for r in gold.itertuples()}),
        "excluded_non_mx_or_unmapped_codes": sorted(excluded_codes),
        "periods": sorted(gold.period_id.unique().tolist()),
        "agent_eligible": False,
        "meaning": "Assigned AICM slots for AM-numbered flights, not verified performed flights or passengers",
    }
    QUALITY.parent.mkdir(parents=True, exist_ok=True)
    QUALITY.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report


if __name__ == "__main__":
    print(json.dumps(run(), ensure_ascii=False, indent=2))
