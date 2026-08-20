"""Discover and preserve BMV XBRL packages for AERO and VOLAR."""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
from typing import Any
from urllib.parse import parse_qs, urljoin, urlparse
import zipfile

from bs4 import BeautifulSoup

from src.common.http import SourceHttpClient
from src.common.storage import find_bronze_by_source_url, save_bronze
from src.config import PATHS, SOURCE_URLS


BMV_ORIGIN = "https://www.bmv.com.mx"
BMV_VIEWER_BASE = f"{BMV_ORIGIN}/docs-pub/visor/"
TRACKED_TICKERS = frozenset({"AERO", "VOLAR"})
MAX_MEMBER_BYTES = 100_000_000
MAX_PACKAGE_UNCOMPRESSED_BYTES = 250_000_000
QUARTER_FILE_PATTERN = re.compile(r"_(?P<year>20\d{2})-0(?P<quarter>[1-4])d?_\d+\.zip$")
ANNUAL_FILE_PATTERN = re.compile(r"_(?P<year>20\d{2})_\d+\.zip$")


@dataclass(frozen=True, slots=True)
class BmvReport:
    ticker: str
    carrier_key: str
    issuer_name: str
    filed_at: str
    description: str
    report_type: str
    package_period_id: str
    viewer_url: str
    zip_url: str
    zip_source_file: str | None = None
    zip_source_hash: str | None = None
    member_name: str | None = None
    member_source_url: str | None = None
    member_source_file: str | None = None
    member_source_hash: str | None = None
    ingested_at: str | None = None

    def as_record(self) -> dict[str, object]:
        return asdict(self)


def _carrier_key(ticker: str) -> str:
    return {"AERO": "AEROMEXICO", "VOLAR": "VOLARIS"}[ticker]


def _normalize_text(value: str) -> str:
    return " ".join(value.split())


def _package_period(zip_url: str, description: str) -> tuple[str, str]:
    filename = PurePosixPath(urlparse(zip_url).path).name
    quarterly = QUARTER_FILE_PATTERN.search(filename)
    if quarterly:
        return "quarter", f"{quarterly.group('year')}Q{quarterly.group('quarter')}"
    annual = ANNUAL_FILE_PATTERN.search(filename)
    if annual and "anual" in description.casefold():
        return "annual", annual.group("year")
    raise ValueError(f"Cannot determine BMV package period from {filename!r}: {description}")


def _zip_url_from_viewer(viewer_url: str) -> str:
    query = parse_qs(urlparse(viewer_url).query)
    docins = query.get("docins", [""])[0]
    zip_url = urljoin(BMV_VIEWER_BASE, docins)
    parsed = urlparse(zip_url)
    if parsed.scheme != "https" or parsed.netloc.casefold() != "www.bmv.com.mx":
        raise ValueError(f"Unsafe BMV package host in {zip_url!r}")
    if not parsed.path.startswith("/docs-pub/") or not parsed.path.casefold().endswith(".zip"):
        raise ValueError(f"Unexpected BMV package path in {zip_url!r}")
    return zip_url


def parse_catalog_html(content: bytes) -> list[BmvReport]:
    """Parse the server-rendered BMV catalog without executing JavaScript."""

    soup = BeautifulSoup(content, "lxml")
    reports: list[BmvReport] = []
    for row in soup.select("table tr"):
        cells = row.find_all("td", recursive=False)
        if len(cells) < 4:
            continue
        ticker = _normalize_text(cells[0].get_text(" ", strip=True)).upper()
        if ticker not in TRACKED_TICKERS:
            continue
        link = cells[3].find("a", href=True)
        if link is None:
            raise ValueError(f"BMV row for {ticker} has no download link")
        viewer_url = urljoin(SOURCE_URLS["bmv_xbrl"], str(link["href"]))
        zip_url = _zip_url_from_viewer(viewer_url)
        description = _normalize_text(cells[3].get_text(" ", strip=True))
        report_type, package_period_id = _package_period(zip_url, description)
        reports.append(
            BmvReport(
                ticker=ticker,
                carrier_key=_carrier_key(ticker),
                issuer_name=_normalize_text(cells[1].get_text(" ", strip=True)),
                filed_at=_normalize_text(cells[2].get_text(" ", strip=True)),
                description=description,
                report_type=report_type,
                package_period_id=package_period_id,
                viewer_url=viewer_url,
                zip_url=zip_url,
            )
        )
    if not reports:
        raise ValueError("BMV catalog contained no AERO or VOLAR XBRL reports")
    natural_keys = [(report.ticker, report.package_period_id, report.report_type) for report in reports]
    if len(natural_keys) != len(set(natural_keys)):
        raise ValueError("BMV catalog contains duplicate ticker/period/report-type rows")
    return reports


def _metadata_for_source_url(source_url: str) -> tuple[Path, dict[str, Any]]:
    found = find_bronze_by_source_url(source_url)
    if found is None:
        raise FileNotFoundError(f"No bronze artifact registered for {source_url}")
    return found


def _fetch_catalog(client: SourceHttpClient) -> tuple[bytes, Path, dict[str, Any]]:
    response = client.request(
        "GET",
        SOURCE_URLS["bmv_xbrl"],
        headers={"Accept": "text/html", "Accept-Language": "es-MX,es;q=0.9"},
    )
    path = save_bronze(
        response.content,
        "bmv",
        "portal_catalog",
        "current",
        "html",
        SOURCE_URLS["bmv_xbrl"],
        "httpx",
        http_status=response.status_code,
        content_type=response.headers.get("content-type", "text/html"),
        downloaded_at=datetime.now(UTC),
        notes="Server-rendered BMV standard XBRL catalog used to discover report packages.",
        relative_dir="bmv/catalog",
    )
    _, metadata = _metadata_for_source_url(SOURCE_URLS["bmv_xbrl"])
    return response.content, path, metadata


def _safe_member_name(name: str) -> str:
    path = PurePosixPath(name.replace("\\", "/"))
    if path.is_absolute() or not path.name or any(part in {"", ".", ".."} for part in path.parts):
        raise ValueError(f"Unsafe ZIP member path: {name!r}")
    if path.suffix.casefold() != ".json":
        raise ValueError(f"Unsupported BMV package member: {name!r}")
    return path.name


def _validate_archive(archive: zipfile.ZipFile) -> list[zipfile.ZipInfo]:
    members = [member for member in archive.infolist() if not member.is_dir()]
    if not members:
        raise ValueError("BMV XBRL package is empty")
    total = 0
    for member in members:
        _safe_member_name(member.filename)
        if member.file_size > MAX_MEMBER_BYTES:
            raise ValueError(f"BMV member is unexpectedly large: {member.filename}")
        total += member.file_size
    if total > MAX_PACKAGE_UNCOMPRESSED_BYTES:
        raise ValueError("BMV package exceeds the uncompressed size safety limit")
    return members


def _download_package(client: SourceHttpClient, report: BmvReport) -> BmvReport:
    if find_bronze_by_source_url(report.zip_url) is None:
        response = client.request("GET", report.zip_url, headers={"Accept": "application/zip"})
        if not response.content.startswith(b"PK"):
            raise ValueError(f"BMV package is not a ZIP archive: {report.zip_url}")
        save_bronze(
            response.content,
            "bmv",
            f"{report.ticker}_xbrl_package",
            report.package_period_id,
            "zip",
            report.zip_url,
            "httpx",
            http_status=response.status_code,
            content_type=response.headers.get("content-type", "application/zip"),
            downloaded_at=datetime.now(UTC),
            notes=f"BMV {report.report_type} XBRL package for {report.ticker} {report.package_period_id}.",
            relative_dir=f"bmv/xbrl/{report.ticker}/{report.package_period_id}",
        )
    zip_path, zip_metadata = _metadata_for_source_url(report.zip_url)
    if hashlib.sha256(zip_path.read_bytes()).hexdigest() != zip_metadata["sha256"]:
        raise ValueError(f"Bronze hash mismatch for {zip_path}")

    extracted: list[tuple[str, str, Path, dict[str, Any]]] = []
    with zipfile.ZipFile(zip_path) as archive:
        for member in _validate_archive(archive):
            member_name = _safe_member_name(member.filename)
            member_url = f"{report.zip_url}#member={member.filename}"
            member_content = archive.read(member)
            if find_bronze_by_source_url(member_url) is None:
                save_bronze(
                    member_content,
                    "bmv",
                    f"{report.ticker}_xbrl_member",
                    report.package_period_id,
                    "json",
                    member_url,
                    "httpx",
                    content_type="application/json",
                    downloaded_at=datetime.now(UTC),
                    notes=f"Exact member {member.filename} extracted from immutable BMV ZIP.",
                    relative_dir=f"bmv/xbrl/{report.ticker}/{report.package_period_id}/extracted",
                )
            member_path, member_metadata = _metadata_for_source_url(member_url)
            extracted.append((member_name, member_url, member_path, member_metadata))
    if len(extracted) != 1:
        raise ValueError(f"Expected one JSON instance in {report.zip_url}; found {len(extracted)}")
    member_name, member_url, member_path, member_metadata = extracted[0]
    return replace(
        report,
        zip_source_file=zip_path.relative_to(PATHS.bronze).as_posix(),
        zip_source_hash=str(zip_metadata["sha256"]),
        member_name=member_name,
        member_source_url=member_url,
        member_source_file=member_path.relative_to(PATHS.bronze).as_posix(),
        member_source_hash=str(member_metadata["sha256"]),
        ingested_at=str(member_metadata["downloaded_at"]),
    )


def download_bmv_reports() -> dict[str, object]:
    """Refresh the catalog and preserve every visible AERO/VOLAR package."""

    with SourceHttpClient("bmv") as client:
        catalog_content, catalog_path, catalog_metadata = _fetch_catalog(client)
        reports = parse_catalog_html(catalog_content)
        downloaded = [_download_package(client, report) for report in reports]
    counts = {ticker: sum(report.ticker == ticker for report in downloaded) for ticker in sorted(TRACKED_TICKERS)}
    periods = {
        ticker: sorted(report.package_period_id for report in downloaded if report.ticker == ticker)
        for ticker in sorted(TRACKED_TICKERS)
    }
    return {
        "catalog_source_file": catalog_path.relative_to(PATHS.bronze).as_posix(),
        "catalog_source_hash": catalog_metadata["sha256"],
        "report_count": len(downloaded),
        "ticker_counts": counts,
        "periods": periods,
    }


def main() -> int:
    print(json.dumps(download_bmv_reports(), indent=2, ensure_ascii=False, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
