"""Parse monthly Aeromexico traffic exhibits filed with SEC 6-Ks."""

from __future__ import annotations

from datetime import datetime
import re
import unicodedata
from typing import Any

from bs4 import BeautifulSoup
import polars as pl

from src.config import PATHS
from src.ingest.sec.discover import classify_6k
from src.parse.sec.common import (
    html_text,
    month_dates,
    previous_year_period,
    read_bronze_verified,
)
from src.parse.sec.earnings_release import _numeric_values, _row_cells


PARSER_VERSION = "sec_traffic_v1.0.0"
MONTHS = {
    "january": 1,
    "february": 2,
    "march": 3,
    "april": 4,
    "may": 5,
    "june": 6,
    "july": 7,
    "august": 8,
    "september": 9,
    "october": 10,
    "november": 11,
    "december": 12,
}
SECTION_SPECS = {
    "passengers": ("passengers", "Passengers (thousands)", 1e3, "count"),
    "asms": ("asm_total", "ASMs (millions)", 1e6, "miles"),
    "rpms": ("rpm_total", "RPMs (millions)", 1e6, "miles"),
    "load factor": ("load_factor_total", "%", 0.01, "fraction"),
}


def _normalize(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value.replace("\xa0", " "))
    plain = "".join(c for c in decomposed if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", plain).casefold().strip()


def detect_traffic_period(text: str) -> str:
    normalized = _normalize(text[:4_000])
    month_names = "|".join(MONTHS)
    match = re.search(
        rf"\b({month_names})\s+(20\d{{2}})\s+traffic results\b", normalized
    )
    if not match:
        raise ValueError("Unable to determine traffic-report month from title")
    return f"{match.group(2)}M{MONTHS[match.group(1)]:02d}"


def parse_traffic_document(document: dict[str, Any]) -> list[dict[str, object]]:
    content = read_bronze_verified(document["source_file"], document["source_hash"])
    return parse_traffic_content(content, document)


def parse_traffic_content(
    content: bytes, document: dict[str, Any]
) -> list[dict[str, object]]:
    """Parse verified monthly exhibit bytes; exposed for frozen fixtures."""

    text = html_text(content)
    period_id = detect_traffic_period(text)
    previous_period = previous_year_period(period_id)
    soup = BeautifulSoup(content, "lxml")
    records: list[dict[str, object]] = []
    target_table = None
    for table in soup.find_all("table"):
        normalized = _normalize(" ".join(table.stripped_strings))
        if "passengers" in normalized and "asms" in normalized and "load factor" in normalized:
            target_table = table
            break
    if target_table is None:
        raise ValueError(f"Traffic statistics table not found in {document['source_file']}")

    current_spec: tuple[str, str, float, str] | None = None
    current_label = ""
    for row in target_table.find_all("tr"):
        cells = _row_cells(row)
        if not cells:
            continue
        first = _normalize(cells[0])
        section = next((key for key in SECTION_SPECS if first.startswith(key)), None)
        if section is not None:
            current_spec = SECTION_SPECS[section]
            current_label = cells[0]
            continue
        if current_spec is None or first not in {"domestic", "international", "total"}:
            continue
        values = _numeric_values(cells)
        if len(values) < 2 or values[0] is None or values[1] is None:
            raise ValueError(
                f"Traffic row lacks current/prior values: {document['source_file']} {cells}"
            )
        metric_key, unit_raw, scale_multiplier, unit_normalized = current_spec
        for observation_period, value in (
            (period_id, values[0]),
            (previous_period, values[1]),
        ):
            start_date, end_date = month_dates(observation_period)
            records.append(
                {
                    "carrier_key": "AEROMEXICO",
                    "accession_number": document["accession_number"],
                    "period_id": observation_period,
                    "period_type": "month",
                    "period_start_date": start_date,
                    "period_end_date": end_date,
                    "metric_key": metric_key,
                    "metric_label_raw": current_label,
                    "segment": first,
                    "value_raw": value,
                    "unit_raw": unit_raw,
                    "scale_multiplier": scale_multiplier,
                    "value_normalized": value * scale_multiplier,
                    "unit_normalized": unit_normalized,
                    "is_preliminary": False,
                    "is_yoy_comparison": False,
                    "extraction_method": "html_table",
                    "extraction_confidence": 0.99,
                    "source_system": "sec_edgar",
                    "source_file": document["source_file"],
                    "source_hash": document["source_hash"],
                    "ingested_at": datetime.fromisoformat(document["ingested_at"]),
                    "parser_version": PARSER_VERSION,
                }
            )
    if not records:
        raise ValueError(f"No traffic metrics extracted from {document['source_file']}")
    return records


def parse_all_traffic() -> pl.DataFrame:
    documents = pl.read_parquet(PATHS.silver / "sec_filing_documents.parquet")
    records: list[dict[str, object]] = []
    for document in documents.filter(
        (pl.col("form_type") == "6-K")
        & pl.col("archive_filename").str.contains(r"(?i)ex99")
        & pl.col("archive_filename").str.ends_with(".htm")
    ).iter_rows(named=True):
        content = read_bronze_verified(document["source_file"], document["source_hash"])
        category, _, _ = classify_6k(content.decode("utf-8", errors="replace"))
        if category == "traffic":
            records.extend(parse_traffic_document(document))
    if not records:
        raise ValueError("No SEC monthly traffic metrics were extracted")
    return pl.DataFrame(records).sort(
        ["period_id", "metric_key", "segment", "accession_number"]
    )
