"""Calendar coverage from observation periods, never capture time or fiscal labels."""

from __future__ import annotations

from datetime import date
from pathlib import Path
import re

import pandas as pd
import pyarrow.parquet as pq


PERIOD_COLUMNS = ("period_id", "calendar_period_id")
DATE_COLUMNS = ("date", "period_start_date", "period_end_date")
CALENDAR_PERIOD = re.compile(r"(\d{4})(?:M(\d{2})|Q([1-4])(?:YTD|TTM)?)?")


def observation_bounds(silver_dir: Path) -> tuple[date, date]:
    """Cover declared input periods without guessing the next release or using today."""
    observed: list[date] = []
    for path in sorted(silver_dir.glob("*.parquet")):
        available = set(pq.ParquetFile(path).schema_arrow.names)
        columns = [name for name in (*PERIOD_COLUMNS, *DATE_COLUMNS) if name in available]
        if {"year", "month"} <= available:
            columns.extend(("year", "month"))
        if not columns:
            continue
        frame = pd.read_parquet(path, columns=columns)
        for column in PERIOD_COLUMNS:
            if column not in frame:
                continue
            for value in frame[column].dropna().astype(str).unique():
                match = CALENDAR_PERIOD.fullmatch(value)
                if match is None:
                    # FY labels and other non-calendar identities do not set the horizon.
                    continue
                year, month, quarter = match.groups()
                if month:
                    period = pd.Period(f"{year}-{month}", freq="M")
                elif quarter:
                    period = pd.Period(f"{year}Q{quarter}", freq="Q")
                else:
                    period = pd.Period(year, freq="Y")
                observed.extend((period.start_time.date(), period.end_time.date()))
        for column in DATE_COLUMNS:
            if column in frame:
                observed.extend(pd.Timestamp(value).date() for value in frame[column].dropna().unique())
        if {"year", "month"} <= set(frame):
            for year, month in (
                frame[["year", "month"]].dropna().drop_duplicates().itertuples(index=False, name=None)
            ):
                observed.append(date(int(year), int(month), 1))
    if not observed:
        raise ValueError("No observed calendar periods in Silver inputs; cannot build dim_period")
    return min(observed), max(observed)
