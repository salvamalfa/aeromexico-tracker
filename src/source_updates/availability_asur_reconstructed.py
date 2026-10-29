"""Day-scoped ASUR visible-reconstruction evidence, never SEC HTTP/original proof."""

import json
import os
import re
from pathlib import Path

import pandas as pd

from src.source_updates.asur_reconstructed import ALIAS, PERIOD, URL, read
from src.source_updates.asur_reconstruction_inputs import FILES, OBSERVED_AT, validate_record
from src.source_updates.calendar import local_time
from src.source_updates.checks import verify_bronze
from src.source_updates.closed_editions import binding_fields, evidence
from src.source_updates.collection import safe_workspace
from src.source_updates.retained import digest

SCOPE = "asur_visible_reconstruction_target_v1"
FIELDS = {"source_scope", "workspace", "run_id"}


def preflight(binding, candidate):
    if not (
        isinstance(binding, dict)
        and binding_fields(binding, FIELDS)
        and binding["source_scope"] == SCOPE
        and isinstance(binding["run_id"], str)
        and re.fullmatch(r"[a-f0-9]{32}", binding["run_id"])
    ):
        raise ValueError("ASUR reconstruction requires its exact physical offline-import binding")
    root, candidate = safe_workspace(Path(binding["workspace"])), safe_workspace(Path(candidate))
    if root == candidate or root.is_relative_to(candidate) or candidate.is_relative_to(root):
        raise ValueError("ASUR reconstruction import and source candidate must be disjoint")
    return root


def verify(item, result, cutoff):
    from src.source_updates.airport_group_native import GRAIN
    from src.source_updates.availability import collection_inventory
    from src.transform.stage9_lineage import add_record_ids

    binding = item["availability"]
    root = preflight(binding, item["workspace"])
    before = collection_inventory(root)
    path = root / "receipts" / f"asur-reconstruction-import-{binding['run_id']}.json"
    if path.is_symlink() or not path.is_file():
        raise ValueError("ASUR requires its real physical reconstruction import receipt")
    receipt_sha = digest(path)
    receipt = json.loads(path.read_text())
    if not (
        item["product"] == "asur_traffic"
        and item["adapter"] == "airport_group"
        and item["period"] == PERIOD
        and result.get("status") == "checks_passed"
        and result.get("product") == "asur_traffic"
        and result.get("period") == PERIOD
        and result.get("source_representation") == "authorized_visible_reconstruction"
        and result.get("effective_as_of") == item["candidate_as_of"]
        and local_time(item["candidate_as_of"]) <= local_time(cutoff)
        and receipt.get("mode") == "reconstruction_import"
        and receipt.get("status") == "imported_reconstruction_unvalidated"
        and receipt.get("run_id") == binding["run_id"]
        and receipt.get("product") == "asur_traffic"
        and receipt.get("period") == PERIOD
        and receipt.get("source_representation") == "authorized_visible_reconstruction"
        and receipt.get("source_observed_at") == OBSERVED_AT
        and receipt.get("is_original_SEC_HTML") is False
        and receipt.get("source_original_sha256") is None
        and receipt.get("network_requests") == 0
        and receipt.get("activation") == "none"
        and receipt.get("publication") == "not_authorized"
        and local_time(receipt["source_observed_at"]) <= local_time(cutoff)
        and local_time(receipt["imported_at"]) <= local_time(cutoff)
        and local_time(receipt["imported_at"]) >= local_time(receipt["source_observed_at"])
        and digest(root / "data/bronze/_manifest.jsonl") == receipt["manifest_sha256"]
    ):
        raise ValueError("ASUR reconstruction identity, scope, observation day or immutable import differs")
    records = verify_bronze(root)
    if set(receipt.get("records", {})) != set(FILES) or len(records) != 4:
        raise ValueError("ASUR requires all four physical reconstructed representations")
    inputs = {}
    for role, row in receipt["records"].items():
        validate_record(row)
        if row != records.get(row["source_file"]) or row["representation_role"] != role:
            raise ValueError("ASUR import selection differs from its physical manifest")
        source = root / "data/bronze" / row["source_file"]
        sidecar = Path(str(source) + ".meta.json")
        if source.is_symlink() or sidecar.is_symlink() or json.loads(sidecar.read_text()) != row:
            raise ValueError("ASUR representation sidecar or regular-file identity changed")
        if (
            os.getxattr(source, "user.library-file-id", follow_symlinks=False).decode()
            != row["library_file_id"]
        ):
            raise ValueError("ASUR physical reconstruction lost its actual Library identity")
        if local_time(row["downloaded_at"]) != local_time(receipt["imported_at"]):
            raise ValueError("ASUR import timestamp is not a source HTTP capture")
        inputs[role] = source.read_bytes(), row
    frame, proof = read(inputs, PERIOD)
    if receipt["source_observed_at"] != proof["source_observed_at"]:
        raise ValueError("ASUR import cannot change the immutable representation observation time")
    if receipt.get("library_file_ids") != {role: row[1]["library_file_id"] for role, row in inputs.items()}:
        raise ValueError("ASUR receipt Library identities differ from its verified physical representations")
    frame = add_record_ids(frame, table_name="airport_group_native", natural_key_columns=GRAIN)
    native = pd.read_parquet(Path(item["workspace"]) / "data/silver/airport_group_native.parquet")
    try:
        pd.testing.assert_frame_equal(native, frame, check_exact=True)
    except AssertionError as exc:
        raise ValueError(
            "ASUR candidate contribution differs from the complete reconstructed source"
        ) from exc
    if (
        set(native.source_system) != {ALIAS}
        or digest(path) != receipt_sha
        or before != collection_inventory(root)
    ):
        raise ValueError("ASUR reconstruction import changed during verification")
    return {
        "validated_closed_edition": evidence(
            item, cutoff, OBSERVED_AT, precision="timestamp", source_url=URL
        ),
        "source_scope": SCOPE,
        "source_url": URL,
        "review_period": PERIOD,
        "source_representation": "authorized_visible_reconstruction",
        "is_original_SEC_HTML": False,
        "upstream_original_sha256": None,
        "source_http_status_observed": None,
        "source_capture_utc": None,
        "source_visible_observed_at": receipt["source_observed_at"],
        "source_observed_local_day": local_time(OBSERVED_AT).date().isoformat(),
        "representation_imported_at": receipt["imported_at"],
        "availability_basis": (
            "authorized_visible_target_reconstruction_verified_not_original_download_or_revision_census"
        ),
        "reconstruction_import_receipt_sha256": receipt_sha,
        "physical_collection_files": before,
        "reconstructed_artifact_sha256": proof["reconstructed_artifact_sha256"],
        "all_sites_latest_revision_census": False,
        "latest_available_period": None,
        "first_publication_date": None,
        "release_lag_days": None,
        "round_as_of": cutoff,
        "provenance_warning": proof["provenance_warning"],
    }
