"""Refresh an unpublished technical approval without changing analysis content."""

from __future__ import annotations

from pathlib import Path


def refresh(state: dict, job: dict, action: dict, root: Path):
    from scripts import source_update_handoffs as handoffs
    from src.analysis_agent import lifecycle

    if job["stage"] != "analysis" or job["status"] != "completed" or not handoffs.is_current(state, job):
        raise ValueError("Technical review refresh needs a completed current analysis job")
    if job.get("attempt") is None or action.get("owner_lease_id") != job["attempt"]["owner_lease_id"]:
        raise ValueError("Technical review must preserve the original worker owner")
    if job.get("native_response") is None:
        raise ValueError("Preserve the acknowledged original analysis worker")
    response = handoffs.load(handoffs.checked_ref(job["native_response"]))
    if not response.get("native_task_name"):
        raise ValueError("Original native acknowledgment has no task identity")
    if not isinstance(action.get("reason"), str) or not action["reason"].strip():
        raise ValueError("Record the concrete technical review reason")
    if action.get("previous_result") != job["result"]:
        raise ValueError("Refresh must name the exact previous result reference")
    descendants = {job["job_id"]}
    while True:
        children = {key for key, value in state["jobs"].items() if value.get("dependency") in descendants}
        if children <= descendants:
            break
        descendants.update(children)
    for key in descendants - {job["job_id"]}:
        child = state["jobs"][key]
        if child["stage"] == "dashboard" and (
            child["status"] not in {"planned", "blocked", "no_change", "superseded"}
            or child.get("served_verification")
        ):
            raise ValueError(
                "An unreconciled, built or served dashboard descendant prevents technical refresh"
            )
    old_receipt = handoffs.load(handoffs.checked_ref(job["result"]))
    receipt = handoffs.load(handoffs.checked_ref(action["receipt"]))
    source = state["sources"][job["source_id"]]
    identity = (job["job_id"], source["data_version"], job["entity"], job["period"], "analysis_approved")
    for value in (old_receipt, receipt):
        if (
            tuple(value.get(key) for key in ("job_id", "data_version", "entity", "period", "status"))
            != identity
        ):
            raise ValueError("Technical review receipt changed its job, data, entity, period or stage")
    old = handoffs.load(handoffs.checked_ref(old_receipt["record"]))
    new = handoffs.load(handoffs.checked_ref(receipt["record"]))
    if old["draft"] != new["draft"] or old["content_hash"] != new["content_hash"]:
        raise ValueError("Technical approval refresh cannot change prose, sources, package or calculations")
    old_versions = (old["code_version"], old["prompt_version"])
    new_versions = (new["code_version"], new["prompt_version"])
    if old_versions == new_versions or old["version"] == new["version"]:
        raise ValueError("Technical review requires a real changed code/prompt fingerprint and new version")
    if lifecycle.record_identity(old)[:2] != lifecycle.record_identity(new)[:2]:
        raise ValueError("Technical review changed analysis entity or period")
    report = handoffs.load(handoffs.checked_ref(action["review_report"]))
    ledger = root / "analysis_runs/lifecycle"
    with lifecycle.writer(ledger):
        previous = lifecycle.state(old, root=ledger)
        if (
            previous["state"] != "approved"
            or previous.get("publication")
            or any(event["action"] == "revoke" for event in previous["events"])
        ):
            raise ValueError(
                "Previous approval is revoked, unpublished validation is absent, or already published"
            )
        handoffs.verify_analysis(job, source, receipt)
        current = lifecycle.state(new, root=ledger)
        if current["state"] != "approved" or current.get("publication"):
            raise ValueError("Replacement analysis must be approved and unpublished")
        audit = current.get("audit") or {}
        if audit.get("report") != report or audit.get("audit_hash") != lifecycle.digest(report):
            raise ValueError(
                "Physical technical review does not match the canonical registered passing audit"
            )
        if report.get("decision") != "pass":
            raise ValueError("Replacement technical audit did not pass")
        history = {
            "operation_id": action["operation_id"],
            "at": action["at"],
            "reason": action["reason"],
            "previous_result": job["result"],
            "replacement_result": action["receipt"],
            "old_version": old["version"],
            "new_version": new["version"],
            "content_hash": new["content_hash"],
            "data_version": source["data_version"],
            "previous_approval_event": previous["approval"]["event_hash"],
            "replacement_approval_event": current["approval"]["event_hash"],
            "review_report": action["review_report"],
            "audit_hash": audit["audit_hash"],
            "original_native_response": job["native_response"],
        }
        receipts = job.setdefault("receipt_history", [])
        if job["result"] not in receipts:
            receipts.append(job["result"])
        receipts.append(action["receipt"])
        job.setdefault("technical_review_history", []).append(history)
        job["result"] = action["receipt"]
