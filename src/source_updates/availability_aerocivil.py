"""Retained Aerocivil maximum-month query, never a new capture or completeness claim."""

from __future__ import annotations

import json
import re
from pathlib import Path

from src.source_updates import aerocivil_metadata
from src.source_updates import availability as physical
from src.source_updates.aerocivil import OUTPUTS
from src.source_updates.aerocivil_operational import SCOPE as CANDIDATE_SCOPE
from src.source_updates.calendar import local_time
from src.source_updates.collection import safe_workspace

SCOPE = "aerocivil_retained_maximum_month_v1"
FIELDS = {"source_scope", "workspace", "collection_id"}


def preflight(binding, candidate):
    if (
        not isinstance(binding, dict)
        or set(binding) != FIELDS
        or binding.get("source_scope") != SCOPE
        or not isinstance(binding.get("workspace"), str)
        or not isinstance(binding.get("collection_id"), str)
        or not re.fullmatch(r"[a-f0-9]{32}", binding["collection_id"])
    ):
        raise ValueError("Aerocivil availability requires its exact retained-query scope and collection ID")
    root = safe_workspace(Path(binding["workspace"]))
    candidate = safe_workspace(Path(candidate))
    if root == candidate or root.is_relative_to(candidate) or candidate.is_relative_to(root):
        raise ValueError("Aerocivil retained query and certified candidate must be disjoint")
    return root


def verify(item, result, cutoff):
    """Bind a successful native replay to a physically reproducible retained query."""
    root = preflight(item["availability"], item["workspace"])
    candidate = safe_workspace(Path(item["workspace"]))
    period = item.get("period")
    if (
        (item.get("product"), item.get("adapter")) != ("aerocivil", "aerocivil")
        or not isinstance(period, str)
        or not re.fullmatch(r"20\d{2}M(?:0[1-9]|1[0-2])", period)
        or result.get("status") != "checks_passed"
        or result.get("period") != period
        or result.get("scope") != CANDIDATE_SCOPE
        or result.get("missing_operator_is_not_zero") is not True
        or result.get("activation") != "none"
        or result.get("publication") != "not_authorized"
        or result.get("effective_as_of") != item.get("candidate_as_of")
        or result.get("collection_run_id") != item.get("receipt_id")
    ):
        raise ValueError("Aerocivil availability requires the checked native month and exact candidate scope")
    if local_time(item["candidate_as_of"]) > local_time(cutoff):
        raise ValueError("Aerocivil candidate cutoff is after the requested round cutoff")
    outputs = result.get("output_sha256")
    if not isinstance(outputs, dict) or set(outputs) != set(OUTPUTS):
        raise ValueError("Aerocivil replay must bind every physical native output hash")
    collection_before = physical.collection_inventory(root)
    candidate_before = physical.collection_inventory(candidate)
    if any(
        not isinstance(value, str)
        or not re.fullmatch(r"[a-f0-9]{64}", value)
        or candidate_before.get(f"data/{name}.parquet") != value
        for name, value in outputs.items()
    ):
        raise ValueError("Aerocivil replay output hashes differ from the physical native candidate")
    collection = item["availability"]["collection_id"]
    receipt_path = root / "receipts" / f"collection-{collection}.json"
    receipt_sha = physical.sha(receipt_path)
    receipt = json.loads(receipt_path.read_text())
    expected_receipt = dict(
        run_id=collection,
        mode="collection",
        status="collected_unvalidated",
        activation="none",
        publication="not_authorized",
    )
    if (
        any(receipt.get(key) != value for key, value in expected_receipt.items())
        or not isinstance(receipt.get("items"), list)
        or len(receipt["items"]) != 1
        or not isinstance(receipt["items"][0], dict)
    ):
        raise ValueError("Aerocivil requires a complete immutable single-query collection receipt")
    row = receipt["items"][0]
    if row.get("requested_period") != "current":
        raise ValueError("Aerocivil maximum-month discovery must preserve its native current-query role")
    relative = Path(row.get("source_file", ""))
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError("Aerocivil retained query must use its physical Bronze-relative source path")
    observation = aerocivil_metadata.availability(root, period[:4], cutoff, collection)
    if (
        observation["status"] != "availability_observed"
        or observation["scope"] != f"AMX_SLI_source_derived_operator_codes_only_{period[:4]}"
        or observation["latest_available_period"] != period
        or observation["collection_receipt_sha256"] != receipt_sha
    ):
        raise ValueError("Aerocivil native month is not the maximum in the retained same-year query")
    manifest = root / "data/bronze/_manifest.jsonl"
    records = [json.loads(line) for line in manifest.read_text().splitlines()]
    if len(records) != 1 or records[0].get("source_file") != observation["source_file"]:
        raise ValueError("Aerocivil retained query requires exactly its own physical manifest record")
    record = records[0]
    path = root / "data/bronze" / observation["source_file"]
    sidecar = Path(str(path) + ".meta.json")
    if (
        json.loads(sidecar.read_text()) != record
        or record.get("http_status") != 200
        or record.get("download_method") != "httpx"
        or record.get("logical_key") != "aerocivil|latest_available_operator_month|current|json"
        or record.get("sha256") != observation["source_hash"]
        or physical.sha(path) != observation["source_hash"]
        or type(row.get("bytes")) is not int
        or row["bytes"] != path.stat().st_size
        or record.get("bytes") != row["bytes"]
    ):
        raise ValueError(
            "Aerocivil retained query sidecar, manifest, hash, bytes or physical capture changed"
        )
    observed = local_time(observation["downloaded_at"])
    if (
        not local_time(receipt["started_at"])
        <= observed
        <= local_time(receipt["finished_at"])
        <= local_time(cutoff)
    ):
        raise ValueError("Aerocivil retained query chronology is inconsistent with the round cutoff")
    # Match availability.artifact(): history is reproducible, but only the
    # round's local capture day establishes latest availability for that round.
    if observed.date() != local_time(cutoff).date():
        raise ValueError("Aerocivil latest availability requires the round's local capture date")
    if (
        physical.collection_inventory(root) != collection_before
        or physical.collection_inventory(candidate) != candidate_before
        or physical.sha(receipt_path) != receipt_sha
    ):
        raise ValueError("Aerocivil retained query or native candidate changed during read-only verification")
    return {
        **observation,
        "source_scope": SCOPE,
        "latest_source_availability_verified": True,
        "source_observation_current_for_round": observed.date() == local_time(cutoff).date(),
        "source_availability_observed_at": observation["downloaded_at"],
        "observed_at": observation["downloaded_at"],
        "round_as_of": cutoff,
        "availability_basis": "physically_replayed_retained_maximum_month_not_current_query",
        "latest_semantics": "maximum_in_retained_AMX_SLI_query_at_original_observation_time",
        "discovery_url": observation["source_url"],
        "discovery_contract_product": "aerocivil",
        "source_artifact_sha256": observation["source_hash"],
        "physical_collection_files": collection_before,
        "native_candidate_files_unchanged": len(candidate_before),
        "complete_quarter_verified": False,
        "missing_operator_is_not_zero": True,
        "new_source_capture": False,
    }
