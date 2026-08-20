"""Derive additive quarterly facts when BMV publishes only cumulative YTD."""

from __future__ import annotations

import calendar
from datetime import date
import hashlib

import polars as pl

from src.parse.bmv.xbrl import FACT_SCHEMA


ADDITIVE_STATEMENTS = frozenset({"310000", "410000", "520000"})


def _key(row: dict[str, object]) -> tuple[object, ...]:
    return (
        row["ticker"],
        row["concept"],
        row["unit"],
        row["dimension_axis"],
        row["dimension_member"],
        row["is_consolidated"],
    )


def derive_quarters_from_ytd(facts: pl.DataFrame) -> pl.DataFrame:
    """Append Qn = YTD_n - YTD_(n-1) for additive base currency facts."""

    source_rows = facts.filter(~pl.col("is_derived")).iter_rows(named=True)
    rows = list(source_rows)
    by_package: dict[tuple[str, str], list[dict[str, object]]] = {}
    for row in rows:
        by_package.setdefault((str(row["ticker"]), str(row["package_period_id"])), []).append(row)

    derived: list[dict[str, object]] = []
    for (ticker, package_period), package_rows in sorted(by_package.items()):
        if "Q" not in package_period:
            continue
        year = int(package_period[:4])
        quarter = int(package_period[-1])
        if quarter == 1:
            continue
        prior_quarter = quarter - 1
        prior_rows = by_package.get((ticker, f"{year}Q{prior_quarter}"), [])
        prior_month = prior_quarter * 3
        prior_end = date(year, prior_month, calendar.monthrange(year, prior_month)[1])
        prior_index = {
            _key(row): row
            for row in prior_rows
            if row["context_period_type"] == "duration"
            and row["period_start_date"] == date(year, 1, 1)
            and row["period_end_date"] == prior_end
            and row["dimension_count"] == 0
            and row["currency"] is not None
            and row["statement_type"] in ADDITIVE_STATEMENTS
        }
        current_month = quarter * 3
        current_end = date(year, current_month, calendar.monthrange(year, current_month)[1])
        direct_start = date(year, (quarter - 1) * 3 + 1, 1)
        direct_keys = {
            _key(row)
            for row in package_rows
            if row["context_period_type"] == "duration"
            and row["period_start_date"] == direct_start
            and row["period_end_date"] == current_end
            and row["dimension_count"] == 0
        }
        for current_ytd in package_rows:
            if not (
                current_ytd["context_period_type"] == "duration"
                and current_ytd["period_start_date"] == date(year, 1, 1)
                and current_ytd["period_end_date"] == current_end
                and current_ytd["dimension_count"] == 0
                and current_ytd["currency"] is not None
                and current_ytd["statement_type"] in ADDITIVE_STATEMENTS
                and current_ytd["value"] is not None
            ):
                continue
            key = _key(current_ytd)
            prior = prior_index.get(key)
            if prior is None or prior["value"] is None or key in direct_keys:
                continue
            digest = hashlib.sha256(
                f"{current_ytd['source_hash']}|{current_ytd['fact_id']}|{prior['source_hash']}|{prior['fact_id']}".encode()
            ).hexdigest()[:24]
            row = dict(current_ytd)
            value = float(current_ytd["value"]) - float(prior["value"])
            row.update(
                {
                    "fact_id": f"derived_q{quarter}_{digest}",
                    "context_id": f"derived_{year}Q{quarter}",
                    "period_id": f"{year}Q{quarter}",
                    "period_type": "quarter",
                    "period_start_date": direct_start,
                    "period_end_date": current_end,
                    "value": value,
                    "value_raw": format(value, ".15g"),
                    "is_derived": True,
                    "is_ytd": False,
                    "derivation_formula": f"Q{quarter} = Q{quarter}_YTD - Q{prior_quarter}_YTD",
                    "derivation_source_file_prior": prior["source_file"],
                    "derivation_source_hash_prior": prior["source_hash"],
                }
            )
            derived.append(row)
    if not derived:
        raise ValueError("No quarterly facts could be derived from BMV YTD packages")
    return pl.concat(
        [facts, pl.DataFrame(derived, schema=FACT_SCHEMA, strict=False)],
        how="vertical",
    ).sort(["ticker", "package_period_id", "period_end_date", "concept", "fact_id"])
