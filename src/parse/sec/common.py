"""Shared SEC parser utilities."""

from __future__ import annotations

from calendar import monthrange
from datetime import date
import hashlib
from pathlib import Path

from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning
import polars as pl
import warnings

from src.config import PATHS


def read_bronze_verified(source_file: str, expected_hash: str) -> bytes:
    path = PATHS.bronze / source_file
    content = path.read_bytes()
    actual_hash = hashlib.sha256(content).hexdigest()
    if actual_hash != expected_hash:
        raise ValueError(
            f"Bronze hash mismatch for {source_file}: {actual_hash} != {expected_hash}"
        )
    return content


def html_text(content: bytes) -> str:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", XMLParsedAsHTMLWarning)
        return BeautifulSoup(content, "lxml").get_text(" ", strip=True)


def quarter_dates(period_id: str) -> tuple[date, date]:
    year = int(period_id[:4])
    quarter = int(period_id[-1])
    start_month = (quarter - 1) * 3 + 1
    end_month = start_month + 2
    return date(year, start_month, 1), date(
        year, end_month, monthrange(year, end_month)[1]
    )


def month_dates(period_id: str) -> tuple[date, date]:
    year = int(period_id[:4])
    month = int(period_id[-2:])
    return date(year, month, 1), date(year, month, monthrange(year, month)[1])


def previous_year_period(period_id: str) -> str:
    return f"{int(period_id[:4]) - 1}{period_id[4:]}"


def write_parquet_atomic(frame: pl.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    frame.write_parquet(temporary, compression="snappy")
    temporary.replace(path)
