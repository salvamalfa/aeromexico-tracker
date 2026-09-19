"""Parse official Aeromexico quarterly releases into typed Silver metrics."""

from __future__ import annotations

from calendar import monthrange
from datetime import UTC, datetime
import hashlib
import json
import logging
from pathlib import Path
import re
from typing import Any

import polars as pl
from pypdf import PdfReader

from src.config import PATHS
from src.parse.sec.common import write_parquet_atomic


PARSER_VERSION = "aeromexico_ir_v1.0.0"
OUTPUT = PATHS.silver / "aeromexico_ir_quarterly_metrics.parquet"
MILES_TO_KM = 1.609344
FIRST_HISTORY_PERIOD = "2021Q1"
LAST_HISTORY_PERIOD = "2024Q2"
REPORTED_FX = {
    "2021Q1": 20.28,
    "2021Q2": 20.17,
    "2021Q3": 19.98,
    "2021Q4": 20.73,
    "2022Q1": 20.54,
    "2022Q2": 20.04,
    "2022Q3": 20.26,
}


def _manifest_records() -> list[dict[str, Any]]:
    manifest = PATHS.bronze / "_manifest.jsonl"
    records: list[dict[str, Any]] = []
    for line in manifest.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        record = json.loads(line)
        period = str(record.get("logical_key", "")).split("|")
        if record.get("source_system") != "aeromexico_ir" or len(period) < 3:
            continue
        period_id = period[2]
        if FIRST_HISTORY_PERIOD <= period_id <= LAST_HISTORY_PERIOD:
            records.append({**record, "period_id": period_id})
    latest: dict[str, dict[str, Any]] = {}
    for record in records:
        current = latest.get(record["period_id"])
        if current is None or int(record.get("logical_version", 1)) > int(current.get("logical_version", 1)):
            latest[record["period_id"]] = record
    return [latest[key] for key in sorted(latest)]


def _verified_bytes(record: dict[str, Any]) -> bytes:
    path = PATHS.bronze / str(record["source_file"])
    content = path.read_bytes()
    digest = hashlib.sha256(content).hexdigest()
    if digest != record["sha256"]:
        raise ValueError(f"Bronze hash mismatch for {path}")
    return content


def _pdf_text(record: dict[str, Any]) -> str:
    import io

    logging.getLogger("pypdf").setLevel(logging.ERROR)
    reader = PdfReader(io.BytesIO(_verified_bytes(record)))
    return "\n".join(page.extract_text(extraction_mode="layout") or "" for page in reader.pages)


def _first_number(text: str, patterns: tuple[str, ...], *, multiline: bool = False) -> tuple[float, str]:
    flags = re.IGNORECASE | (re.DOTALL if multiline else 0)
    for pattern in patterns:
        match = re.search(pattern, text, flags)
        if match is None:
            continue
        raw = match.group("value").replace(",", "")
        return float(raw), match.group(0).splitlines()[0].strip()
    raise ValueError(f"Unable to extract any of: {patterns}")


def _period_dates(period_id: str) -> tuple[str, str]:
    year, quarter = int(period_id[:4]), int(period_id[-1])
    start_month = 3 * quarter - 2
    end_month = 3 * quarter
    return (
        f"{year:04d}-{start_month:02d}-01",
        f"{year:04d}-{end_month:02d}-{monthrange(year, end_month)[1]:02d}",
    )


def _row(
    record: dict[str, Any],
    *,
    metric_key: str,
    label: str,
    value_raw: float,
    unit_raw: str,
    scale_multiplier: float,
    unit_normalized: str,
    extraction_method: str = "pdf_table",
    confidence: float = 0.99,
) -> dict[str, Any]:
    period_id = record["period_id"]
    start, end = _period_dates(period_id)
    return {
        "carrier_key": "AEROMEXICO",
        "accession_number": f"IR-{period_id}",
        "period_id": period_id,
        "period_type": "quarter",
        "period_start_date": start,
        "period_end_date": end,
        "metric_key": metric_key,
        "metric_label_raw": label,
        "segment": "total",
        "value_raw": value_raw,
        "unit_raw": unit_raw,
        "scale_multiplier": scale_multiplier,
        "value_normalized": value_raw * scale_multiplier,
        "unit_normalized": unit_normalized,
        "is_preliminary": False,
        "is_yoy_comparison": False,
        "extraction_method": extraction_method,
        "extraction_confidence": confidence,
        "source_system": "aeromexico_ir",
        "source_file": record["source_file"],
        "source_hash": record["sha256"],
        "ingested_at": datetime.fromisoformat(record["downloaded_at"]).astimezone(UTC),
        "parser_version": PARSER_VERSION,
        "calendar_period_id": period_id,
        "fiscal_period_id": period_id,
    }


def parse_report(record: dict[str, Any]) -> list[dict[str, Any]]:
    text = _pdf_text(record)
    period_id = record["period_id"]
    ask, ask_label = _first_number(text, (r"ASKs totales \(millones\)\s+(?P<value>[\d,]+)",))
    passengers, passengers_label = _first_number(text, (r"Pasajeros \((?:miles|'000)\)\s+(?P<value>[\d,]+)",))
    load, load_label = _first_number(
        text,
        (
            r"Factor de ocupaci.n (?:\(itinerario %\)|itinerario \(%\))\s+(?P<value>\d+(?:\.\d+)?)%?",
            r"Factor de ocupaci.n\s+(?P<value>\d+(?:\.\d+)?)%",
        ),
        multiline=True,
    )
    cask, cask_label = _first_number(
        text,
        (
            r"Costo total / ASK \(centavos de USD\)\s+(?P<value>\d+(?:\.\d+)?)",
            r"Costo total / ASK \(USD\)\*{0,4}\s+(?P<value>\d+(?:\.\d+)?)",
        ),
    )
    if period_id in REPORTED_FX:
        rask_mxn, rask_label = _first_number(
            text, (r"Ingreso total / ASK \(pesos\)\s+(?P<value>\d+(?:\.\d+)?)",)
        )
        rask = rask_mxn / REPORTED_FX[period_id] * 100
        rask_method = "pdf_table+reported_fx"
        rask_confidence = 0.98
    else:
        rask, rask_label = _first_number(
            text, (r"Ingreso total / ASK \(centavos de USD\)\s+(?P<value>\d+(?:\.\d+)?)",)
        )
        rask_method = "pdf_table"
        rask_confidence = 0.99

    cask_scale = 100 * MILES_TO_KM if cask < 1 else MILES_TO_KM
    rows = [
        _row(record, metric_key="asm_total", label=ask_label, value_raw=ask, unit_raw="million ASK-km", scale_multiplier=1_000_000 / MILES_TO_KM, unit_normalized="miles"),
        _row(record, metric_key="passengers", label=passengers_label, value_raw=passengers, unit_raw="thousand passengers", scale_multiplier=1_000, unit_normalized="count"),
        _row(record, metric_key="load_factor_total", label=load_label, value_raw=load, unit_raw="percent", scale_multiplier=0.01, unit_normalized="fraction"),
        _row(record, metric_key="trasm", label=rask_label, value_raw=rask, unit_raw="USD cents per ASK-km", scale_multiplier=MILES_TO_KM, unit_normalized="usd_cents_per_mile", extraction_method=rask_method, confidence=rask_confidence),
        _row(record, metric_key="casm", label=cask_label, value_raw=cask, unit_raw="USD per ASK-km" if cask < 1 else "USD cents per ASK-km", scale_multiplier=cask_scale, unit_normalized="usd_cents_per_mile"),
    ]
    return rows


def run() -> dict[str, Any]:
    records = _manifest_records()
    expected = [f"{year}Q{quarter}" for year in range(2021, 2025) for quarter in range(1, 5) if f"{year}Q{quarter}" <= LAST_HISTORY_PERIOD]
    available = [record["period_id"] for record in records]
    missing = sorted(set(expected) - set(available))
    if missing:
        raise ValueError(f"Missing official Aeromexico IR reports in Bronze: {missing}")
    rows = [row for record in records for row in parse_report(record)]
    frame = pl.DataFrame(rows).sort(["period_id", "metric_key"])
    duplicates = frame.group_by(["source_file", "carrier_key", "accession_number", "period_id", "metric_key", "segment"]).len().filter(pl.col("len") > 1)
    if duplicates.height:
        raise ValueError("Aeromexico IR Silver grain is not unique")
    write_parquet_atomic(frame, OUTPUT)
    return {"rows": frame.height, "periods": available, "period_min": min(available), "period_max": max(available), "output": OUTPUT.as_posix()}


if __name__ == "__main__":
    print(json.dumps(run(), indent=2, ensure_ascii=False, default=str))
