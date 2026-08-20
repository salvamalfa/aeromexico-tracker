"""Discover, classify, and normalize Aeromexico SEC filings."""

from __future__ import annotations

from collections import Counter
from datetime import UTC, date, datetime
import hashlib
import json
from pathlib import Path
import re
import unicodedata
from typing import Any, Iterable
from urllib.parse import unquote

from bs4 import BeautifulSoup
import polars as pl

from src.common.http import SourceHttpClient
from src.common.storage import save_bronze
from src.config import CIK_AEROMEXICO, PATHS, SOURCE_URLS
from src.ingest.sec.download import (
    DownloadedDocument,
    document_text,
    download_filing,
    filing_base_url,
)


PARSER_VERSION = "sec_discover_v1.0.0"
RELEVANT_FORMS = frozenset({"6-K", "20-F", "F-1", "F-1/A"})
CLASSIFICATION_PATTERNS: dict[str, tuple[str, ...]] = {
    "earnings": (
        "quarterly results",
        "financial results",
        "results for the",
        "ebitdar",
        "operating revenue",
        "casm",
        "trasm",
        "fourth quarter",
    ),
    "traffic": (
        "traffic report",
        "traffic results",
        "passenger traffic",
        "operating statistics",
        "passengers carried",
        "monthly traffic",
        "reporte de trafico",
    ),
    "governance": (
        "shareholders meeting",
        "general meeting",
        "asamblea",
        "board of directors",
        "corporate governance",
    ),
}


def _normalize_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    without_accents = "".join(char for char in normalized if not unicodedata.combining(char))
    return re.sub(r"\s+", " ", without_accents).casefold().strip()


def _visible_text(raw_document: str) -> str:
    if "<" not in raw_document:
        return raw_document
    return BeautifulSoup(raw_document, "lxml").get_text(" ", strip=True)


def classify_6k(text: str) -> tuple[str, float, list[str]]:
    normalized = _normalize_text(_visible_text(text))
    hits = {
        category: [pattern for pattern in patterns if pattern in normalized]
        for category, patterns in CLASSIFICATION_PATTERNS.items()
    }
    scores = {category: len(patterns) for category, patterns in hits.items()}
    earnings_score = scores["earnings"]
    traffic_score = scores["traffic"]
    governance_score = scores["governance"]
    if earnings_score >= 2 and earnings_score >= traffic_score:
        category = "earnings"
    elif traffic_score >= 2 or (
        traffic_score >= 1
        and any(
            phrase in hits["traffic"]
            for phrase in ("traffic report", "traffic results", "monthly traffic")
        )
    ):
        category = "traffic"
    elif governance_score >= 2:
        category = "governance"
    else:
        return "material_event", 0.5, []
    confidence = min(0.99, 0.55 + 0.07 * scores[category])
    return category, confidence, hits[category]


def _rows_from_columnar(columnar: dict[str, list[Any]]) -> list[dict[str, Any]]:
    lengths = {key: len(values) for key, values in columnar.items()}
    if not lengths or len(set(lengths.values())) != 1:
        raise ValueError(f"SEC submissions arrays have inconsistent lengths: {lengths}")
    keys = list(columnar)
    return [dict(zip(keys, values, strict=True)) for values in zip(*(columnar[k] for k in keys), strict=True)]


def _save_current_json(
    response_content: bytes,
    *,
    entity: str,
    url: str,
    content_type: str,
    notes: str,
) -> tuple[Path, dict[str, Any]]:
    ingested_at = datetime.now(UTC)
    path = save_bronze(
        response_content,
        "sec",
        entity,
        "current",
        "json",
        url,
        "httpx",
        content_type=content_type,
        downloaded_at=ingested_at,
        notes=notes,
        relative_dir=f"sec/{entity}",
    )
    metadata = json.loads(
        path.with_suffix(path.suffix + ".meta.json").read_text(encoding="utf-8")
    )
    return path, metadata


def download_source_catalogs(
    client: SourceHttpClient,
) -> tuple[dict[str, Any], Path, dict[str, Any], dict[str, Any], Path, dict[str, Any]]:
    submissions_response = client.request("GET", SOURCE_URLS["sec_submissions"])
    submissions_path, submissions_meta = _save_current_json(
        submissions_response.content,
        entity="submissions",
        url=SOURCE_URLS["sec_submissions"],
        content_type=submissions_response.headers.get("content-type", "application/json"),
        notes="Aeromexico SEC submissions catalog for Stage 1 discovery.",
    )
    companyfacts_response = client.request("GET", SOURCE_URLS["sec_companyfacts"])
    companyfacts_path, companyfacts_meta = _save_current_json(
        companyfacts_response.content,
        entity="companyfacts",
        url=SOURCE_URLS["sec_companyfacts"],
        content_type=companyfacts_response.headers.get("content-type", "application/json"),
        notes="Aeromexico SEC companyfacts coverage check for Stage 1.",
    )
    return (
        submissions_response.json(),
        submissions_path,
        submissions_meta,
        companyfacts_response.json(),
        companyfacts_path,
        companyfacts_meta,
    )


def companyfacts_summary(payload: dict[str, Any]) -> dict[str, object]:
    facts = payload.get("facts", {})
    if not isinstance(facts, dict):
        raise ValueError("Unexpected SEC companyfacts schema: facts is not an object")
    taxonomies = {
        taxonomy: sorted(concepts)
        for taxonomy, concepts in facts.items()
        if isinstance(concepts, dict)
    }
    return {
        "entity_name": payload.get("entityName"),
        "taxonomies": taxonomies,
        "taxonomy_counts": {key: len(value) for key, value in taxonomies.items()},
        "has_ifrs_full": bool(taxonomies.get("ifrs-full")),
        "has_us_gaap": bool(taxonomies.get("us-gaap")),
    }


def _historical_rows(
    client: SourceHttpClient,
    submissions_payload: dict[str, Any],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for file_info in submissions_payload.get("filings", {}).get("files", []):
        name = str(file_info["name"])
        url = f"https://data.sec.gov/submissions/{name}"
        response = client.request("GET", url)
        path, _ = _save_current_json(
            response.content,
            entity=f"submissions_{Path(name).stem}",
            url=url,
            content_type=response.headers.get("content-type", "application/json"),
            notes=f"Historical SEC submissions page {name}.",
        )
        payload = json.loads(path.read_text(encoding="utf-8"))
        rows.extend(_rows_from_columnar(payload))
    return rows


def _form_classification(form_type: str) -> str:
    if form_type == "20-F":
        return "annual_report"
    if form_type in {"F-1", "F-1/A", "424B1", "FWP"}:
        return "registration"
    if form_type in {"3", "4", "5"}:
        return "insider_ownership"
    if form_type.startswith("SCHEDULE 13"):
        return "beneficial_ownership"
    if form_type == "S-8":
        return "employee_plan"
    if form_type in {"8-A12B", "CERT"}:
        return "listing"
    if form_type.startswith("DRS"):
        return "draft_registration"
    return "other"


def _parse_date(value: Any) -> date | None:
    text = str(value or "").strip()
    return date.fromisoformat(text) if text else None


def _write_parquet_atomic(frame: pl.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    frame.write_parquet(temporary, compression="snappy")
    temporary.replace(path)


def _write_discovery_tables(
    *,
    all_rows: list[dict[str, Any]],
    submissions: dict[str, Any],
    submissions_path: Path,
    submissions_meta: dict[str, Any],
    documents_by_accession: dict[str, list[DownloadedDocument]],
) -> tuple[pl.DataFrame, pl.DataFrame]:
    source_relative = submissions_path.relative_to(PATHS.bronze).as_posix()
    index_records: list[dict[str, object]] = []
    for row in all_rows:
        accession = str(row["accessionNumber"])
        form_type = str(row["form"])
        downloaded = documents_by_accession.get(accession, [])
        reasons: list[str] = []
        content_tags: list[str] = []
        if form_type == "6-K":
            combined_text = "\n".join(
                _visible_text(document_text(doc)) for doc in downloaded
            )
            content_type, confidence, reasons = classify_6k(combined_text)
            tag_documents = [
                doc
                for doc in downloaded
                if "ex99" in doc.archive_filename.casefold()
            ] or [doc for doc in downloaded if doc.is_primary_document]
            document_categories = set()
            for doc in tag_documents:
                text = document_text(doc)
                if text:
                    document_categories.add(classify_6k(text)[0])
            content_tags = sorted(
                category
                for category in document_categories
                if category != "material_event" or len(document_categories) == 1
            )
        else:
            content_type = _form_classification(form_type)
            confidence = 1.0 if content_type != "other" else 0.5
            content_tags = [content_type]
        base_url = filing_base_url(accession)
        primary_document = str(row["primaryDocument"])
        index_records.append(
            {
                "cik": CIK_AEROMEXICO,
                "company_name": str(submissions["name"]),
                "carrier_key": "AEROMEXICO",
                "accession_number": accession,
                "form_type": form_type,
                "filing_date": _parse_date(row.get("filingDate")),
                "report_date": _parse_date(row.get("reportDate")),
                "primary_document": primary_document,
                "primary_doc_url": f"{base_url}/{primary_document}",
                "filing_index_url": f"{base_url}/{accession}-index.html",
                "items": str(row.get("items", "")),
                "content_type": content_type,
                "classification_confidence": confidence,
                "classification_reasons": reasons,
                "content_tags": content_tags,
                "has_earnings": "earnings" in content_tags,
                "has_traffic": "traffic" in content_tags,
                "has_governance": "governance" in content_tags,
                "is_downloaded": bool(downloaded),
                "document_count": len(downloaded),
                "source_system": "sec_edgar",
                "source_file": source_relative,
                "source_hash": str(submissions_meta["sha256"]),
                "ingested_at": datetime.fromisoformat(str(submissions_meta["downloaded_at"])),
                "parser_version": PARSER_VERSION,
            }
        )
    documents = [
        document
        for accession_documents in documents_by_accession.values()
        for document in accession_documents
    ]
    index_frame = pl.DataFrame(index_records).sort("filing_date", descending=True)
    documents_frame = pl.DataFrame([document.as_record() for document in documents]).sort(
        ["accession_number", "archive_filename"]
    )
    _write_parquet_atomic(index_frame, PATHS.silver / "sec_filings_index.parquet")
    _write_parquet_atomic(
        documents_frame, PATHS.silver / "sec_filing_documents.parquet"
    )
    return index_frame, documents_frame


def discover_and_download() -> dict[str, object]:
    """Run SEC discovery, download relevant filings, and write silver indexes."""

    with SourceHttpClient("sec") as client:
        (
            submissions,
            submissions_path,
            submissions_meta,
            companyfacts,
            companyfacts_path,
            companyfacts_meta,
        ) = download_source_catalogs(client)
        recent = _rows_from_columnar(submissions["filings"]["recent"])
        all_rows = recent + _historical_rows(client, submissions)
        accessions = [str(row["accessionNumber"]) for row in all_rows]
        if len(accessions) != len(set(accessions)):
            raise ValueError("Duplicate accession numbers in SEC submissions catalog")

        documents: list[DownloadedDocument] = []
        documents_by_accession: dict[str, list[DownloadedDocument]] = {}
        relevant = [row for row in all_rows if str(row["form"]) in RELEVANT_FORMS]
        for row in relevant:
            accession = str(row["accessionNumber"])
            downloaded = download_filing(
                client,
                accession_number=accession,
                form_type=str(row["form"]),
                primary_document=str(row["primaryDocument"]),
            )
            documents.extend(downloaded)
            documents_by_accession[accession] = downloaded

    index_frame, documents_frame = _write_discovery_tables(
        all_rows=all_rows,
        submissions=submissions,
        submissions_path=submissions_path,
        submissions_meta=submissions_meta,
        documents_by_accession=documents_by_accession,
    )
    summary = companyfacts_summary(companyfacts)
    return {
        "filing_count": index_frame.height,
        "form_counts": dict(Counter(index_frame["form_type"].to_list())),
        "six_k_classification_counts": dict(
            Counter(
                index_frame.filter(pl.col("form_type") == "6-K")["content_type"].to_list()
            )
        ),
        "downloaded_filing_count": len(documents_by_accession),
        "downloaded_document_count": documents_frame.height,
        "companyfacts": summary,
        "companyfacts_source_file": companyfacts_path.relative_to(PATHS.bronze).as_posix(),
        "companyfacts_source_hash": companyfacts_meta["sha256"],
        "filings_index_path": str(PATHS.silver / "sec_filings_index.parquet"),
        "documents_index_path": str(PATHS.silver / "sec_filing_documents.parquet"),
    }


def rebuild_discovery_from_bronze() -> dict[str, object]:
    """Recreate discovery tables from bronze and its manifest without network I/O."""

    manifest_path = PATHS.bronze / "_manifest.jsonl"
    manifest = [
        json.loads(line)
        for line in manifest_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    submissions_records = [
        record
        for record in manifest
        if record.get("source_url") == SOURCE_URLS["sec_submissions"]
        and (PATHS.bronze / str(record.get("source_file", ""))).is_file()
    ]
    if not submissions_records:
        raise FileNotFoundError("SEC submissions catalog is missing from bronze")
    submissions_meta = submissions_records[-1]
    submissions_path = PATHS.bronze / str(submissions_meta["source_file"])
    submissions = json.loads(submissions_path.read_text(encoding="utf-8"))
    all_rows = _rows_from_columnar(submissions["filings"]["recent"])
    for file_info in submissions.get("filings", {}).get("files", []):
        url = f"https://data.sec.gov/submissions/{file_info['name']}"
        matching = [record for record in manifest if record.get("source_url") == url]
        if not matching:
            raise FileNotFoundError(f"Historical submissions page missing from bronze: {url}")
        path = PATHS.bronze / str(matching[-1]["source_file"])
        all_rows.extend(_rows_from_columnar(json.loads(path.read_text(encoding="utf-8"))))

    relevant = {
        str(row["accessionNumber"]): row
        for row in all_rows
        if str(row["form"]) in RELEVANT_FORMS
    }
    by_compact_accession = {
        accession.replace("-", ""): accession for accession in relevant
    }
    archive_pattern = re.compile(
        r"^https://www\.sec\.gov/Archives/edgar/data/1561861/(\d{18})/(.+)$"
    )
    unique_documents: dict[tuple[str, str], DownloadedDocument] = {}
    for record in manifest:
        url = str(record.get("source_url", ""))
        match = archive_pattern.match(url)
        if not match or match.group(1) not in by_compact_accession:
            continue
        accession = by_compact_accession[match.group(1)]
        source_file = str(record.get("source_file", ""))
        if not (PATHS.bronze / source_file).is_file():
            continue
        filename = unquote(match.group(2))
        filing = relevant[accession]
        unique_documents[(accession, url)] = DownloadedDocument(
            accession_number=accession,
            form_type=str(filing["form"]),
            archive_filename=filename,
            source_url=url,
            source_file=source_file,
            source_hash=str(record["sha256"]),
            content_type=str(record["content_type"]),
            bytes=int(record["bytes"]),
            ingested_at=str(record["downloaded_at"]),
            is_primary_document=filename.casefold()
            == str(filing["primaryDocument"]).casefold(),
            download_method=str(record["download_method"]),
        )
    documents_by_accession: dict[str, list[DownloadedDocument]] = {
        accession: [] for accession in relevant
    }
    for document in unique_documents.values():
        documents_by_accession[document.accession_number].append(document)
    missing = [
        accession for accession, documents in documents_by_accession.items() if not documents
    ]
    if missing:
        raise FileNotFoundError(f"Relevant filings missing from bronze: {missing}")
    index_frame, documents_frame = _write_discovery_tables(
        all_rows=all_rows,
        submissions=submissions,
        submissions_path=submissions_path,
        submissions_meta=submissions_meta,
        documents_by_accession=documents_by_accession,
    )
    return {
        "filing_count": index_frame.height,
        "downloaded_filing_count": len(documents_by_accession),
        "downloaded_document_count": documents_frame.height,
        "network_used": False,
    }


def main() -> int:
    print(json.dumps(discover_and_download(), indent=2, ensure_ascii=False, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
