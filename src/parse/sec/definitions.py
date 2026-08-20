"""Extract complete report text and reference sections from SEC documents."""

from __future__ import annotations

from datetime import UTC, datetime
import re
from typing import Any

import polars as pl

from src.config import PATHS
from src.ingest.sec.discover import classify_6k
from src.parse.sec.common import html_text, read_bronze_verified, write_parquet_atomic
from src.parse.sec.earnings_release import detect_current_period
from src.parse.sec.traffic_report import detect_traffic_period


PARSER_VERSION = "sec_text_v1.0.0"
STAGE_LENGTH_PATTERN = re.compile(
    r"SLA RASK\s*=\s*RASK\s*\*\s*\(Carrier average stage length"
    r"\s*/\s*([\d,]+)\)\s*\^\s*\(0\.5\)",
    re.I,
)
DEFINITION_TERMS = (
    "Available Seat Miles",
    "Revenue Passenger Miles",
    "Load Factor",
    "Average stage length",
    "CASK",
    "RASK",
    "Adjusted EBITDAR",
)


def _reference_record(
    document: dict[str, Any], *, document_type: str, section: str, text: str
) -> dict[str, object]:
    return {
        "carrier_key": "AEROMEXICO",
        "accession_number": document["accession_number"],
        "document_type": document_type,
        "section": section,
        "text": text,
        "word_count": len(text.split()),
        "source_system": "sec_edgar",
        "source_file": document["source_file"],
        "source_hash": document["source_hash"],
        "ingested_at": datetime.fromisoformat(document["ingested_at"]),
        "parser_version": PARSER_VERSION,
    }


def _definition_excerpt(text: str) -> str:
    sentences = re.split(r"(?<=[.!?])\s+", text)
    selected = [
        sentence
        for sentence in sentences
        if any(term.casefold() in sentence.casefold() for term in DEFINITION_TERMS)
        and len(sentence) <= 2_500
    ]
    return "\n".join(dict.fromkeys(selected))


def extract_reference_text() -> pl.DataFrame:
    documents = pl.read_parquet(PATHS.silver / "sec_filing_documents.parquet")
    primary = documents.filter(
        pl.col("form_type").is_in(["F-1", "F-1/A", "20-F"])
        & pl.col("is_primary_document")
    ).sort(["form_type", "accession_number"])
    records: list[dict[str, object]] = []
    for document in primary.iter_rows(named=True):
        content = read_bronze_verified(document["source_file"], document["source_hash"])
        text = html_text(content)
        document_type = "ipo_prospectus" if document["form_type"].startswith("F-1") else "annual_report"
        records.append(
            _reference_record(
                document,
                document_type=document_type,
                section="full_document",
                text=text,
            )
        )
        definitions = _definition_excerpt(text)
        if definitions:
            records.append(
                _reference_record(
                    document,
                    document_type=document_type,
                    section="kpi_definitions",
                    text=definitions,
                )
            )
        match = STAGE_LENGTH_PATTERN.search(text)
        if match:
            start = max(0, match.start() - 200)
            end = min(len(text), match.end() + 200)
            formula_text = text[start:end]
            records.append(
                {
                    **_reference_record(
                        document,
                        document_type=document_type,
                        section="stage_length_adjustment",
                        text=formula_text,
                    ),
                    "stage_length_reference_km": float(match.group(1).replace(",", "")),
                    "formula_key": "sla_rask",
                }
            )
    if not records:
        raise ValueError("No SEC reference text was extracted")
    frame = pl.DataFrame(records).sort(["accession_number", "section"])
    write_parquet_atomic(frame, PATHS.silver / "sec_reference_text.parquet")
    return frame


def extract_report_text() -> pl.DataFrame:
    documents = pl.read_parquet(PATHS.silver / "sec_filing_documents.parquet")
    candidates = documents.filter(
        (pl.col("form_type") == "6-K")
        & pl.col("archive_filename").str.contains(r"(?i)ex99")
        & pl.col("archive_filename").str.ends_with(".htm")
    )
    records: list[dict[str, object]] = []
    for document in candidates.iter_rows(named=True):
        content = read_bronze_verified(document["source_file"], document["source_hash"])
        raw = content.decode("utf-8", errors="replace")
        category, _, _ = classify_6k(raw)
        if category not in {"earnings", "traffic"}:
            continue
        text = html_text(content)
        period_id = (
            detect_current_period(text)
            if category == "earnings"
            else detect_traffic_period(text)
        )
        records.append(
            {
                "carrier_key": "AEROMEXICO",
                "accession_number": document["accession_number"],
                "archive_filename": document["archive_filename"],
                "report_type": category,
                "period_id": period_id,
                "section": "full_report",
                "text": text,
                "word_count": len(text.split()),
                "extracted_at": datetime.fromisoformat(document["ingested_at"]),
                "source_system": "sec_edgar",
                "source_file": document["source_file"],
                "source_hash": document["source_hash"],
                "ingested_at": datetime.fromisoformat(document["ingested_at"]),
                "parser_version": PARSER_VERSION,
            }
        )
    if not records:
        raise ValueError("No SEC report text was extracted")
    frame = pl.DataFrame(records).sort(["period_id", "report_type"])
    write_parquet_atomic(frame, PATHS.silver / "sec_report_text.parquet")
    return frame
