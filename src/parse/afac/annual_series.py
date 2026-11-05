"""Persist the explicitly selected native annual AFAC series as normal Silver.

The selection file describes physical inputs, not publication authority. Its
absence is an error; this entry point never falls back to a June PDF edition.
"""

import json
import re
from datetime import datetime

import polars as pl

from src.config import PATHS
from src.parse.afac.market_scope import TOTAL_FORMULA, TOTAL_KEY, carrier_identity, market_cells
from src.parse.afac.monthly_stats import (
    MONTH_NAMES,
    PARSER_VERSION,
    _frame,
    _load_crosswalk,
    _metadata,
    _month_dates,
    _normalize,
    _rows,
    parse_annual_passenger_workbook,
)
from src.parse.sec.common import write_parquet_atomic

INPUTS_NAME = "afac_native_annual_inputs.json"


def native_metadata(path):
    from src.source_updates.retained import public_original

    metadata = _metadata(path)
    public_original(metadata)
    if (
        metadata["source_system"] != "afac"
        or metadata["http_status"] != 200
        or metadata["bytes"] != path.stat().st_size
    ):
        raise ValueError("Native AFAC workbook requires its successful official capture identity")
    return metadata


def annual_records(path, year, through, crosswalk):
    metadata = native_metadata(path)
    from src.source_updates.calendar import local_time

    if _month_dates(year, through)[1] >= local_time(metadata["downloaded_at"]).date():
        raise ValueError("Native AFAC observation month was not closed before capture")
    facts, checks = parse_annual_passenger_workbook(path, year)
    _, receipt = market_cells(facts, checks, year, through, crosswalk)
    file = path.relative_to(PATHS.bronze).as_posix()
    records = []
    estimates = _estimates(path, year, {row["source_sheet"] for row in facts})
    # Preserve raw carrier and country scope for totals, mapping and lineage.
    for raw in [row for row in facts if int(row["month"]) <= through]:
        key, iata = carrier_identity(raw, crosswalk)
        row = _record(raw, key, iata, file, metadata)
        notes = [
            note
            for sheet, name, months, note in estimates
            if sheet == raw["source_sheet"]
            and name in _normalize(raw["source_carrier_name"])
            and raw["month"] in months
        ]
        row.update(is_estimated=bool(notes), footnote_text=" | ".join(notes) or None)
        records.append(row)
    selected_checks = [row for row in checks if int(row["period_id"][-2:]) <= through]
    for check in selected_checks:
        if check["is_domestic_carrier"] is not True:
            continue
        raw = dict(
            year=year,
            month=int(check["period_id"][-2:]),
            source_carrier_name=TOTAL_KEY,
            is_domestic_carrier=True,
            service_type=check["service_type"],
            market=check["market"],
            value=check["expected"],
            source_row_number=check["total_row_number"],
        )
        row = _record(raw, TOTAL_KEY, None, file, metadata)
        row["is_estimated"] = any(
            record["is_estimated"]
            for record in records
            if record["period_id"] == check["period_id"]
            and record["service_type"] == check["service_type"]
            and record["market"] == check["market"]
            and record["is_domestic_carrier"] is True
        )
        row["footnote_text"] = TOTAL_FORMULA
        records.append(row)
    quality = [
        {
            **row,
            "source_file": file,
            "source_hash": metadata["sha256"],
            "check_scope": "annual_workbook_total",
            "passed": row["difference"] == 0,
        }
        for row in selected_checks
    ]
    return records, quality, {**receipt, "source_file": file, "source_sha256": metadata["sha256"]}


def _estimates(path, year, sheets):
    rules = []
    for sheet in sheets:
        rows = _rows(path, sheet)
        if year >= 2019 and rows[0][13] != year:
            raise ValueError("AFAC annual native sheet year differs from selected year")
        for row in rows:
            text = str(row[0] or "")
            if "Datos estimados" not in text:
                continue
            match = re.match(r"^\*+ Datos estimados (?:de (.+?) para|para (.+?) en) (.+?) (20\d{2})\.", text)
            if not match or int(match[4]) != year:
                raise ValueError("Unsupported AFAC native estimated-cell footnote")
            months = {_normalize(month) for month in match[3].split(" y ")}
            if not months <= set(MONTH_NAMES):
                raise ValueError("Unsupported AFAC native estimated-cell month")
            rules.append((sheet, _normalize(match[1] or match[2]), {MONTH_NAMES[m] for m in months}, text))
    return rules


def _record(raw, key, iata, file, metadata):
    year, month = int(raw["year"]), int(raw["month"])
    start, end = _month_dates(year, month)
    return dict(
        period_id=f"{year}M{month:02d}",
        period_type="month",
        period_start_date=start,
        period_end_date=end,
        carrier_key=key,
        source_carrier_name=raw["source_carrier_name"],
        iata_code=iata,
        is_domestic_carrier=raw["is_domestic_carrier"],
        service_type=raw["service_type"],
        market=raw["market"],
        metric_key="passengers",
        value=raw["value"],
        unit="passengers",
        is_preliminary=bool(metadata.get("is_preliminary", False)),
        is_estimated=False,
        footnote_text=None,
        source_system="afac",
        source_file=file,
        source_hash=metadata["sha256"],
        ingested_at=metadata["downloaded_at"],
        parser_version=PARSER_VERSION,
        source_row_number=raw["source_row_number"],
        source_region=None,
        source_row_count=1,
        source_family="native_annual_reconciled_v2",
    )


def run():
    path = PATHS.data / INPUTS_NAME
    if not path.is_file():
        raise FileNotFoundError(f"Native AFAC annual input selection is required: {path}; no legacy fallback")
    selection = json.loads(path.read_bytes())
    if (
        set(selection) != {"schema_version", "observations"}
        or selection["schema_version"] != "afac_native_annual_inputs_v1"
    ):
        raise ValueError("Unsupported native AFAC annual input selection")
    observations = selection["observations"]
    if not observations:
        raise ValueError("Native AFAC annual observations are missing")
    seen = set()
    records, quality, receipts = [], [], []
    for item in sorted(observations, key=lambda row: row["year"]):
        if set(item) != {"year", "through", "source_file", "sha256"} or item["year"] in seen:
            raise ValueError("Native AFAC selection requires one exact workbook per year")
        seen.add(item["year"])
        source = (PATHS.bronze / item["source_file"]).resolve()
        source.relative_to(PATHS.bronze.resolve())
        metadata = _metadata(source)
        if metadata["sha256"] != item["sha256"]:
            raise ValueError("Native AFAC selected SHA differs from capture metadata")
        datetime.fromisoformat(metadata["downloaded_at"])  # Validate capture time before persisting.
        rows, checks, receipt = annual_records(source, item["year"], item["through"], _load_crosswalk())
        records.extend(rows)
        quality.extend(checks)
        receipts.append(receipt)
    if seen != set(range(min(seen), max(seen) + 1)):
        raise ValueError("Native AFAC annual series has missing years")
    if any(item["through"] != 12 for item in observations if item["year"] < max(seen)):
        raise ValueError("Historical AFAC annual coverage must include all twelve months")
    frame = _frame(records)
    checks = pl.DataFrame(quality, infer_schema_length=None)
    if checks.filter(~pl.col("passed")).height:
        raise ValueError("Native AFAC source totals do not reconcile")
    validation = validate_frames(frame, checks, selection)
    write_parquet_atomic(frame, PATHS.silver / "afac_monthly_stats.parquet")
    write_parquet_atomic(checks, PATHS.quality / "afac_total_checks.parquet")
    return dict(
        network_used=False,
        silver_rows=frame.height,
        period_min=frame["period_id"].min(),
        period_max=frame["period_id"].max(),
        native_annual_inputs=receipts,
        total_checks=checks.height,
        failed_total_checks=0,
        native_validation=validation,
    )


def validate_frames(facts, checks, selection):
    """Check the selected native series without a fixed month or invented SEC match."""
    expected = {
        f"{row['year']}M{month:02d}"
        for row in selection["observations"]
        for month in range(1, row["through"] + 1)
    }
    from src.transform.silver_contracts import validate_silver_table

    validate_silver_table("afac_monthly_stats", facts.to_pandas())
    grain = [
        "period_id",
        "carrier_key",
        "source_carrier_name",
        "is_domestic_carrier",
        "market",
        "service_type",
        "metric_key",
    ]
    if (
        set(facts["period_id"]) != expected
        or facts.group_by(grain).len().filter(pl.col("len") > 1).height
        or facts.filter(pl.col("value").is_null() | (pl.col("value") < 0)).height
        or checks.filter(~pl.col("passed") | (pl.col("difference") != 0)).height
    ):
        raise ValueError("Native AFAC coverage, grain, values or original TOTAL checks failed")
    margins = facts.filter(pl.col("carrier_key") == TOTAL_KEY)
    if margins.height != len(expected) * 4:
        raise ValueError("Native AFAC must preserve four literal Mexican TOTAL records per month")
    keys = ["period_id", "service_type", "market", "source_file"]
    domestic = facts.filter((pl.col("carrier_key") != TOTAL_KEY) & pl.col("is_domestic_carrier"))
    sums = domestic.group_by(keys).agg(pl.col("value").sum().alias("sum_value"))
    compared = margins.join(sums, on=keys, how="full", coalesce=True)
    if (
        compared.height != margins.height
        or compared.filter(
            pl.col("sum_value").is_null()
            | pl.col("value").is_null()
            | (pl.col("value") != pl.col("sum_value"))
        ).height
    ):
        raise ValueError("Native AFAC Mexican TOTAL includes foreign rows or omits an operator")
    return dict(
        native_annual_series=True,
        period_count=len(expected),
        period_min=min(expected),
        period_max=max(expected),
        mexican_service_totals=margins.height,
        failed_total_checks=0,
        duplicate_natural_keys=0,
        sec_reconciliation="not_used_as_a_replacement_for_native_scope_reconciliation",
    )


def validate():
    return validate_frames(
        pl.read_parquet(PATHS.silver / "afac_monthly_stats.parquet"),
        pl.read_parquet(PATHS.quality / "afac_total_checks.parquet"),
        json.loads((PATHS.data / INPUTS_NAME).read_bytes()),
    )
