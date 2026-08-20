"""Cross-check SEC API facts, quarterly releases, and monthly traffic reports."""

from __future__ import annotations

from datetime import UTC, datetime
import json
from pathlib import Path
import re
from typing import Any

import polars as pl

from src.common.quality import log_issue
from src.config import PATHS
from src.parse.sec.common import read_bronze_verified, write_parquet_atomic


PARSER_VERSION = "sec_crosscheck_v1.0.0"


def _comparison(
    *,
    metric_key: str,
    period_id: str,
    source_a: str,
    value_a: float,
    source_b: str,
    value_b: float,
    source_file_a: str,
    source_file_b: str,
    flagged_at: datetime,
    tolerance_pct: float = 0.01,
) -> dict[str, object]:
    abs_diff = abs(value_a - value_b)
    pct_diff = abs_diff / abs(value_a) if value_a else (0.0 if value_b == 0 else None)
    return {
        "metric_key": metric_key,
        "period_id": period_id,
        "source_a": source_a,
        "value_a": value_a,
        "source_b": source_b,
        "value_b": value_b,
        "abs_diff": abs_diff,
        "pct_diff": pct_diff,
        "is_material": pct_diff is None or pct_diff > tolerance_pct,
        "tolerance_pct": tolerance_pct,
        "source_file_a": source_file_a,
        "source_file_b": source_file_b,
        "flagged_at": flagged_at,
        "parser_version": PARSER_VERSION,
    }


def _quarterly_monthly_crosschecks(operating: pl.DataFrame) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    quarters = operating.filter(pl.col("period_type") == "quarter")
    months = operating.filter(pl.col("period_type") == "month")
    for period_id in quarters["period_id"].unique().sort().to_list():
        year = int(period_id[:4])
        quarter = int(period_id[-1])
        month_ids = [f"{year}M{month:02d}" for month in range((quarter - 1) * 3 + 1, quarter * 3 + 1)]
        month_slice = months.filter(pl.col("period_id").is_in(month_ids) & (pl.col("segment") == "total"))
        if month_slice["period_id"].n_unique() != 3:
            continue
        quarter_slice = quarters.filter(pl.col("period_id") == period_id)
        for metric_key in ("asm_total", "rpm_total", "passengers"):
            quarter_rows = quarter_slice.filter(pl.col("metric_key") == metric_key)
            month_rows = month_slice.filter(pl.col("metric_key") == metric_key)
            if quarter_rows.height != 1 or month_rows.height != 3:
                continue
            q = quarter_rows.row(0, named=True)
            monthly_value = float(month_rows["value_normalized"].sum())
            records.append(
                _comparison(
                    metric_key=metric_key,
                    period_id=period_id,
                    source_a="quarterly_earnings_release",
                    value_a=float(q["value_normalized"]),
                    source_b="monthly_traffic_reports_sum",
                    value_b=monthly_value,
                    source_file_a=str(q["source_file"]),
                    source_file_b=";".join(sorted(month_rows["source_file"].to_list())),
                    flagged_at=max(q["ingested_at"], month_rows["ingested_at"].max()),
                )
            )
        q_lf = quarter_slice.filter(pl.col("metric_key") == "load_factor_total")
        monthly_asm = month_slice.filter(pl.col("metric_key") == "asm_total")
        monthly_rpm = month_slice.filter(pl.col("metric_key") == "rpm_total")
        if q_lf.height == 1 and monthly_asm.height == 3 and monthly_rpm.height == 3:
            q = q_lf.row(0, named=True)
            derived_lf = float(monthly_rpm["value_normalized"].sum()) / float(
                monthly_asm["value_normalized"].sum()
            )
            records.append(
                _comparison(
                    metric_key="load_factor_total",
                    period_id=period_id,
                    source_a="quarterly_earnings_release",
                    value_a=float(q["value_normalized"]),
                    source_b="monthly_traffic_reports_derived",
                    value_b=derived_lf,
                    source_file_a=str(q["source_file"]),
                    source_file_b=";".join(sorted(monthly_rpm["source_file"].to_list())),
                    flagged_at=max(q["ingested_at"], monthly_rpm["ingested_at"].max()),
                )
            )
    return records


def _companyfacts_document_crosscheck() -> dict[str, object]:
    companyfacts_candidates = [
        path
        for path in (
            list((PATHS.bronze / "sec").glob("sec_companyfacts_current_*.json"))
            + list((PATHS.bronze / "sec" / "companyfacts").glob("*.json"))
        )
        if not path.name.endswith(".meta.json")
    ]
    if not companyfacts_candidates:
        raise FileNotFoundError("No Aeromexico companyfacts bronze file found")
    companyfacts_path = companyfacts_candidates[-1]
    companyfacts = json.loads(companyfacts_path.read_text(encoding="utf-8"))
    companyfacts_meta = json.loads(
        companyfacts_path.with_suffix(companyfacts_path.suffix + ".meta.json").read_text(
            encoding="utf-8"
        )
    )
    facts = companyfacts["facts"]["dei"]["EntityCommonStockSharesOutstanding"]["units"]["shares"]
    if len(facts) != 1:
        raise ValueError("Expected exactly one outstanding-shares companyfact")
    fact = facts[0]
    documents = pl.read_parquet(PATHS.silver / "sec_filing_documents.parquet")
    document = documents.filter(
        (pl.col("accession_number") == fact["accn"])
        & pl.col("is_primary_document")
    ).row(0, named=True)
    content = read_bronze_verified(document["source_file"], document["source_hash"])
    match = re.search(
        rb'name="dei:EntityCommonStockSharesOutstanding"[^>]*>'
        rb'\s*([\d,]+)\s*<',
        content,
        re.I,
    )
    if not match:
        raise ValueError("Outstanding shares not found in the 20-F primary document")
    document_value = float(match.group(1).replace(b",", b""))
    return _comparison(
        metric_key="shares_outstanding",
        period_id=str(fact["end"])[:4],
        source_a="sec_companyfacts_api",
        value_a=float(fact["val"]),
        source_b="sec_20f_inline_xbrl",
        value_b=document_value,
        source_file_a=companyfacts_path.relative_to(PATHS.bronze).as_posix(),
        source_file_b=str(document["source_file"]),
        flagged_at=max(
            datetime.fromisoformat(str(companyfacts_meta["downloaded_at"])),
            datetime.fromisoformat(str(document["ingested_at"])),
        ),
        tolerance_pct=0.0,
    )


def build_crosscheck(operating: pl.DataFrame | None = None) -> pl.DataFrame:
    if operating is None:
        operating = pl.read_parquet(PATHS.silver / "sec_operating_metrics.parquet")
    records = _quarterly_monthly_crosschecks(operating)
    records.append(_companyfacts_document_crosscheck())
    frame = pl.DataFrame(records).sort(["period_id", "metric_key"])
    for row in frame.filter(pl.col("is_material")).iter_rows(named=True):
        log_issue(
            "silver",
            "sec_crosscheck",
            str(row["source_file_a"]),
            "warning",
            "source_conflict",
            (
                f"{row['metric_key']} {row['period_id']} differs by "
                f"{float(row['pct_diff'] or 0):.2%} between {row['source_a']} "
                f"and {row['source_b']}."
            ),
            affected_rows=1,
        )
    write_parquet_atomic(frame, PATHS.silver / "sec_crosscheck.parquet")
    return frame
