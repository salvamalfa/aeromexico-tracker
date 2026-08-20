"""Discover and preserve AFAC airline statistics from official public sources."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
from urllib.parse import urljoin, urlparse
import zipfile

from bs4 import BeautifulSoup

from src.common.http import SourceHttpClient
from src.common.storage import find_bronze_by_source_url, save_bronze
from src.config import PATHS


DATATUR_CATALOG_URL = "https://datatur.sectur.gob.mx/SitePages/afac.aspx"
DATATUR_DATABASE_URL = (
    "https://datatur.sectur.gob.mx/Documentoscompartidos/afac/DB_AFAC.zip"
)
AFAC_CATALOG_URL = (
    "https://www.gob.mx/afac/acciones-y-programas/"
    "estadistica-mensual-por-aerolinea-monthly-airline-statistics"
)
AFAC_ARCHIVE_TIMESTAMP = "20240315161818"
AFAC_ARCHIVE_URL = (
    f"https://web.archive.org/web/{AFAC_ARCHIVE_TIMESTAMP}id_/" f"{AFAC_CATALOG_URL}"
)
DATATUR_ORIGIN = "https://datatur.sectur.gob.mx"
OFFICIAL_ATTACHMENT_HOST = "www.gob.mx"
PDF_PATTERN = re.compile(r"AFAC_(?P<year>20\d{2})_(?P<month>0[1-9]|1[0-2])\.pdf$", re.I)
YEAR_PATTERN = re.compile(r"(?P<year>19\d{2}|20\d{2})")
MAX_DOWNLOAD_BYTES = 100_000_000
XLS_MAGIC = bytes.fromhex("D0CF11E0A1B11AE1")

# The live gob.mx catalog is rendered successfully by a browser but its attachment
# CDN intermittently challenges direct HTTP clients.  Keeping the browser-observed
# filenames and canonical URLs here makes a manual/browser refresh deterministic.
CURRENT_ANNUAL_DOWNLOADS: dict[int, tuple[str, str]] = {
    2012: ("resumendic12.xlsx", "https://www.gob.mx/cms/uploads/attachment/file/652433/resumendic12.xlsx"),
    2013: ("resumendic13.xlsx", "https://www.gob.mx/cms/uploads/attachment/file/652434/resumendic13.xlsx"),
    2014: ("resumen-2014-dic-total.xlsx", "https://www.gob.mx/cms/uploads/attachment/file/652429/resumen-2014-dic-total.xlsx"),
    2015: ("resumen-2015-historico.xlsx", "https://www.gob.mx/cms/uploads/attachment/file/652430/resumen-2015-historico.xlsx"),
    2016: ("resumen-2016-historico-10032017.xlsx", "https://www.gob.mx/cms/uploads/attachment/file/652431/resumen-2016-historico-10032017.xlsx"),
    2017: ("resumen-2017-historico-25052017.xlsx", "https://www.gob.mx/cms/uploads/attachment/file/652432/resumen-2017-historico-25052017.xlsx"),
    2018: ("resumen-diciembre-2018-16042019.xlsx", "https://www.gob.mx/cms/uploads/attachment/file/652435/resumen-diciembre-2018-16042019.xlsx"),
    2019: ("resumen-historico-dic-19.xlsx", "https://www.gob.mx/cms/uploads/attachment/file/652436/resumen-historico-dic-19.xlsx"),
    2020: ("resumen-diciembre-2020-24052025.xlsx", "https://www.gob.mx/cms/uploads/attachment/file/992048/resumen-diciembre-2020-24052025.xlsx"),
    2021: ("resumen-diciembre-2021-24052025.xlsx", "https://www.gob.mx/cms/uploads/attachment/file/992049/resumen-diciembre-2021-24052025.xlsx"),
    2022: ("resumen-diciembre-2022-28012026.xlsx", "https://www.gob.mx/cms/uploads/attachment/file/1052813/resumen-diciembre-2022-28012026.xlsx"),
    2023: ("resumen-diciembre-2023-28012026.xlsx", "https://www.gob.mx/cms/uploads/attachment/file/1052814/resumen-diciembre-2023-28012026.xlsx"),
    2024: ("resumen-diciembre-2024-28012026.xlsx", "https://www.gob.mx/cms/uploads/attachment/file/1052815/resumen-diciembre-2024-28012026.xlsx"),
    2025: ("resumen-diciembre-2025-05022026h.xlsx", "https://www.gob.mx/cms/uploads/attachment/file/1055165/resumen-diciembre-2025-05022026h.xlsx"),
}

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 Chrome/128.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/pdf,application/zip,*/*;q=0.8",
    "Accept-Language": "es-MX,es;q=0.9,en;q=0.8",
    "Referer": DATATUR_CATALOG_URL,
}


@dataclass(frozen=True, slots=True)
class AfacArtifact:
    period_id: str
    artifact_type: str
    source_url: str
    extension: str


class UnexpectedAfacPayloadError(ValueError):
    """A public URL returned bytes that do not match its declared artifact."""


def _validate_host(url: str, allowed_host: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.netloc.casefold() != allowed_host:
        raise ValueError(f"Unsafe AFAC source URL: {url!r}")


def parse_datatur_catalog(content: bytes) -> list[AfacArtifact]:
    """Return every monthly PDF visibly linked by the official DATATUR mirror."""

    soup = BeautifulSoup(content, "lxml")
    artifacts: dict[str, AfacArtifact] = {}
    for anchor in soup.select("a[href]"):
        href = str(anchor.get("href") or "").strip()
        if not href:
            continue
        if href.casefold().endswith(".pd"):
            href += "f"  # The live page currently truncates 2024/2025 extensions.
        url = urljoin(DATATUR_CATALOG_URL, href)
        match = PDF_PATTERN.search(PurePosixPath(urlparse(url).path).name)
        if not match:
            continue
        _validate_host(url, "datatur.sectur.gob.mx")
        period_id = f"{match.group('year')}M{match.group('month')}"
        artifacts[url] = AfacArtifact(period_id, "datatur_monthly_bulletin", url, "pdf")
    return sorted(artifacts.values(), key=lambda artifact: artifact.period_id)


def parse_historical_catalog(content: bytes) -> list[AfacArtifact]:
    """Return unique official Excel attachments from the archived AFAC catalog."""

    soup = BeautifulSoup(content, "lxml")
    artifacts: dict[str, AfacArtifact] = {}
    for anchor in soup.select("a[href]"):
        href = str(anchor.get("href") or "").strip()
        parsed = urlparse(href)
        extension = PurePosixPath(parsed.path).suffix.casefold().lstrip(".")
        if extension not in {"xls", "xlsx"}:
            continue
        _validate_host(href, OFFICIAL_ATTACHMENT_HOST)
        text = " ".join(anchor.get_text(" ", strip=True).split())
        match = YEAR_PATTERN.search(f"{text} {PurePosixPath(parsed.path).name}")
        if not match:
            raise ValueError(f"Cannot determine AFAC year for {href}")
        year = match.group("year")
        artifacts[href] = AfacArtifact(year, "afac_annual_workbook", href, extension)
    result = sorted(artifacts.values(), key=lambda artifact: artifact.period_id)
    years = [artifact.period_id for artifact in result]
    if years != [str(year) for year in range(1992, 2024)]:
        raise ValueError(f"Unexpected archived AFAC workbook coverage: {years}")
    return result


def _validate_payload(content: bytes, extension: str, source_url: str) -> None:
    if not content or len(content) > MAX_DOWNLOAD_BYTES:
        raise ValueError(f"Invalid AFAC payload size for {source_url}: {len(content)}")
    if extension == "pdf" and not content.startswith(b"%PDF-"):
        raise ValueError(f"AFAC PDF has invalid magic bytes: {source_url}")
    if extension == "xls" and not content.startswith(XLS_MAGIC):
        raise ValueError(f"AFAC XLS has invalid magic bytes: {source_url}")
    if extension == "xlsx":
        if not content.startswith(b"PK"):
            raise ValueError(f"AFAC XLSX has invalid magic bytes: {source_url}")
        from io import BytesIO

        with zipfile.ZipFile(BytesIO(content)) as archive:
            names = set(archive.namelist())
            if "[Content_Types].xml" not in names or "xl/workbook.xml" not in names:
                raise ValueError(f"AFAC XLSX is missing workbook members: {source_url}")
    if extension == "zip":
        from io import BytesIO

        with zipfile.ZipFile(BytesIO(content)) as archive:
            members = [member for member in archive.infolist() if not member.is_dir()]
            if len(members) != 1 or PurePosixPath(members[0].filename).suffix.casefold() != ".xlsx":
                raise ValueError(f"Unexpected DATATUR database archive: {source_url}")
            if members[0].file_size > MAX_DOWNLOAD_BYTES:
                raise ValueError(f"DATATUR database member is too large: {source_url}")


def _existing(source_url: str) -> tuple[Path, dict[str, object]] | None:
    found = find_bronze_by_source_url(source_url)
    if found is None:
        return None
    path, metadata = found
    if hashlib.sha256(path.read_bytes()).hexdigest() != metadata["sha256"]:
        raise ValueError(f"Bronze hash mismatch for {path}")
    return path, metadata


def _valid_existing(artifact: AfacArtifact) -> tuple[Path, dict[str, object]] | None:
    found = _existing(artifact.source_url)
    if found is None:
        return None
    try:
        _validate_payload(found[0].read_bytes(), artifact.extension, artifact.source_url)
    except ValueError:
        return None
    return found


def _fetch(
    client: SourceHttpClient,
    artifact: AfacArtifact,
    *,
    refresh: bool = False,
) -> tuple[Path, dict[str, object]]:
    found = None if refresh else _valid_existing(artifact)
    if found is not None:
        return found
    response = client.request("GET", artifact.source_url, headers=HEADERS)
    content = response.content
    try:
        _validate_payload(content, artifact.extension, artifact.source_url)
    except ValueError as exc:
        unexpected_extension = (
            "html"
            if b"<html" in content[:500].lower() or b"<!doctype html" in content[:500].lower()
            else "bin"
        )
        save_bronze(
            content,
            "afac",
            f"{artifact.artifact_type}_unexpected_response",
            artifact.period_id,
            unexpected_extension,
            str(response.url),
            "httpx",
            f"Unexpected response preserved before raising: {exc}",
            http_status=response.status_code,
            content_type=response.headers.get("content-type", "application/octet-stream"),
            relative_dir=f"afac/{artifact.period_id}",
        )
        raise UnexpectedAfacPayloadError(str(exc)) from exc
    relative_dir = (
        f"afac/{artifact.period_id}"
        if artifact.artifact_type != "datatur_monthly_bulletin"
        else f"afac/{artifact.period_id[:4]}/{artifact.period_id[-2:]}"
    )
    path = save_bronze(
        content,
        "afac",
        artifact.artifact_type,
        artifact.period_id,
        artifact.extension,
        str(response.url),
        "httpx",
        "Official AFAC statistics or official DATATUR mirror artifact.",
        http_status=response.status_code,
        content_type=response.headers.get("content-type", "application/octet-stream"),
        relative_dir=relative_dir,
    )
    found = _existing(str(response.url))
    if found is None:
        raise RuntimeError(f"Saved AFAC artifact is absent from manifest: {path}")
    return found


def _fetch_catalog(
    client: SourceHttpClient,
    url: str,
    entity: str,
    period: str,
    relative_dir: str,
    *,
    refresh: bool,
) -> tuple[bytes, Path, dict[str, object]]:
    found = None if refresh else _existing(url)
    if found is not None:
        path, metadata = found
        return path.read_bytes(), path, metadata
    response = client.request("GET", url, headers=HEADERS)
    content = response.content
    if b"<html" not in content[:500].lower() and b"<!doctype html" not in content[:500].lower():
        raise ValueError(f"AFAC catalog is not HTML: {url}")
    path = save_bronze(
        content,
        "afac",
        entity,
        period,
        "html",
        str(response.url),
        "httpx",
        "Public catalog used to discover AFAC source files.",
        http_status=response.status_code,
        content_type=response.headers.get("content-type", "text/html"),
        relative_dir=relative_dir,
    )
    found = _existing(str(response.url))
    if found is None:
        raise RuntimeError(f"Saved AFAC catalog is absent from manifest: {path}")
    return content, found[0], found[1]


def _preserve_database_member(zip_path: Path) -> Path:
    with zipfile.ZipFile(zip_path) as archive:
        members = [member for member in archive.infolist() if not member.is_dir()]
        if len(members) != 1:
            raise ValueError(f"Expected one DATATUR database member; found {len(members)}")
        member = members[0]
        if PurePosixPath(member.filename).name != member.filename:
            raise ValueError(f"Unsafe DATATUR ZIP member: {member.filename}")
        content = archive.read(member)
    _validate_payload(content, "xlsx", DATATUR_DATABASE_URL)
    member_url = f"{DATATUR_DATABASE_URL}#member={member.filename}"
    return save_bronze(
        content,
        "afac",
        "datatur_database_member",
        "current",
        "xlsx",
        member_url,
        "httpx",
        "Exact XLSX member extracted from the immutable DATATUR ZIP.",
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        relative_dir="afac/database/extracted",
        downloaded_at=None,
    )


def import_browser_downloads(downloads_dir: Path) -> list[Path]:
    """Preserve browser-downloaded annual workbooks in immutable bronze storage."""

    saved: list[Path] = []
    for year, (filename, source_url) in CURRENT_ANNUAL_DOWNLOADS.items():
        source_path = downloads_dir / filename
        if not source_path.is_file():
            continue
        content = source_path.read_bytes()
        _validate_payload(content, "xlsx", source_url)
        saved.append(
            save_bronze(
                content,
                "afac",
                "afac_annual_workbook",
                str(year),
                "xlsx",
                source_url,
                "computer_use",
                "Downloaded by clicking the official annual link in the visible gob.mx catalog.",
                content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                relative_dir=f"afac/{year}",
            )
        )
    return saved


def download_afac_sources() -> dict[str, object]:
    """Download all discoverable historical workbooks and current mirror files."""

    with SourceHttpClient("afac", timeout_seconds=180) as client:
        datatur_content, datatur_path, datatur_metadata = _fetch_catalog(
            client,
            DATATUR_CATALOG_URL,
            "datatur_catalog",
            "current",
            "afac/catalog",
            refresh=True,
        )
        monthly = parse_datatur_catalog(datatur_content)
        archive_content, archive_path, archive_metadata = _fetch_catalog(
            client,
            AFAC_ARCHIVE_URL,
            "wayback_catalog_snapshot",
            AFAC_ARCHIVE_TIMESTAMP[:8],
            "afac/discovery",
            refresh=False,
        )
        archived_historical = parse_historical_catalog(archive_content)
        historical_by_year = {
            artifact.period_id: artifact for artifact in archived_historical
        }
        historical_by_year.update(
            {
                str(year): AfacArtifact(
                    str(year), "afac_annual_workbook", source_url, "xlsx"
                )
                for year, (_, source_url) in CURRENT_ANNUAL_DOWNLOADS.items()
            }
        )
        historical = sorted(
            historical_by_year.values(), key=lambda artifact: artifact.period_id
        )
        database_path, database_metadata = _fetch(
            client,
            AfacArtifact("current", "datatur_database", DATATUR_DATABASE_URL, "zip"),
            refresh=True,
        )
        database_member_path = _preserve_database_member(database_path)
        monthly_paths = [_fetch(client, artifact)[0] for artifact in monthly]
        historical_failures: list[dict[str, str]] = []
        priority = sorted(
            historical,
            key=lambda artifact: (int(artifact.period_id) < 2015, artifact.period_id),
        )
        for artifact in priority:
            try:
                _fetch(client, artifact)
            except UnexpectedAfacPayloadError as exc:
                historical_failures.append(
                    {
                        "period_id": artifact.period_id,
                        "source_url": artifact.source_url,
                        "error": str(exc),
                    }
                )
                break  # A CDN challenge will affect the remaining links in this session.
        historical_paths = [
            found[0]
            for artifact in historical
            if (found := _valid_existing(artifact)) is not None
            and found[0].suffix.casefold() == f".{artifact.extension}"
        ]
    required_annual = [
        artifact for artifact in historical if 2015 <= int(artifact.period_id) <= 2025
    ]
    historical_methods = sorted(
        {
            str(found[1]["download_method"])
            for artifact in historical
            if (found := _valid_existing(artifact)) is not None
        }
    )
    return {
        "network_used": True,
        "access_level": "httpx_datatur_plus_visible_browser_for_gob_attachments",
        "datatur_catalog": datatur_path.relative_to(PATHS.bronze).as_posix(),
        "datatur_catalog_hash": datatur_metadata["sha256"],
        "archive_catalog": archive_path.relative_to(PATHS.bronze).as_posix(),
        "archive_catalog_hash": archive_metadata["sha256"],
        "database_zip": database_path.relative_to(PATHS.bronze).as_posix(),
        "database_member": database_member_path.relative_to(PATHS.bronze).as_posix(),
        "historical_workbook_count": len(historical_paths),
        "historical_period_min": historical[0].period_id,
        "historical_period_max": historical[-1].period_id,
        "historical_download_methods": historical_methods,
        "monthly_bulletin_count": len(monthly_paths),
        "monthly_period_min": monthly[0].period_id,
        "monthly_period_max": monthly[-1].period_id,
        "historical_download_failures": historical_failures,
        "required_coverage_ready": all(
            _valid_existing(artifact) is not None for artifact in required_annual
        )
        and all(path.exists() for path in monthly_paths if "2026" in path.as_posix()),
    }


def main() -> int:
    print(json.dumps(download_afac_sources(), indent=2, ensure_ascii=False, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
