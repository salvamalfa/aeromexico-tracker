"""Official airport workbook downloaded in a browser; text index is not original HTML."""

import hashlib
import io
import json
import os
import re
from pathlib import Path
from zipfile import ZipFile

import pandas as pd

from src.source_updates import afac_airports
from src.source_updates.availability_afac_airports import ENTRY, MONTHS, TABLE
from src.source_updates.calendar import local_time
from src.source_updates.collection import safe_workspace, validate_url
from src.source_updates.retained import digest

SCOPE = "afac_airports_browser_download_v1"
FIELDS = {"source_scope", "workspace", "run_id", "artifact_item", "browser_packet"}


def preflight(binding, candidate):
    if (
        set(binding) != FIELDS
        or binding.get("source_scope") != SCOPE
        or not re.fullmatch(r"[a-f0-9]{32}", str(binding["run_id"]))
        or not re.fullmatch(r"imports/[A-Za-z0-9_-]+\.zip", str(binding["browser_packet"]))
    ):
        raise ValueError("AFAC manual availability requires an exact native-download handoff")
    root, target = safe_workspace(Path(binding["workspace"])), safe_workspace(Path(candidate))
    if root == target or root.is_relative_to(target) or target.is_relative_to(root):
        raise ValueError("AFAC manual collection and candidate must be disjoint")
    return root


def packet(path, cutoff):
    identity = os.getxattr(path, "user.library-file-id", follow_symlinks=False).decode()
    if not re.fullmatch(r"libfile_[a-f0-9]{32}", identity):
        raise ValueError("AFAC browser packet requires its actual materialized Library identity")
    with ZipFile(io.BytesIO(path.read_bytes())) as archive:
        names = archive.namelist()
        if (
            len(names) != 3
            or len(set(names)) != 3
            or sum(i.file_size for i in archive.infolist()) > 2_000_000
        ):
            raise ValueError(
                "AFAC handoff must contain only workbook, index snapshot and acquisition manifest"
            )
        manifest = json.loads(archive.read("acquisition-manifest.json"))
        name = manifest["name"]
        if set(names) != {name, "afac-statistics-index.txt", "acquisition-manifest.json"}:
            raise ValueError("Unexpected AFAC handoff members")
        original, index = archive.read(name), archive.read("afac-statistics-index.txt").decode("utf-8-sig")
    url = manifest["download_url"]
    validate_url(url, ["www.gob.mx"])
    match = re.fullmatch(
        r"https://www\.gob\.mx/cms/uploads/attachment/file/\d+/"
        r"producto-aeropuertos?-2006-(20\d{2})-([a-z]{3})-(\d{8})\.xlsx",
        url,
    )
    if not match or match[2] not in MONTHS or url.rsplit("/", 1)[-1] != name:
        raise ValueError("AFAC browser file is not the exact airport-product workbook")
    period = f"{match[1]}M{MONTHS.index(match[2]) + 1:02d}"
    airport_books = re.findall(
        r"/url: (https://www\.gob\.mx/cms/uploads/attachment/file/\d+/"
        r"producto-aeropuertos?-2006-20\d{2}-[a-z]{3}-\d{8}\.xlsx)", index
    )
    observed = local_time(manifest["download_completed_utc"])
    if (
        manifest.get("index_url") != ENTRY
        or manifest.get("bytes") != len(original)
        or manifest.get("sha256") != hashlib.sha256(original).hexdigest()
        or observed > local_time(cutoff)
        or observed.date() != local_time(cutoff).date()
        or 'heading "Estadísticas" [level=1]' not in index
        or "Estadística Operacional de Aeropuertos. Statistics by Airport" not in index
        or index.count("/url: " + url + "\n") != 1
        or airport_books != [url]
    ):
        raise ValueError("AFAC browser origin, index snapshot, bytes or real observation day differs")
    # Corroborate both published language labels/editions without fabricating HTML.
    for language in ("es", "en"):
        pattern = (
            r"/url: https://www\.gob\.mx/cms/uploads/attachment/file/\d+/"
            rf"producto-aeropuertos-{language}-{match[2]}-{match[1][-2:]}-{match[3]}\.pdf"
        )
        if len(re.findall(pattern, index)) != 1:
            raise ValueError("AFAC browser index does not corroborate the same airport edition")
    return (
        original,
        manifest,
        dict(
            packet_sha256=digest(path),
            container_library_file_id=identity,
            index_snapshot_sha256=hashlib.sha256(index.encode()).hexdigest(),
            index_representation="browser_accessibility_snapshot_text_not_original_HTML",
            source_observed_at=manifest["download_completed_utc"],
            period=period,
            source_http_status_observed=None,
            source_capture_method="native_browser_download",
        ),
    )


def verify(item, result, cutoff):
    from src.source_updates.availability import collection_inventory
    from src.source_updates.checks import verify_bronze

    binding = item["availability"]
    root = preflight(binding, item["workspace"])
    before = collection_inventory(root)
    original, manifest, proof = packet(root / binding["browser_packet"], cutoff)
    path = root / "receipts" / f"collection-{binding['run_id']}.json"
    receipt = json.loads(path.read_text())
    if (
        (item["product"], item["adapter"], item["period"]) != ("afac_airports", "retained", proof["period"])
        or receipt.get("run_id") != binding["run_id"]
        or receipt.get("mode") != "collection"
        or receipt.get("status") != "collected_unvalidated"
        or len(receipt.get("items", [])) != 1
        or receipt.get("activation") != "none"
        or receipt.get("publication") != "not_authorized"
        or local_time(item["candidate_as_of"]) > local_time(cutoff)
    ):
        raise ValueError("AFAC manual collection/product/period/cutoff differs")
    entry = receipt["items"][0]
    records = verify_bronze(root)
    if len(records) != 1 or entry.get("source_file") not in records:
        raise ValueError("AFAC manual collection must bind its one original workbook")
    record = records[entry["source_file"]]
    source = root / "data/bronze" / record["source_file"]
    sidecar = Path(str(source) + ".meta.json")
    if (
        entry.get("id") != binding["artifact_item"]
        or entry.get("product") != "afac_airports"
        or entry.get("requested_period") != proof["period"]
        or entry.get("status") != "collected_unvalidated"
        or entry.get("response_url") is not None
        or entry.get("source_capture_utc") is not None
        or entry.get("source_http_status_observed") is not None
        or entry.get("timestamp_semantics") != "local_manual_import_not_source_HTTP_capture"
        or any(row.get("source_url") != manifest["download_url"] for row in (entry, record))
        or any(row.get("sha256") != manifest["sha256"] for row in (entry, record))
        or record.get("source_system") != "afac"
        or record.get("download_method") != "manual"
        or record.get("http_status") != 0
        or any(row.get("bytes") != len(original) for row in (entry, record))
        or json.loads(sidecar.read_text()) != record
        or len((root / "data/bronze/_manifest.jsonl").read_text().splitlines()) != 1
        or not local_time(proof["source_observed_at"])
        <= local_time(record["downloaded_at"])
        <= local_time(cutoff)
        or not local_time(receipt["started_at"])
        <= local_time(record["downloaded_at"])
        <= local_time(receipt["finished_at"])
        <= local_time(cutoff)
        or source.read_bytes() != original
    ):
        raise ValueError("AFAC manual import changed original bytes, source identity, method or chronology")
    frame, details = afac_airports.parse(original, item["period"], record)
    native = pd.read_parquet(Path(item["workspace"]) / "data" / TABLE)
    try:
        pd.testing.assert_frame_equal(native[list(frame.columns)], frame, check_exact=True)
    except (AssertionError, KeyError) as exc:
        raise ValueError("AFAC manual native differs from full original workbook replay") from exc
    if (
        result.get("status") != "checks_passed"
        or result.get("product") != "afac_airports"
        or result.get("effective_as_of") != item["candidate_as_of"]
        or result.get("report_period") != item["period"]
        or any(result.get(k) != details[k] for k in ("months_validated", "visible_crosschecks", "rows"))
        or collection_inventory(root) != before
    ):
        raise ValueError("AFAC manual native scope or immutable source collection changed")
    return dict(
        proof,
        source_scope=SCOPE,
        collection_receipt_sha256=digest(path),
        source_artifact_sha256=manifest["sha256"],
        source_artifact_url=manifest["download_url"],
        source_imported_at=record["downloaded_at"],
        latest_available_period=item["period"],
        round_as_of=cutoff,
        physical_collection_files=before,
        reported_workbook_verified=True,
        complete_observational_census_claimed=False,
        first_publication_date=None,
        release_lag_days=None,
        availability_basis="official_browser_download_with_text_index_snapshot_not_HTTP_recapture",
    )
