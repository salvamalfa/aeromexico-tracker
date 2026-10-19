"""Candidate AFAC monthly coverage from verified PDFs and the matching charter database."""

from __future__ import annotations

import io
import re
import zipfile
from datetime import datetime
from pathlib import PurePosixPath

import openpyxl
from pypdf import PdfReader

from src.common.storage import save_bronze
from src.config import PATHS
from src.ingest.afac.download import DATATUR_DATABASE_URL
from src.source_updates.checks import verify_bronze

MONTHS = "enero febrero marzo abril mayo junio julio agosto septiembre octubre noviembre diciembre".split()


def database_months(content: bytes) -> set[int]:
    book = openpyxl.load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    try:
        rows = book["AFAC"].iter_rows(values_only=True)
        headers = list(next(rows))
        indices = [headers.index(name) for name in ("Año", "Id_mes", "Servicio")]
        observed = {"regular": set(), "fletamento": set()}
        for count, row in enumerate(rows):
            if count >= 1_000_000:
                raise ValueError("AFAC workbook exceeds bounded row count")
            year, month, service = [row[index] for index in indices]
            if year != 2026:
                continue
            key = str(service).strip().casefold()
            if key not in observed or month is None or int(month) != month or not 1 <= month <= 12:
                raise ValueError("Unexpected AFAC service or month; do not guess schema")
            observed[key].add(int(month))
        if observed["regular"] != observed["fletamento"] or not observed["regular"]:
            raise ValueError("AFAC scheduled/charter database periods differ or are missing")
        months = observed["regular"]
        if months != set(range(1, max(months) + 1)):
            raise ValueError("AFAC database has missing observation months")
        return months
    finally:
        book.close()


def bulletin_notes(content: bytes, month: int) -> dict[str, str]:
    pages = PdfReader(io.BytesIO(content)).pages
    if len(pages) != 2:
        raise ValueError("Expected the two-page AFAC scheduled-passenger bulletin")
    notes = {}
    # Match the canonical PDF parser: page 1 is domestic, page 2 international.
    for market, page in zip(("domestic", "international"), pages, strict=True):
        text = page.extract_text() or ""
        # The document explicitly names its current monthly comparison. A file
        # label or a cumulative month name alone cannot establish the period.
        pattern = rf"\by\s+{MONTHS[month - 1]}\s+(?:de\s+)?2025\s*[-–]\s*2026\b"
        if not re.search(pattern, text, re.I):
            raise ValueError("AFAC PDF content does not confirm the requested 2026 monthly comparison")
        if "Notas:" not in text or "Fuente" not in text:
            raise ValueError("AFAC bulletin notes/source section missing")
        notes[market] = text.split("Notas:", 1)[1].split("Fuente", 1)[0].strip()
    return notes


def run() -> dict:
    import polars as pl

    from src.parse.sec.common import write_parquet_atomic
    from src.parse.afac.monthly_stats import run_afac_parse

    artifacts = verify_bronze(PATHS.root)
    candidates = sorted(
        ((name, row) for name, row in artifacts.items() if row["source_system"] == "afac"),
        key=lambda pair: pair[1]["downloaded_at"],
    )
    databases = [
        (name, row)
        for name, row in candidates
        if row["source_url"] == DATATUR_DATABASE_URL and name.endswith(".zip")
    ]
    if not databases:
        raise FileNotFoundError("Verified DATATUR database ZIP is required for candidate AFAC parsing")
    zip_name, metadata = databases[-1]
    with zipfile.ZipFile(PATHS.bronze / zip_name) as archive:
        entries = archive.infolist()
        if len(entries) != 1:
            raise ValueError("Expected exactly one DATATUR database member")
        member = entries[0]
        if (
            member.is_dir()
            or member.flag_bits & 1
            or member.file_size > 100_000_000
            or PurePosixPath(member.filename).name != member.filename
            or "\\" in member.filename
            or not member.filename.lower().endswith(".xlsx")
        ):
            raise ValueError("Unsafe, encrypted, oversized or unexpected DATATUR member")
        content = archive.read(member)
    months = database_months(content)
    documents = {}
    for name, row in candidates:
        match = re.fullmatch(r"afac/2026/(\d{2})/[^/]+\.pdf", name)
        if match and int(match[1]) in months:
            documents[int(match[1])] = PATHS.bronze / name
    if set(documents) != months:
        raise ValueError(
            f"AFAC scheduled PDFs missing for database months: {sorted(months - set(documents))}"
        )
    notes = {month: bulletin_notes(path.read_bytes(), month) for month, path in documents.items()}
    database = save_bronze(
        content,
        "afac",
        "datatur_database_member",
        "current",
        "xlsx",
        f"{DATATUR_DATABASE_URL}#member={member.filename}",
        "offline_zip_member",
        "Exact verified database ZIP member; no fragment URL request.",
        downloaded_at=datetime.fromisoformat(metadata["downloaded_at"]),
        relative_dir="afac/database/extracted",
        bronze_root=PATHS.bronze,
    )
    result = run_afac_parse(documents=documents, database=database, through_month=max(months))
    path = PATHS.silver / "afac_monthly_stats.parquet"
    facts = pl.read_parquet(path)
    page_notes = pl.DataFrame(
        [
            {"period_id": f"2026M{month:02d}", "market": market, "_bulletin_note": note}
            for month, by_market in notes.items()
            for market, note in by_market.items()
        ]
    )
    facts = facts.join(page_notes, on=["period_id", "market"], how="left", validate="m:1", maintain_order="left")
    eligible = (
        pl.col("period_id").is_in([f"2026M{m:02d}" for m in months])
        & pl.col("source_family").eq("datatur_monthly_bulletin_pdf")
    )
    if facts.filter(eligible & pl.col("_bulletin_note").is_null()).height:
        raise ValueError("AFAC PDF market has no matching page notes")
    facts = facts.with_columns(
        pl.when(eligible)
        .then(
            pl.concat_str(
                [
                    pl.col("footnote_text").fill_null(""),
                    pl.col("_bulletin_note"),
                ],
                separator="\n",
            )
        )
        .otherwise(pl.col("footnote_text"))
        .alias("footnote_text")
    ).drop("_bulletin_note")
    write_parquet_atomic(facts, path)
    return {
        **result,
        "observation_months_2026": sorted(months),
        "database_zip_sha256": metadata["sha256"],
        "bulletin_notes_preserved": True,
        "coverage": "reported_monthly_universe_with_source_caveats",
        "latest_published_period": None,
        "publication_dates_verified": False,
    }
