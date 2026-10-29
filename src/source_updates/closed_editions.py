"""Reuse three reviewed closed editions; observation and revision checks stay separate."""

import json
import re
from datetime import date
from pathlib import Path

from src.source_updates.calendar import local_time
from src.source_updates.checks import period_end
from src.source_updates.retained import digest

POLICY = "validated_closed_editions_20261028_v1"
SCOPES = {
    "gap_official_manual_target_v1": ("gap_traffic", "airport_group", "2026M09"),
    "asur_visible_reconstruction_target_v1": ("asur_traffic", "airport_group", "2026M09"),
    "volaris_Q3_visible_reconstruction_target_v1": ("volaris_sec", "carrier_source", "2026Q3"),
}


def binding_fields(binding, required):
    if not isinstance(binding, dict):
        return False
    if "known_new_edition" in binding:
        raise ValueError(
            "Known new edition requires a new source validation; retained edition cannot clear it"
        )
    return set(binding) in (required, required | {"revision_check"})


def revision_check(binding, item, cutoff, source_url, original_sha):
    """Read an optional real collection, never a caller's 'unchanged/latest' flag."""
    from src.source_updates.collection import safe_workspace

    ref = binding.get("revision_check")
    if ref is None:
        return {"status": "not_checked", "checked_at": None, "latest_edition_verified": False}
    if (
        not isinstance(ref, dict)
        or set(ref) != {"workspace", "run_id", "item_id"}
        or not re.fullmatch(r"[a-f0-9]{32}", str(ref["run_id"]))
    ):
        raise ValueError("Revision check requires an exact physical collection reference")
    root = safe_workspace(Path(ref["workspace"]))
    path = root / "receipts" / f"collection-{ref['run_id']}.json"
    if path.is_symlink() or not path.is_file():
        raise ValueError("Revision collection must be a regular physical receipt")
    receipt = json.loads(path.read_text())
    started, finished = (local_time(receipt[k]) for k in ("started_at", "finished_at"))
    if (
        receipt.get("run_id") != ref["run_id"]
        or receipt.get("mode") != "collection"
        or receipt.get("activation") != "none"
        or receipt.get("publication") != "not_authorized"
        or not started <= finished <= local_time(cutoff)
    ):
        raise ValueError("Revision collection identity, chronology or authority differs")
    rows = [r for r in receipt["items"] if r.get("id") == ref["item_id"]]
    if len(rows) != 1:
        raise ValueError("Revision collection item must be unique")
    row = rows[0]
    if (row.get("product"), row.get("requested_period"), row.get("source_url")) != (
        item["product"],
        item["period"],
        source_url,
    ):
        raise ValueError("Revision observation is not the same document, product and period")
    proof = dict(
        checked_at=receipt["finished_at"],
        collection_receipt_sha256=digest(path),
        http_status=row.get("http_status"),
        latest_edition_verified=False,
    )
    if row.get("status") == "access_or_payload_failed":
        failed = row.get("failed_response")
        if failed is not None:
            failure = safe_file(root, failed["file"])
            if digest(failure) != failed["sha256"] or failure.stat().st_size != failed["bytes"]:
                raise ValueError("Revision failed-response evidence changed")
        return dict(proof, status="failed", error_type=row.get("error_type"), failed_response=failed)
    if row.get("status") != "collected_unvalidated":
        raise ValueError("Revision observation does not contain a data response or explicit failure")
    source = safe_file(root, "data/bronze/" + row["source_file"])
    if digest(source) != row["sha256"] or source.stat().st_size != row["bytes"]:
        raise ValueError("Revision response bytes changed")
    sidecar = json.loads(safe_file(root, "data/bronze/" + row["source_file"] + ".meta.json").read_text())
    if (
        row.get("http_status") != 200
        or sidecar.get("http_status") != 200
        or sidecar.get("download_method") != "httpx"
        or sidecar.get("source_url") != source_url
        or sidecar.get("sha256") != row["sha256"]
        or sidecar.get("bytes") != row["bytes"]
        or not started <= local_time(sidecar["downloaded_at"]) <= finished
    ):
        raise ValueError("A manual import cannot be relabeled as a revision HTTP check")
    if original_sha is not None and row["sha256"] != original_sha:
        raise ValueError("Changed official document requires a new source validation")
    return dict(
        proof,
        status="same_document_bytes" if original_sha else "original_not_equated_to_derivative",
        observed_artifact_sha256=row["sha256"],
    )


def safe_file(root, relative):
    path = root / relative
    if path.resolve() != path.absolute() or not path.resolve().is_relative_to(root) or not path.is_file():
        raise ValueError("Revision evidence must be a regular file within its collection")
    return path


def evidence(item, cutoff, observed, *, precision, source_url, original_sha=None):
    scope = item["availability"]["source_scope"]
    identity = (item["product"], item["adapter"], item["period"])
    if SCOPES.get(scope) != identity:
        raise ValueError("Closed-edition policy is limited to its three reviewed product/period bindings")
    if precision not in {"day", "timestamp"} or "known_new_edition" in item["availability"]:
        raise ValueError("Unknown observation precision or known new edition requires validation")
    if precision == "timestamp" and local_time(observed) > local_time(cutoff):
        raise ValueError("Source observation is after the round cutoff")
    day = date.fromisoformat(observed) if precision == "day" else local_time(observed).date()
    round_day = local_time(cutoff).date()
    if not period_end(item["period"]) < day <= round_day or local_time(item["candidate_as_of"]) > local_time(
        cutoff
    ):
        raise ValueError("Closed edition observation, requested period or candidate cutoff is invalid")
    check = revision_check(item["availability"], item, cutoff, source_url, original_sha)
    return {
        "policy_id": POLICY,
        "source_scope": scope,
        "product": item["product"],
        "adapter": item["adapter"],
        "period": item["period"],
        "accepted_for_requested_period": True,
        "observed_at_or_day": observed,
        "observation_precision": precision,
        "source_observation_current_for_round": day == round_day,
        "round_as_of": cutoff,
        "revision_check": check,
        "uncertainty": "Later publisher corrections may remain undetected; latest edition is not certified",
    }


def accepted(item, result):
    if result.get("latest_source_availability_verified") is True:
        return True
    proof = result.get("source_availability_evidence", {}).get("validated_closed_edition", {})
    return (
        result.get("status") == "checks_passed"
        and proof.get("policy_id") == POLICY
        and SCOPES.get(proof.get("source_scope")) == (item["product"], item["adapter"], item["period"])
        and proof.get("accepted_for_requested_period") is True
        and proof.get("period") == item["period"]
        and proof.get("revision_check", {}).get("status")
        in {"not_checked", "failed", "same_document_bytes", "original_not_equated_to_derivative"}
    )
