"""Materialize OMA's dated MTY–CDG schedule and MTY–MAD route mention."""

from __future__ import annotations

from datetime import date, timedelta
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


SOURCE = PATHS.bronze / "international_routes" / "oma_mty_cdg_route_launch_2026Q2_20260913T143058Z.pdf"
SILVER = PATHS.silver / "international_routes" / "oma_documented_routes.parquet"
GOLD = PATHS.gold / "fact_oma_documented_routes.parquet"
QUALITY = PATHS.quality / "oma_documented_routes.json"
TABLE = "fact_oma_documented_routes"
BRIDGE = "bridge_oma_documented_route_lineage"
VERSION = "oma_documented_routes_v1"


def _scheduled_dates(start: date, end: date, weekdays: tuple[int, ...]) -> list[str]:
    days = []
    day = start
    while day <= end:
        if day.weekday() in weekdays:
            days.append(day.isoformat())
        day += timedelta(days=1)
    return days


def run() -> dict:
    metadata = json.loads(Path(str(SOURCE) + ".meta.json").read_text(encoding="utf-8"))
    source_hash = hashlib.sha256(SOURCE.read_bytes()).hexdigest()
    if source_hash != metadata["sha256"]:
        raise ValueError("OMA Bronze hash differs from metadata")
    with pdfplumber.open(SOURCE) as pdf:
        if len(pdf.pages) != 2:
            raise ValueError("Unexpected OMA report page count")
        intro = pdf.pages[0].extract_text().lower()
        schedule = pdf.pages[1].extract_text().lower()
    if "monterrey" not in intro or "madrid" not in intro or "13 de abril de 2026" not in intro:
        raise ValueError("OMA route and publication date not found")
    if not all(word in schedule for word in ("lunes", "jueves", "sábado", "martes", "viernes", "domingo")):
        raise ValueError("OMA MTY–CDG weekly schedule not found")
    quarter_end = date(2026, 6, 30)
    launch = date(2026, 4, 13)
    outbound = _scheduled_dates(launch, quarter_end, (0, 3, 5))
    inbound = _scheduled_dates(launch, quarter_end, (1, 4, 6))
    silver = pd.DataFrame([
        dict(period_id="2026Q2", origin_iata="MTY", dest_iata="CDG",
             route_status="scheduled_from_dated_release", scheduled_movements=len(outbound),
             scheduled_dates="|".join(outbound), source_page=2,
             source_locator="page:2:weekly-schedule", source_hash=source_hash,
             source_url=metadata["source_url"], parser_version=VERSION),
        dict(period_id="2026Q2", origin_iata="CDG", dest_iata="MTY",
             route_status="scheduled_from_dated_release", scheduled_movements=len(inbound),
             scheduled_dates="|".join(inbound), source_page=2,
             source_locator="page:2:weekly-schedule", source_hash=source_hash,
             source_url=metadata["source_url"], parser_version=VERSION),
        dict(period_id="2026Q2", origin_iata="MTY", dest_iata="MAD",
             route_status="operating_route_mentioned_count_unavailable", scheduled_movements=None,
             scheduled_dates=None, source_page=1,
             source_locator="page:1:existing-MTY-MAD", source_hash=source_hash,
             source_url=metadata["source_url"], parser_version=VERSION),
    ])
    SILVER.parent.mkdir(parents=True, exist_ok=True)
    write_parquet_atomic(silver, SILVER)
    gold = silver.drop(columns=["scheduled_dates"]).copy()
    gold["source_system"] = "oma"
    gold["agent_eligible"] = False
    gold["record_id"] = gold.apply(lambda row: make_record_id(TABLE, {
        "source_hash": source_hash, "period_id": row.period_id,
        "origin_iata": row.origin_iata, "dest_iata": row.dest_iata,
        "parser_version": VERSION,
    }), axis=1)
    artifacts = build_dim_source_artifact()
    matched = artifacts[artifacts.artifact_sha256.eq(source_hash)]
    if len(matched) != 1:
        raise ValueError("OMA original does not resolve to one Bronze artifact")
    artifact_id = str(matched.iloc[0].artifact_id)
    gold["artifact_id"] = artifact_id
    bridge = build_bridge_record_lineage([
        LineageSpec(record_id=row.record_id, table_name=TABLE, lineage_type="derived",
                    artifact_ids=(artifact_id,),
                    lineage_note="Scheduled weekday count or route presence from dated OMA release")
        for row in gold.itertuples(index=False)
    ], artifacts)
    outputs = {TABLE: gold, BRIDGE: bridge,
               "dim_source": build_dim_source(), "dim_source_artifact": artifacts}
    with duckdb.connect(str(PATHS.warehouse)) as connection:
        connection.execute("BEGIN TRANSACTION")
        for name, frame in outputs.items():
            path = PATHS.gold / f"{name}.parquet"
            write_parquet_atomic(frame, path)
            connection.execute(f"CREATE OR REPLACE TABLE {name} AS SELECT * FROM read_parquet(?)", [str(path)])
        connection.execute("COMMIT")
    report = {
        "source": str(SOURCE.relative_to(PATHS.root)).replace("\\", "/"),
        "source_hash": source_hash, "silver_rows": len(silver), "gold_rows": len(gold),
        "lineage_links": len(bridge), "mty_cdg_scheduled_movements": len(outbound) + len(inbound),
        "mty_mad_status": "operating_route_mentioned_count_unavailable",
        "agent_eligible": False,
    }
    QUALITY.parent.mkdir(parents=True, exist_ok=True)
    QUALITY.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report


if __name__ == "__main__":
    print(json.dumps(run(), ensure_ascii=False, indent=2))
