"""Shared SEC parser utilities."""

from __future__ import annotations

from calendar import monthrange
from datetime import date
import hashlib
from pathlib import Path
import re

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


# Numeric references &#128;-&#159; name C1 control points. HTML5 re-maps them
# to Windows-1252 glyphs (&#149; -> U+2022), and libxml2 does so from 2.14 on
# -- the build in Linux lxml wheels -- but not the build bundled with lxml on
# Windows. The same SEC filing therefore extracted to different text by
# platform, and approved evidence (built on Windows) failed re-verification
# elsewhere. They are pinned to the literal code point, as approved, by routing
# them through private-use characters libxml2 leaves alone.
_C1_REFERENCE = re.compile(rb"&#(?:(1[2-5][0-9])|[xX]([89][0-9a-fA-F]));")
_PRIVATE_OFFSET = 0xE000
_C1_RESTORE = {_PRIVATE_OFFSET + code: code for code in range(0x80, 0xA0)}


def _pin_c1_references(content: bytes) -> bytes:
    if any(chr(private).encode() in content for private in _C1_RESTORE):
        raise ValueError("Source already contains the private-use range used to pin C1 references")

    def replace(match: re.Match[bytes]) -> bytes:
        code = int(match[1]) if match[1] else int(match[2], 16)
        if not 0x80 <= code <= 0x9F:
            return match[0]
        return f"&#x{_PRIVATE_OFFSET + code:X};".encode()

    return _C1_REFERENCE.sub(replace, content)


def html_text(content: bytes) -> str:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", XMLParsedAsHTMLWarning)
        text = BeautifulSoup(_pin_c1_references(content), "lxml").get_text(" ", strip=True)
    return text.translate(_C1_RESTORE)


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
