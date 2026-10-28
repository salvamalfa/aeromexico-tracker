"""Reviewed manually obtained official GAP target; never a fresh HTTP/index census."""

import hashlib
import json
import os
import re
from datetime import timedelta
from pathlib import Path

import pandas as pd

from src.source_updates.airport_group_native import GAP_SEPTEMBER_CAPTURE_SHA, GAP_SEPTEMBER_URL
from src.source_updates.calendar import local_time
from src.source_updates.collection import safe_workspace
from src.source_updates.retained import digest

SCOPE = "gap_official_manual_target_v1"
PERIOD = "2026M09"
OBSERVED_DAY = "2026-10-27"  # Native manual-browser recovery confirmed in the trusted handoff.
RAW_SHA = GAP_SEPTEMBER_CAPTURE_SHA
RAW_BYTES = 77223
FIELDS = {"source_scope", "workspace", "run_id", "artifact_item", "manual_original"}


def preflight(binding, candidate):
    if (
        not isinstance(binding, dict)
        or set(binding) != FIELDS
        or binding["source_scope"] != SCOPE
        or not isinstance(binding["run_id"], str)
        or not re.fullmatch(r"[a-f0-9]{32}", binding["run_id"])
        or binding["manual_original"] != "imports/f6k_100626.htm"
        or not isinstance(binding["artifact_item"], str)
        or not binding["artifact_item"]
    ):
        raise ValueError("GAP manual availability requires its exact reviewed target binding")
    root, candidate = safe_workspace(Path(binding["workspace"])), safe_workspace(Path(candidate))
    if root == candidate or root.is_relative_to(candidate) or candidate.is_relative_to(root):
        raise ValueError("GAP manual source collection and candidate must be disjoint")
    return root


def verify(item, result, cutoff):
    from src.source_updates.availability import collection_inventory
    from src.source_updates.checks import verify_bronze

    binding = item["availability"]
    root = preflight(binding, item["workspace"])
    before = collection_inventory(root)
    day = local_time(cutoff).date()
    latest_closed = (day.replace(day=1) - timedelta(days=1)).strftime("%YM%m")
    if (
        item["product"] != "gap_traffic"
        or item["adapter"] != "airport_group"
        or item["period"] != PERIOD
        or latest_closed != PERIOD
        or day.isoformat() != OBSERVED_DAY
        or result.get("product") != item["product"]
        or result.get("period") != PERIOD
        or result.get("status") != "checks_passed"
        or result.get("effective_as_of") != item["candidate_as_of"]
        or local_time(item["candidate_as_of"]) > local_time(cutoff)
    ):
        raise ValueError("GAP manual verification day, closed target, candidate or product differs")
    path = root / binding["manual_original"]
    reference_path = root / "imports/library-original-verification.json"
    receipt_path = root / "receipts" / f"collection-{binding['run_id']}.json"
    manifest = root / "data/bronze/_manifest.jsonl"
    if any(p.is_symlink() or not p.is_file() for p in (path, reference_path, receipt_path, manifest)):
        raise ValueError("GAP manual inputs must be regular physical files without symlinks")
    library_id = os.getxattr(path, "user.library-file-id", follow_symlinks=False).decode()
    if not re.fullmatch(r"libfile_[a-f0-9]{32}", library_id):
        raise ValueError("GAP manual original must preserve its materialized Library identity")
    raw = path.read_bytes()
    if len(raw) != RAW_BYTES or hashlib.sha256(raw).hexdigest() != RAW_SHA:
        raise ValueError("GAP manual original is not the exact reviewed complete received file")
    reference = json.loads(reference_path.read_text())
    if (
        reference.get("library_file_id") != library_id
        or reference.get("name") != "f6k_100626.htm"
        or type(reference.get("version")) is not int
        or reference.get("version") != 0
        or not re.fullmatch(r"file_[a-f0-9]{32}", str(reference.get("backing_file_id", "")))
        or reference.get("bytes") != RAW_BYTES
        or reference.get("sha256") != RAW_SHA
        or reference.get("source_url") != GAP_SEPTEMBER_URL
        or reference.get("binary_identity_with_index_listed_document_claimed") is not False
        or reference.get("materialization_is_not_a_fresh_SEC_HTTP_capture") is not True
    ):
        raise ValueError("GAP Library materialization reference differs from the reviewed manual original")
    receipt_sha = digest(receipt_path)
    receipt = json.loads(receipt_path.read_text())
    expected = dict(
        run_id=binding["run_id"],
        mode="collection",
        status="collected_unvalidated",
        activation="none",
        publication="not_authorized",
    )
    if any(receipt.get(k) != v for k, v in expected.items()) or len(receipt.get("items", [])) != 1:
        raise ValueError("GAP requires the exact single manual-import collection receipt")
    entry = receipt["items"][0]
    if (
        entry.get("id") != binding["artifact_item"]
        or entry.get("product") != "gap_traffic"
        or entry.get("requested_period") != PERIOD
        or entry.get("source_url") != GAP_SEPTEMBER_URL
        or entry.get("status") != "collected_unvalidated"
        or entry.get("sha256") != RAW_SHA
        or entry.get("bytes") != RAW_BYTES
        or entry.get("response_url") is not None
    ):
        raise ValueError("GAP import identity changed or falsely claims a new HTTP response")
    records = verify_bronze(root)
    if set(records) != {entry["source_file"]}:
        raise ValueError("GAP collection must contain only the reviewed original")
    record = records[entry["source_file"]]
    source = root / "data/bronze" / record["source_file"]
    sidecar = Path(str(source) + ".meta.json")
    if any(p.is_symlink() or not p.is_file() for p in (source, sidecar)):
        raise ValueError("GAP original and sidecar must be regular physical files")
    if (
        json.loads(sidecar.read_text()) != record
        or source.read_bytes() != raw
        or record.get("sha256") != RAW_SHA
        or record.get("source_url") != GAP_SEPTEMBER_URL
        or record.get("source_system") != "sec_edgar"
        or record.get("download_method") != "manual"
        or record.get("logical_key") != "sec_edgar|GAP_traffic_0001171843-26-006475|2026M09|htm"
        or local_time(record["downloaded_at"]) > local_time(cutoff)
        or local_time(record["downloaded_at"]).date().isoformat() != OBSERVED_DAY
    ):
        raise ValueError("GAP manual import changed bytes, provenance, alias, logical identity or cutoff")
    native = pd.read_parquet(Path(item["workspace"]) / "data/silver/airport_group_native.parquet")
    if (
        len(native) != 192
        or set(native.source_hash) != {RAW_SHA}
        or set(native.source_file) != {record["source_file"]}
        or set(native.source_system) != {"sec_edgar"}
        or set(native.report_period) != {PERIOD}
        or native.record_id.duplicated().any()
    ):
        raise ValueError("GAP native contribution is not the complete reviewed manual artifact")
    if digest(receipt_path) != receipt_sha or collection_inventory(root) != before:
        raise ValueError("GAP manual source collection changed during verification")
    return dict(
        source_scope=SCOPE,
        collection_receipt_sha256=receipt_sha,
        physical_collection_files=before,
        source_url=GAP_SEPTEMBER_URL,
        source_sha256=RAW_SHA,
        review_period=PERIOD,
        manual_source_observed_on=OBSERVED_DAY,
        manual_source_observation_precision="day",
        manual_imported_at=record["downloaded_at"],
        source_capture_utc=None,
        source_http_status_observed=None,
        manual_import_default_http_metadata_is_not_source_HTTP_evidence=True,
        library_file_id=library_id,
        library_backing_file_id=reference["backing_file_id"],
        library_version_as_reported_by_handoff=reference["version"],
        library_materialization_reference_sha256=digest(reference_path),
        original_bytes=RAW_BYTES,
        EDGAR_index_declared_bytes_reported_by_handoff=77102,
        EDGAR_index_bytes_physically_checked_here=False,
        indexed_binary_identity_claimed=False,
        availability_basis="manually_obtained_official_target_report_verified_not_HTTP_revalidation_or_index_census",
        latest_available_period=None,
        all_sites_latest_revision_census=False,
        first_publication_date=None,
        release_lag_days=None,
        round_as_of=cutoff,
    )
