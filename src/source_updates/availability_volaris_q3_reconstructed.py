"""Day-scoped visible Q3 reconstruction proof; never original SEC or revision census."""

import json
import re
from pathlib import Path

import pandas as pd

from src.source_updates.calendar import local_time
from src.source_updates.closed_editions import binding_fields, evidence
from src.source_updates.collection import safe_workspace
from src.source_updates.retained import digest
from src.source_updates.volaris_q3_inputs import ROLE, VERIFIED_AT, decode, validate_import_artifact
from src.source_updates.volaris_q3_source import read

SCOPE = "volaris_Q3_visible_reconstruction_target_v1"


def preflight(binding, candidate):
    if not (
        isinstance(binding, dict)
        and binding_fields(binding, {"source_scope", "workspace", "run_id"})
        and binding["source_scope"] == SCOPE
        and isinstance(binding["run_id"], str)
        and re.fullmatch(r"[a-f0-9]{32}", binding["run_id"])
    ):
        raise ValueError("Volaris Q3 requires its exact physical authorized-reconstruction import")
    root, target = safe_workspace(Path(binding["workspace"])), safe_workspace(Path(candidate))
    if root == target or root.is_relative_to(target) or target.is_relative_to(root):
        raise ValueError("Volaris import and certified candidate must be disjoint")
    return root


def verify(item, result, cutoff):
    from src.source_updates.availability import collection_inventory
    from src.source_updates.carrier_source_contract import identifier

    binding = item["availability"]
    root = preflight(binding, item["workspace"])
    before = collection_inventory(root)
    path = root / "receipts" / f"volaris-reconstruction-import-{binding['run_id']}.json"
    receipt = json.loads(path.read_text())
    if not (
        item["product"] == "volaris_sec"
        and item["adapter"] == "carrier_source"
        and item["period"] == "2026Q3"
        and result.get("period") == "2026Q3"
        and result.get("source_representation") == "authorized_visible_reconstruction"
        and result.get("status") == "checks_passed"
        and receipt.get("product") == "volaris_sec"
        and receipt.get("period") == "2026Q3"
        and receipt.get("run_id") == binding["run_id"]
        and receipt.get("mode") == "reconstruction_import"
        and receipt.get("status") == "imported_reconstruction_unvalidated"
        and receipt.get("source_representation") == "authorized_visible_reconstruction"
        and receipt.get("source_original_sha256") is None
        and receipt.get("activation") == "none"
        and receipt.get("publication") == "not_authorized"
        and receipt.get("network_requests") == 0
        and set(receipt.get("records", {})) == {ROLE}
        and local_time(VERIFIED_AT) <= local_time(receipt["imported_at"]) <= local_time(cutoff)
        and local_time(item["candidate_as_of"]) <= local_time(cutoff)
        and result.get("effective_as_of") == item["candidate_as_of"]
        and digest(root / "data/bronze/_manifest.jsonl") == receipt.get("manifest_sha256")
    ):
        raise ValueError("Volaris Q3 import identity, chronology or actual visible-read day differs")
    source = receipt["records"][ROLE]
    physical = validate_import_artifact(root / "data/bronze", source)
    if source["downloaded_at"] != receipt["imported_at"]:
        raise ValueError("Volaris import timestamp differs from its actual packet provenance")
    frame, proof = read({ROLE: (physical.read_bytes(), source)}, "2026Q3")
    _, expected_import_proof = decode(physical.read_bytes())
    if receipt["proof"] != expected_import_proof:
        raise ValueError("Volaris import proof changed from the verified immutable packet")
    frame["record_id"] = frame.apply(identifier, axis=1)
    native = pd.read_parquet(Path(item["workspace"]) / "data/silver/volaris_sec_source_native.parquet")
    try:
        pd.testing.assert_frame_equal(native, frame.reset_index(drop=True), check_exact=True)
    except AssertionError as exc:
        raise ValueError("Volaris Q3 native candidate differs from the actual reconstruction") from exc
    if before != collection_inventory(root):
        raise ValueError("Volaris Q3 import changed during its availability check")
    return {
        "validated_closed_edition": evidence(
            item, cutoff, VERIFIED_AT, precision="timestamp", source_url=source["source_url"]
        ),
        "source_scope": SCOPE,
        "source_representation": "authorized_visible_reconstruction",
        "source_url": source["source_url"],
        "reconstructed_artifact_sha256": source["sha256"],
        "source_original_sha256": None,
        "source_http_status_observed": None,
        "source_visible_verified_at": VERIFIED_AT,
        "representation_imported_at": receipt["imported_at"],
        "source_observation_semantics": proof["source_observation_semantics"],
        "availability_basis": (
            "authorized_visible_target_reconstruction_not_original_download_or_revision_census"
        ),
        "review_period": "2026Q3",
        "first_publication_date": None,
        "release_lag_days": None,
        "latest_available_period": None,
        "all_sites_latest_revision_census": False,
        "physical_import_files": before,
        "round_as_of": cutoff,
        "provenance_warning": proof["provenance_warning"],
    }
