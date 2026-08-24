"""Download immutable SEC filing indexes and non-graphic documents."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path
import re
from typing import Any, Callable
from urllib.parse import quote

from src.common.http import SourceHttpClient
from src.common.storage import find_bronze_by_source_url, save_bronze
from src.config import CIK_AEROMEXICO, PATHS


ACCESSION_PATTERN = re.compile(r"^\d{10}-\d{2}-\d{6}$")
DOWNLOADABLE_EXTENSIONS = frozenset(
    {".htm", ".html", ".txt", ".xml", ".xsd", ".xbrl", ".json", ".pdf"}
)
TEXT_EXTENSIONS = frozenset({".htm", ".html", ".txt", ".xml", ".xsd", ".xbrl"})


@dataclass(frozen=True, slots=True)
class DownloadedDocument:
    accession_number: str
    form_type: str
    archive_filename: str
    source_url: str
    source_file: str
    source_hash: str
    content_type: str
    bytes: int
    ingested_at: str
    is_primary_document: bool
    download_method: str
    carrier_key: str = "AEROMEXICO"
    cik: str = CIK_AEROMEXICO

    def as_record(self) -> dict[str, object]:
        return asdict(self)


def accession_without_dashes(accession_number: str) -> str:
    if not ACCESSION_PATTERN.fullmatch(accession_number):
        raise ValueError(f"Invalid SEC accession number: {accession_number!r}")
    return accession_number.replace("-", "")


def normalize_cik(cik: str) -> str:
    """Return a ten-digit CIK after strict numeric validation."""

    value = cik.strip()
    if not value.isdigit() or len(value) > 10:
        raise ValueError(f"Invalid SEC CIK: {cik!r}")
    return value.zfill(10)


def filing_base_url(
    accession_number: str, *, cik: str = CIK_AEROMEXICO
) -> str:
    archive_cik = str(int(normalize_cik(cik)))
    return (
        f"https://www.sec.gov/Archives/edgar/data/{archive_cik}/"
        f"{accession_without_dashes(accession_number)}"
    )


def filing_index_url(
    accession_number: str, *, cik: str = CIK_AEROMEXICO
) -> str:
    return f"{filing_base_url(accession_number, cik=cik)}/index.json"


def filing_document_url(
    accession_number: str,
    filename: str,
    *,
    cik: str = CIK_AEROMEXICO,
) -> str:
    if Path(filename).name != filename or filename in {".", ".."}:
        raise ValueError(f"Unsafe SEC archive filename: {filename!r}")
    return f"{filing_base_url(accession_number, cik=cik)}/{quote(filename)}"


def _metadata_for(path: Path) -> dict[str, Any]:
    metadata_path = path.with_suffix(path.suffix + ".meta.json")
    return json.loads(metadata_path.read_text(encoding="utf-8"))


def _fetch_immutable(
    client: SourceHttpClient,
    *,
    url: str,
    accession_number: str,
    entity: str,
    ext: str,
    notes: str,
    carrier_key: str = "AEROMEXICO",
) -> tuple[Path, dict[str, Any]]:
    existing = find_bronze_by_source_url(url)
    if existing is not None:
        return existing
    response = client.request(
        "GET",
        url,
        headers={"Accept-Encoding": "gzip, deflate", "Accept": "*/*"},
    )
    saved = save_bronze(
        response.content,
        "sec",
        entity,
        accession_number,
        ext,
        url,
        "httpx",
        http_status=response.status_code,
        content_type=response.headers.get("content-type", "application/octet-stream"),
        downloaded_at=datetime.now(UTC),
        notes=notes,
        relative_dir=(
            f"sec/filings/{accession_number}"
            if carrier_key == "AEROMEXICO"
            else f"sec/filings/{carrier_key.lower()}/{accession_number}"
        ),
    )
    return saved, _metadata_for(saved)


def download_filing_index(
    client: SourceHttpClient,
    accession_number: str,
    *,
    cik: str = CIK_AEROMEXICO,
    carrier_key: str = "AEROMEXICO",
) -> tuple[dict[str, Any], Path, dict[str, Any]]:
    url = filing_index_url(accession_number, cik=cik)
    path, metadata = _fetch_immutable(
        client,
        url=url,
        accession_number=accession_number,
        entity=f"{accession_number}_index",
        ext="json",
        notes=f"SEC filing directory index for accession {accession_number}.",
        carrier_key=carrier_key,
    )
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload.get("directory", {}).get("item"), list):
        raise ValueError(f"Unexpected SEC index schema for {accession_number}")
    return payload, path, metadata


def _downloadable_items(index_payload: dict[str, Any]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for item in index_payload["directory"]["item"]:
        name = str(item.get("name", ""))
        if not name or Path(name).suffix.lower() not in DOWNLOADABLE_EXTENSIONS:
            continue
        items.append(item)
    return items


def download_filing(
    client: SourceHttpClient,
    *,
    accession_number: str,
    form_type: str,
    primary_document: str,
    cik: str = CIK_AEROMEXICO,
    carrier_key: str = "AEROMEXICO",
    include_document: Callable[[str], bool] | None = None,
) -> list[DownloadedDocument]:
    """Download an index and every non-graphic document listed by SEC."""

    index_payload, index_path, index_metadata = download_filing_index(
        client, accession_number, cik=cik, carrier_key=carrier_key
    )
    records = [
        DownloadedDocument(
            accession_number=accession_number,
            form_type=form_type,
            archive_filename="index.json",
            source_url=filing_index_url(accession_number, cik=cik),
            source_file=index_path.relative_to(PATHS.bronze).as_posix(),
            source_hash=str(index_metadata["sha256"]),
            content_type=str(index_metadata["content_type"]),
            bytes=int(index_metadata["bytes"]),
            ingested_at=str(index_metadata["downloaded_at"]),
            is_primary_document=False,
            download_method=str(index_metadata["download_method"]),
            carrier_key=carrier_key,
            cik=normalize_cik(cik),
        )
    ]
    for item in _downloadable_items(index_payload):
        filename = str(item["name"])
        if include_document is not None and not include_document(filename):
            continue
        url = filing_document_url(accession_number, filename, cik=cik)
        suffix = Path(filename).suffix.lower().lstrip(".")
        path, metadata = _fetch_immutable(
            client,
            url=url,
            accession_number=accession_number,
            entity=f"{accession_number}_{Path(filename).stem}",
            ext=suffix,
            notes=(
                f"SEC {form_type} document {filename} from accession "
                f"{accession_number}; archive type={item.get('type', '')}."
            ),
            carrier_key=carrier_key,
        )
        records.append(
            DownloadedDocument(
                accession_number=accession_number,
                form_type=form_type,
                archive_filename=filename,
                source_url=url,
                source_file=path.relative_to(PATHS.bronze).as_posix(),
                source_hash=str(metadata["sha256"]),
                content_type=str(metadata["content_type"]),
                bytes=int(metadata["bytes"]),
                ingested_at=str(metadata["downloaded_at"]),
                is_primary_document=filename.casefold() == primary_document.casefold(),
                download_method=str(metadata["download_method"]),
                carrier_key=carrier_key,
                cik=normalize_cik(cik),
            )
        )
    return records


def document_text(record: DownloadedDocument) -> str:
    """Decode one textual filing artifact for classification or parsing."""

    if Path(record.archive_filename).suffix.lower() not in TEXT_EXTENSIONS:
        return ""
    content = (PATHS.bronze / record.source_file).read_bytes()
    if hashlib.sha256(content).hexdigest() != record.source_hash:
        raise ValueError(f"Bronze hash mismatch for {record.source_file}")
    return content.decode("utf-8", errors="replace")
