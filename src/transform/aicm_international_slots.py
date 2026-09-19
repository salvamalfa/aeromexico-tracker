"""Preserve and materialize international AM slots from the AICM summer PDF.

The PDF identifies a flight number and the airport opposite MEX. Its assigned
operations are a schedule, not a record that every flight took place.
"""

from __future__ import annotations

from datetime import date, datetime
import hashlib
import json
from pathlib import Path

import duckdb
import pandas as pd
import pdfplumber

from src.config import PATHS
from src.ingest.stage4_common import write_parquet_atomic
from src.transform.domestic_slots import SOURCE, QUARTER_START, QUARTER_END, _dates
from src.transform.stage9_lineage import (
    LineageSpec, build_bridge_record_lineage, build_dim_source,
    build_dim_source_artifact, make_record_id,
)


SILVER = PATHS.silver / "international_slots" / "aicm_amx_assigned_flight_days.parquet"
GOLD = PATHS.gold / "fact_aicm_international_scheduled_route_movements.parquet"
QUALITY = PATHS.quality / "aicm_international_slots.json"
VERSION = "aicm_amx_international_slots_v1"
TABLE = "fact_aicm_international_scheduled_route_movements"
BRIDGE = "bridge_aicm_international_slot_lineage"


def run() -> dict:
    metadata = json.loads(Path(str(SOURCE) + ".meta.json").read_text(encoding="utf-8"))
    source_hash = hashlib.sha256(SOURCE.read_bytes()).hexdigest()
    if source_hash != metadata["sha256"]:
        raise ValueError("AICM Bronze hash differs from metadata")
    with duckdb.connect(str(PATHS.warehouse), read_only=True) as connection:
        airport_country = dict(connection.execute(
            "SELECT airport_iata, country FROM dim_airport"
        ).fetchall())
    records = []
    unrecognized = set()
    with pdfplumber.open(SOURCE) as pdf:
        for page_number, page in enumerate(pdf.pages, start=1):
            for table_number, table in enumerate(page.extract_tables(), start=1):
                for row_number, row in enumerate(table, start=1):
                    if row[0] not in {"A", "D"}:
                        continue
                    movement = row[0]
                    counterpart = str(row[7] if movement == "A" else row[9]).strip()
                    if counterpart not in airport_country:
                        unrecognized.add(counterpart)
                        continue
                    if airport_country[counterpart] == "MX":
                        continue
                    origin = counterpart if movement == "A" else "MEX"
                    destination = "MEX" if movement == "A" else counterpart
                    start = datetime.strptime(row[10], "%d/%m/%Y").date()
                    end = datetime.strptime(row[11], "%d/%m/%Y").date()
                    frequency = str(row[12])
                    days = list(_dates(start, end, frequency))
                    if len(days) != int(row[13]):
                        raise ValueError(f"Page {page_number}, row {row_number}: count mismatch")
                    for day in days:
                        if QUARTER_START <= day <= QUARTER_END:
                            records.append({
                                "flight_date": str(day),
                                "period_id": f"{day.year}M{day.month:02d}",
                                "origin_iata": origin, "dest_iata": destination,
                                "counterpart_country": airport_country[counterpart],
                                "flight_number": str(row[1]).strip(),
                                "flight_suffix": str(row[2] or "").strip(),
                                "assigned_time_utc": str(row[5]).strip(),
                                "source_page": page_number,
                                "source_locator": f"page:{page_number}:table:{table_number}:row:{row_number}",
                                "source_hash": source_hash,
                                "source_url": metadata["source_url"],
                                "downloaded_at": metadata["downloaded_at"],
                                "parser_version": VERSION,
                            })
    if unrecognized:
        raise ValueError(f"Unmapped AICM international airports: {sorted(unrecognized)}")
    silver = pd.DataFrame.from_records(records)
    if silver.empty:
        raise ValueError("No AICM international flight days in the quarter")
    key = ["flight_date", "origin_iata", "dest_iata", "flight_number", "flight_suffix", "assigned_time_utc"]
    duplicates = int(silver.duplicated(key).sum())
    silver = silver.drop_duplicates(key).sort_values(key).reset_index(drop=True)
    SILVER.parent.mkdir(parents=True, exist_ok=True)
    write_parquet_atomic(silver, SILVER)
    gold = silver.groupby(["period_id", "origin_iata", "dest_iata", "counterpart_country"], as_index=False).agg(
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
            lineage_note="Monthly assigned AM international slots at MEX; flight performance unverified",
        ) for row in gold.itertuples(index=False)
    ], artifacts)
    if int(gold.scheduled_movements.sum()) != len(silver):
        raise ValueError("Gold international movements do not reconcile with Silver")
    outputs = {
        TABLE: gold, BRIDGE: bridge,
        "dim_source": build_dim_source(), "dim_source_artifact": artifacts,
    }
    with duckdb.connect(str(PATHS.warehouse)) as connection:
        connection.execute("BEGIN TRANSACTION")
        for name, frame in outputs.items():
            path = PATHS.gold / f"{name}.parquet"
            write_parquet_atomic(frame, path)
            connection.execute(f"CREATE OR REPLACE TABLE {name} AS SELECT * FROM read_parquet(?)", [str(path)])
        connection.execute("COMMIT")
    report = {
        "source": str(SOURCE.relative_to(PATHS.root)).replace("\\", "/"),
        "source_hash": source_hash,
        "international_flight_days": len(records),
        "duplicate_flight_days_removed": duplicates,
        "silver_flight_days": len(silver),
        "gold_month_route_directions": len(gold),
        "lineage_links": len(bridge),
        "routes": len({tuple(sorted((r.origin_iata, r.dest_iata))) for r in gold.itertuples()}),
        "country_movements": {str(k): int(v) for k, v in gold.groupby("counterpart_country").scheduled_movements.sum().items()},
        "periods": sorted(gold.period_id.unique().tolist()),
        "agent_eligible": False,
        "meaning": "Assigned AM international slots at MEX; not verified performed flights",
    }
    QUALITY.parent.mkdir(parents=True, exist_ok=True)
    QUALITY.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report


if __name__ == "__main__":
    print(json.dumps(run(), ensure_ascii=False, indent=2))
