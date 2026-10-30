"""Synthetic technical refresh tests; no real approval or publication is granted."""

import copy
from contextlib import nullcontext

import pytest

from scripts import source_update_handoff_review as review
from scripts import source_update_handoffs as handoffs
from src.analysis_agent import lifecycle
from tests.test_source_update_handoffs import NOW, ack, action, claim, only_job, result_receipt, start, write
from tests.test_source_update_handoffs import env as env


@pytest.fixture
def prepared(env, monkeypatch):
    workspace, _, _ = env
    job_id = only_job(start(env))
    claim(workspace, job_id)
    ack(workspace, job_id)
    draft = {
        "entity_key": "VIVA_AEROBUS",
        "period_id": "2026Q3",
        "package_id": "same-package",
        "calculation_fingerprint": "same-calculations",
        "claims": [{"text": "unchanged prose"}],
    }
    old = {
        "draft": draft,
        "content_hash": "same-content",
        "code_version": "old-code",
        "prompt_version": "same-prompt",
        "version": "old-version",
    }
    new = {**old, "code_version": "new-code", "version": "new-version"}
    old_record = write(workspace / "old-record.json", old)
    new_record = write(workspace / "new-record.json", new)
    monkeypatch.setattr(handoffs, "verify_analysis", lambda *args: None)
    old_receipt = result_receipt(workspace, job_id, record=old_record)
    finished = action(
        workspace, "finish", "finish1", job_id=job_id, owner_lease_id="local_lease:test", receipt=old_receipt
    )
    report = {"decision": "pass", "reviewer_task": "independent-synthetic-review", "version": "new-version"}
    report_ref = write(workspace / "new-review.json", report)
    new_receipt = write(
        workspace / "new-analysis-receipt.json",
        {
            "job_id": job_id,
            "data_version": "a" * 64,
            "entity": "VIVA_AEROBUS",
            "period": "2026Q3",
            "status": "analysis_approved",
            "record": new_record,
        },
    )
    statuses = {
        "old-version": {
            "state": "approved",
            "publication": None,
            "events": [],
            "approval": {"event_hash": "old-approval"},
        },
        "new-version": {
            "state": "approved",
            "publication": None,
            "events": [],
            "approval": {"event_hash": "new-approval"},
            "audit": {"report": report, "audit_hash": lifecycle.digest(report)},
        },
    }
    monkeypatch.setattr(lifecycle, "writer", lambda *args: nullcontext())
    monkeypatch.setattr(lifecycle, "state", lambda record, **kwargs: statuses[record["version"]])
    monkeypatch.setattr(
        lifecycle,
        "record_identity",
        lambda record: (
            record["draft"]["entity_key"],
            record["draft"]["period_id"],
            record["version"],
        ),
    )
    operation = {
        "action": "refresh_analysis_approval",
        "operation_id": "refresh-1",
        "at": NOW,
        "job_id": job_id,
        "owner_lease_id": "local_lease:test",
        "previous_result": old_receipt,
        "receipt": new_receipt,
        "review_report": report_ref,
        "reason": "Reimport and independent audit after a runtime-only correction",
    }
    return workspace, finished["state"], job_id, operation, statuses


def test_technical_refresh_changes_only_result_and_append_only_history(prepared):
    workspace, before, job_id, operation, _ = prepared
    old_job = copy.deepcopy(before["jobs"][job_id])
    result = handoffs.run(workspace, action=operation)
    state, job = result["state"], result["state"]["jobs"][job_id]
    assert state["heads"] == before["heads"] and state["sources"] == before["sources"]
    assert state["jobs"].keys() == before["jobs"].keys()
    assert job["result"] == operation["receipt"] and job["status"] == "completed"
    assert job["native_response"] == old_job["native_response"] and job["attempt"] == old_job["attempt"]
    assert job["receipt_history"] == [old_job["result"], operation["receipt"]]
    history = job["technical_review_history"][0]
    assert history["previous_result"] == old_job["result"] and history["replacement_result"] == job["result"]
    assert history["content_hash"] == "same-content" and history["data_version"] == "a" * 64
    for key, child in before["jobs"].items():
        if key != job_id:
            assert state["jobs"][key] == child
    body = (workspace / "state.json").read_bytes()
    handoffs.run(workspace, action=operation)
    assert (workspace / "state.json").read_bytes() == body
    with pytest.raises(ValueError, match="Operation ID"):
        handoffs.run(workspace, action={**operation, "reason": "different operation content"})


@pytest.mark.parametrize(
    "mutation", ["prose", "package", "calculations", "data", "code_unchanged", "stale_ref"]
)
def test_content_data_or_identity_changes_cannot_use_technical_refresh(prepared, mutation):
    workspace, state, job_id, operation, _ = prepared
    receipt_path = handoffs.checked_ref(operation["receipt"])
    receipt = handoffs.load(receipt_path)
    record = handoffs.load(handoffs.checked_ref(receipt["record"]))
    if mutation in {"prose", "package", "calculations"}:
        key = {"prose": "claims", "package": "package_id", "calculations": "calculation_fingerprint"}[
            mutation
        ]
        record["draft"][key] = "different"
    elif mutation == "data":
        receipt["data_version"] = "b" * 64
    elif mutation == "code_unchanged":
        record["code_version"] = "old-code"
    else:
        operation["previous_result"] = {"path": "/not-the-prior-result", "sha256": "c" * 64}
    receipt["record"] = write(workspace / "changed-record.json", record)
    operation["receipt"] = write(workspace / "changed-receipt.json", receipt)
    with pytest.raises(ValueError):
        review.refresh(state, state["jobs"][job_id], operation, handoffs.ROOT)
    assert state["jobs"][job_id]["result"] == prepared[1]["jobs"][job_id]["result"]


@pytest.mark.parametrize("state_kind", ["revoked", "revoked_then_approved", "published", "missing_new_audit"])
def test_revocation_publication_or_unregistered_review_blocks(prepared, state_kind):
    _, state, job_id, operation, statuses = prepared
    if state_kind == "revoked":
        statuses["old-version"]["state"] = "validated"
    elif state_kind == "revoked_then_approved":
        statuses["old-version"]["events"] = [{"action": "revoke"}]
    elif state_kind == "published":
        statuses["old-version"]["state"] = "published"
    else:
        statuses["new-version"]["audit"] = None
    with pytest.raises(ValueError):
        review.refresh(state, state["jobs"][job_id], operation, handoffs.ROOT)


@pytest.mark.parametrize(
    "child_status", ["completed", "served_verified", "dispatch_intent", "running", "unknown"]
)
def test_built_or_published_descendant_prevents_refresh(prepared, child_status):
    _, state, job_id, operation, _ = prepared
    child = next(value for value in state["jobs"].values() if value.get("dependency") == job_id)
    child["status"] = child_status
    with pytest.raises(ValueError, match="descendant"):
        review.refresh(state, state["jobs"][job_id], operation, handoffs.ROOT)


def test_running_dashboard_can_be_blocked_and_continued_with_same_worker_after_refresh(prepared):
    _, state, job_id, operation, _ = prepared
    child = next(value for value in state["jobs"].values() if value.get("dependency") == job_id)
    child.update(status="blocked", result={"path": "retained-blocking-receipt", "sha256": "e" * 64})
    before = copy.deepcopy(child)
    review.refresh(state, state["jobs"][job_id], operation, handoffs.ROOT)
    assert child == before and child["dependency"] == job_id


def test_wrong_owner_or_superseded_source_does_not_refresh(prepared):
    workspace, state, job_id, operation, _ = prepared
    with pytest.raises(ValueError, match="another owner"):
        handoffs.run(workspace, action={**operation, "owner_lease_id": "local_lease:another"})
    source = state["sources"][state["jobs"][job_id]["source_id"]]
    state["heads"][f"{source['product']}:{source['period']}"] = "superseding-source"
    with pytest.raises(ValueError, match="completed current"):
        review.refresh(state, state["jobs"][job_id], operation, handoffs.ROOT)


def test_canonical_verifier_and_registered_review_must_both_pass(prepared, monkeypatch):
    _, state, job_id, operation, statuses = prepared
    calls = []

    def blocked_verifier(*args):
        calls.append(args)
        raise ValueError("Actual source binding or current presentation is invalid")

    monkeypatch.setattr(handoffs, "verify_analysis", blocked_verifier)
    with pytest.raises(ValueError, match="source binding"):
        review.refresh(state, state["jobs"][job_id], operation, handoffs.ROOT)
    assert calls
    monkeypatch.setattr(handoffs, "verify_analysis", lambda *args: None)
    statuses["new-version"]["audit"]["audit_hash"] = "unregistered-audit"
    with pytest.raises(ValueError, match="canonical registered"):
        review.refresh(state, state["jobs"][job_id], operation, handoffs.ROOT)
