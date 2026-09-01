"""Stage 5 peer-source ingestion with immutable bronze lineage."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime
import json
from pathlib import Path
from urllib.parse import unquote
from typing import Any

import polars as pl

from src.common.http import SourceHttpClient
from src.common.storage import find_bronze_by_source_url, save_bronze
from src.config import CARRIERS, PATHS
from src.ingest.sec.discover import _rows_from_columnar
from src.ingest.sec.download import DownloadedDocument, download_filing
from src.parse.sec.common import write_parquet_atomic


PARSER_VERSION = "peer_sec_discovery_v1.0.0"
COMPANY_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
RYANAIR_KEY_STATS_URL = "https://corporate.ryanair.com/facts-figures/key-stats/"
VIVA_REPORT_URL = (
    "https://cdn.investorcloud.net/VivaAerobus/InformacionFinanciera/"
    "ReportesTrimestrales/{year}-{quarter}T{yy}-en.pdf"
)


def submissions_url(cik: str) -> str:
    return f"https://data.sec.gov/submissions/CIK{cik.zfill(10)}.json"


def companyfacts_url(cik: str) -> str:
    return f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik.zfill(10)}.json"


def _metadata(path: Path) -> dict[str, Any]:
    return json.loads(
        path.with_suffix(path.suffix + ".meta.json").read_text(encoding="utf-8")
    )


def _fetch_bronze(
    client: SourceHttpClient,
    *,
    url: str,
    source_system: str,
    entity: str,
    period: str,
    ext: str,
    relative_dir: str,
    notes: str,
) -> tuple[Path, dict[str, Any]]:
    existing = find_bronze_by_source_url(url)
    if existing is not None:
        return existing
    response = client.request("GET", url)
    path = save_bronze(
        response.content,
        source_system,
        entity,
        period,
        ext,
        url,
        "httpx",
        http_status=response.status_code,
        content_type=response.headers.get("content-type", "application/octet-stream"),
        downloaded_at=datetime.now(UTC),
        notes=notes,
        relative_dir=relative_dir,
    )
    return path, _metadata(path)


def verify_sec_identities(payload: dict[str, Any]) -> list[dict[str, object]]:
    """Match every SEC-reporting project carrier to the official ticker catalog."""

    rows = list(payload.values())
    verified: list[dict[str, object]] = []
    for carrier_key in ("AEROMEXICO", "VOLARIS", "RYANAIR", "DELTA"):
        expected = CARRIERS[carrier_key]
        ticker = str(expected["ticker"])
        matches = [row for row in rows if str(row.get("ticker", "")).upper() == ticker]
        if len(matches) != 1:
            raise ValueError(f"SEC ticker {ticker} resolved to {len(matches)} records")
        match = matches[0]
        catalog_cik = str(match["cik_str"]).zfill(10)
        if catalog_cik != expected["cik"]:
            raise ValueError(
                f"CIK mismatch for {carrier_key}: config={expected['cik']} catalog={catalog_cik}"
            )
        verified.append(
            {
                "carrier_key": carrier_key,
                "ticker": ticker,
                "cik": catalog_cik,
                "company_name": str(match["title"]),
                "is_verified": True,
            }
        )
    return verified


def _select_filings(
    carrier_key: str, rows: Iterable[dict[str, Any]]
) -> list[dict[str, Any]]:
    since = "2023-01-01"
    recent = [row for row in rows if str(row.get("filingDate", "")) >= since]
    if carrier_key == "VOLARIS":
        earnings = [
            row
            for row in recent
            if row.get("form") == "6-K"
            and "vlrspr" in str(row.get("primaryDocument", "")).casefold()
        ]
        annual = [row for row in recent if row.get("form") == "20-F"]
        return sorted(earnings + annual, key=lambda row: str(row["filingDate"]))
    if carrier_key == "DELTA":
        return sorted(
            [row for row in recent if row.get("form") in {"10-Q", "10-K"}],
            key=lambda row: str(row["filingDate"]),
        )
    if carrier_key == "RYANAIR":
        return sorted(
            [row for row in recent if row.get("form") == "20-F"],
            key=lambda row: str(row["filingDate"]),
        )
    raise KeyError(carrier_key)


def _document_filter(carrier_key: str, primary_document: str):
    primary = primary_document.casefold()

    def include(filename: str) -> bool:
        lowered = filename.casefold()
        if lowered == primary:
            return True
        return carrier_key == "VOLARIS" and (
            "ex99" in lowered or "ex-99" in lowered
        ) and Path(lowered).suffix in {".htm", ".html", ".pdf"}

    return include


def ingest_sec_peers() -> dict[str, object]:
    """Download verified SEC catalogs and the bounded Stage 5 filing set."""

    index_records: list[dict[str, object]] = []
    document_records: list[dict[str, object]] = []
    with SourceHttpClient("sec") as client:
        catalog_path, catalog_meta = _fetch_bronze(
            client,
            url=COMPANY_TICKERS_URL,
            source_system="sec",
            entity="company_tickers",
            period="current",
            ext="json",
            relative_dir="sec/reference",
            notes="Official SEC ticker-to-CIK catalog used for Stage 5 identity checks.",
        )
        identities = verify_sec_identities(json.loads(catalog_path.read_text("utf-8")))
        identity_source = catalog_path.relative_to(PATHS.bronze).as_posix()
        ingested_at = datetime.fromisoformat(str(catalog_meta["downloaded_at"]))
        identity_frame = pl.DataFrame(
            [
                {
                    **row,
                    "source_system": "sec_edgar",
                    "source_file": identity_source,
                    "source_hash": str(catalog_meta["sha256"]),
                    "ingested_at": ingested_at,
                    "parser_version": PARSER_VERSION,
                }
                for row in identities
            ]
        )
        write_parquet_atomic(identity_frame, PATHS.silver / "sec_peer_identities.parquet")

        for carrier_key in ("VOLARIS", "RYANAIR", "DELTA"):
            cik = str(CARRIERS[carrier_key]["cik"])
            sub_url = submissions_url(cik)
            submissions_path, submissions_meta = _fetch_bronze(
                client,
                url=sub_url,
                source_system="sec",
                entity=f"{carrier_key.lower()}_submissions",
                period="current",
                ext="json",
                relative_dir=f"sec/{carrier_key.lower()}/submissions",
                notes=f"SEC submissions catalog for {carrier_key}.",
            )
            facts_url = companyfacts_url(cik)
            _fetch_bronze(
                client,
                url=facts_url,
                source_system="sec",
                entity=f"{carrier_key.lower()}_companyfacts",
                period="current",
                ext="json",
                relative_dir=f"sec/{carrier_key.lower()}/companyfacts",
                notes=f"SEC companyfacts for {carrier_key}.",
            )
            submissions = json.loads(submissions_path.read_text(encoding="utf-8"))
            rows = _rows_from_columnar(submissions["filings"]["recent"])
            selected = _select_filings(carrier_key, rows)
            for row in selected:
                documents = download_filing(
                    client,
                    accession_number=str(row["accessionNumber"]),
                    form_type=str(row["form"]),
                    primary_document=str(row["primaryDocument"]),
                    cik=cik,
                    carrier_key=carrier_key,
                    include_document=_document_filter(
                        carrier_key, str(row["primaryDocument"])
                    ),
                )
                index_records.append(
                    {
                        "carrier_key": carrier_key,
                        "cik": cik,
                        "company_name": str(submissions["name"]),
                        "accession_number": str(row["accessionNumber"]),
                        "form_type": str(row["form"]),
                        "filing_date": str(row["filingDate"]),
                        "report_date": str(row.get("reportDate", "")) or None,
                        "primary_document": str(row["primaryDocument"]),
                        "document_count": len(documents),
                        "source_system": "sec_edgar",
                        "source_file": submissions_path.relative_to(PATHS.bronze).as_posix(),
                        "source_hash": str(submissions_meta["sha256"]),
                        "ingested_at": datetime.fromisoformat(
                            str(submissions_meta["downloaded_at"])
                        ),
                        "parser_version": PARSER_VERSION,
                    }
                )
                document_records.extend(document.as_record() for document in documents)

    index_frame = pl.DataFrame(index_records).with_columns(
        pl.col("filing_date").str.to_date(), pl.col("report_date").str.to_date()
    )
    documents_frame = pl.DataFrame(document_records)
    write_parquet_atomic(index_frame, PATHS.silver / "sec_peer_filings_index.parquet")
    write_parquet_atomic(
        documents_frame, PATHS.silver / "sec_peer_filing_documents.parquet"
    )
    return {
        "verified_identities": len(identities),
        "filings": index_frame.height,
        "documents": documents_frame.height,
    }


def rebuild_sec_peers_from_bronze() -> dict[str, object]:
    """Recreate peer discovery tables from immutable Bronze without network I/O."""

    manifest_path = PATHS.bronze / "_manifest.jsonl"
    if not manifest_path.is_file():
        raise FileNotFoundError(f"Bronze manifest is missing: {manifest_path}")
    manifest = [
        json.loads(line)
        for line in manifest_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]

    def latest_for_url(url: str) -> dict[str, Any]:
        matches = [
            record
            for record in manifest
            if record.get("source_url") == url
            and (PATHS.bronze / str(record.get("source_file", ""))).is_file()
        ]
        if not matches:
            raise FileNotFoundError(f"Required peer discovery artifact is missing: {url}")
        return max(
            matches,
            key=lambda record: (
                int(record.get("logical_version", 0)),
                str(record.get("downloaded_at", "")),
            ),
        )

    catalog_meta = latest_for_url(COMPANY_TICKERS_URL)
    catalog_path = PATHS.bronze / str(catalog_meta["source_file"])
    identities = verify_sec_identities(json.loads(catalog_path.read_text(encoding="utf-8")))
    identity_frame = pl.DataFrame(
        [
            {
                **row,
                "source_system": "sec_edgar",
                "source_file": str(catalog_meta["source_file"]),
                "source_hash": str(catalog_meta["sha256"]),
                "ingested_at": datetime.fromisoformat(str(catalog_meta["downloaded_at"])),
                "parser_version": PARSER_VERSION,
            }
            for row in identities
        ]
    )
    write_parquet_atomic(identity_frame, PATHS.silver / "sec_peer_identities.parquet")

    index_records: list[dict[str, object]] = []
    document_records: list[dict[str, object]] = []
    for carrier_key in ("VOLARIS", "RYANAIR", "DELTA"):
        cik = str(CARRIERS[carrier_key]["cik"])
        submissions_meta = latest_for_url(submissions_url(cik))
        submissions_path = PATHS.bronze / str(submissions_meta["source_file"])
        submissions = json.loads(submissions_path.read_text(encoding="utf-8"))
        selected = _select_filings(
            carrier_key,
            _rows_from_columnar(submissions["filings"]["recent"]),
        )
        for filing in selected:
            accession = str(filing["accessionNumber"])
            compact = accession.replace("-", "")
            archive_prefix = (
                f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{compact}/"
            )
            include_document = _document_filter(
                carrier_key,
                str(filing["primaryDocument"]),
            )
            candidates_by_url: dict[str, dict[str, Any]] = {}
            for record in manifest:
                url = str(record.get("source_url", ""))
                if not url.startswith(archive_prefix):
                    continue
                filename = unquote(url.removeprefix(archive_prefix))
                if filename != "index.json" and not include_document(filename):
                    continue
                source_file = PATHS.bronze / str(record.get("source_file", ""))
                if not source_file.is_file():
                    continue
                existing = candidates_by_url.get(url)
                candidate_order = (
                    int(record.get("logical_version", 0)),
                    str(record.get("downloaded_at", "")),
                )
                existing_order = (
                    int(existing.get("logical_version", 0)),
                    str(existing.get("downloaded_at", "")),
                ) if existing else (-1, "")
                if candidate_order > existing_order:
                    candidates_by_url[url] = record
            if not candidates_by_url:
                raise FileNotFoundError(
                    f"Peer filing {carrier_key} {accession} has no Bronze documents"
                )
            documents = []
            for url, record in sorted(candidates_by_url.items()):
                filename = unquote(url.removeprefix(archive_prefix))
                document = DownloadedDocument(
                    accession_number=accession,
                    form_type=str(filing["form"]),
                    archive_filename=filename,
                    source_url=url,
                    source_file=str(record["source_file"]),
                    source_hash=str(record["sha256"]),
                    content_type=str(record["content_type"]),
                    bytes=int(record["bytes"]),
                    ingested_at=str(record["downloaded_at"]),
                    is_primary_document=filename.casefold()
                    == str(filing["primaryDocument"]).casefold(),
                    download_method=str(record["download_method"]),
                    carrier_key=carrier_key,
                    cik=cik,
                )
                documents.append(document)
                document_records.append(document.as_record())
            index_records.append(
                {
                    "carrier_key": carrier_key,
                    "cik": cik,
                    "company_name": str(submissions["name"]),
                    "accession_number": accession,
                    "form_type": str(filing["form"]),
                    "filing_date": str(filing["filingDate"]),
                    "report_date": str(filing.get("reportDate", "")) or None,
                    "primary_document": str(filing["primaryDocument"]),
                    "document_count": len(documents),
                    "source_system": "sec_edgar",
                    "source_file": str(submissions_meta["source_file"]),
                    "source_hash": str(submissions_meta["sha256"]),
                    "ingested_at": datetime.fromisoformat(str(submissions_meta["downloaded_at"])),
                    "parser_version": PARSER_VERSION,
                }
            )

    index_frame = pl.DataFrame(index_records).with_columns(
        pl.col("filing_date").str.to_date(),
        pl.col("report_date").str.to_date(),
    ).sort(["carrier_key", "filing_date", "accession_number"])
    documents_frame = pl.DataFrame(document_records).sort(
        ["carrier_key", "accession_number", "archive_filename"]
    )
    write_parquet_atomic(index_frame, PATHS.silver / "sec_peer_filings_index.parquet")
    write_parquet_atomic(
        documents_frame,
        PATHS.silver / "sec_peer_filing_documents.parquet",
    )
    return {
        "network_used": False,
        "verified_identities": identity_frame.height,
        "filings": index_frame.height,
        "documents": documents_frame.height,
    }


def ingest_non_sec_peers() -> dict[str, object]:
    """Download Viva quarterly releases and Ryanair monthly key-stat HTML."""

    viva = 0
    with SourceHttpClient("default") as client:
        for year in range(2023, 2027):
            for quarter in range(1, 5):
                if (year, quarter) > (2026, 2):
                    continue
                url = VIVA_REPORT_URL.format(year=year, quarter=quarter, yy=str(year)[2:])
                _fetch_bronze(
                    client,
                    url=url,
                    source_system="viva_ir",
                    entity="viva_aerobus_earnings",
                    period=f"{year}Q{quarter}",
                    ext="pdf",
                    relative_dir=f"peers/viva_aerobus/{year}",
                    notes=f"Viva Aerobus English quarterly earnings release {year}Q{quarter}.",
                )
                viva += 1
        _fetch_bronze(
            client,
            url=RYANAIR_KEY_STATS_URL,
            source_system="ryanair_ir",
            entity="ryanair_key_stats",
            period="current",
            ext="html",
            relative_dir="peers/ryanair/traffic",
            notes="Ryanair official monthly key statistics table.",
        )
    return {"viva_reports": viva, "ryanair_key_stats": 1}


def main() -> int:
    print(json.dumps({"sec": ingest_sec_peers(), "other": ingest_non_sec_peers()}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
