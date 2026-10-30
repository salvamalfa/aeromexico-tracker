"""Synthetic recovery of a completed, not-yet-served build; no real publication."""

import copy
import json

import pytest

from scripts import source_update_handoffs as handoffs


@pytest.fixture
def recovery(tmp_path):
    def write(name, value):
        path = tmp_path / name
        path.write_text(json.dumps(value))
        return handoffs.file_ref(path)

    old = write("old-receipt.json", {"status": "site_built_verified"})
    job = {
        "job_id": "job",
        "source_id": "source",
        "entity": "AEROMEXICO",
        "period": "2026Q3",
        "stage": "dashboard",
        "status": "completed",
        "dependency": None,
        "release_kind": "movements",
        "attempt": {"owner_lease_id": "local_lease:test"},
        "native_response": write("native.json", {"native_task_name": "/root/synthetic"}),
        "result": old,
        "receipt_history": [old],
    }
    state = {
        "jobs": {"job": job},
        "heads": {"aerocivil:2026Q3": "source"},
        "sources": {"source": {"product": "aerocivil", "period": "2026Q3", "data_version": "a" * 64}},
    }
    action = {
        "action": "continue_existing_worker",
        "job_id": "job",
        "owner_lease_id": "local_lease:test",
        "reconciliation": write("reconciliation.json", {"reason": "Correct producer after CI failure"}),
    }
    return state, action, tmp_path, write


def test_completed_build_recovery_retains_receipt_and_requires_new_verified_finish(recovery, monkeypatch):
    state, action, workspace, write = recovery
    before = copy.deepcopy(state["jobs"]["job"])
    old_bytes = handoffs.checked_ref(before["result"]).read_bytes()
    handoffs.transition(state, action, workspace)
    job = state["jobs"]["job"]
    assert job["status"] == "running"
    for key in ("attempt", "native_response", "result", "receipt_history"):
        assert job[key] == before[key]
    assert handoffs.checked_ref(before["result"]).read_bytes() == old_bytes
    calls = []
    monkeypatch.setattr(handoffs, "verify_dashboard", lambda result: calls.append("gate"))
    monkeypatch.setattr(handoffs, "verify_release_binding", lambda job, source: calls.append("binding"))
    new = write(
        "new-receipt.json",
        {
            "job_id": "job",
            "entity": "AEROMEXICO",
            "period": "2026Q3",
            "data_version": "a" * 64,
            "status": "site_built_verified",
        },
    )
    handoffs.transition(state, {**action, "action": "finish", "receipt": new}, workspace)
    assert calls == ["gate", "binding"]
    assert job["status"] == "completed" and job["result"] == new
    assert job["receipt_history"] == [before["result"], new]


@pytest.mark.parametrize(
    "stage,status",
    [
        ("analysis", "completed"),
        ("dashboard", "served_verified"),
        ("dashboard", "no_change"),
        ("dashboard", "superseded"),
        ("dashboard", "planned"),
    ],
)
def test_build_recovery_rejects_closed_or_non_dashboard_completion(recovery, stage, status):
    state, action, workspace, _ = recovery
    state["jobs"]["job"].update(stage=stage, status=status)
    before = copy.deepcopy(state)
    with pytest.raises(ValueError, match="Continue only"):
        handoffs.transition(state, action, workspace)
    assert state == before


@pytest.mark.parametrize("mutation", ["native", "head", "lease", "reconciliation", "old_receipt"])
def test_build_recovery_requires_exact_current_worker_and_physical_evidence(recovery, mutation):
    state, action, workspace, _ = recovery
    if mutation == "native":
        state["jobs"]["job"]["native_response"] = None
    elif mutation == "head":
        state["heads"]["aerocivil:2026Q3"] = "newer-source"
    elif mutation == "lease":
        action["owner_lease_id"] = "local_lease:other"
    else:
        ref = action["reconciliation"] if mutation == "reconciliation" else state["jobs"]["job"]["result"]
        handoffs.checked_ref(ref).write_text("changed")
    before = copy.deepcopy(state)
    with pytest.raises(ValueError):
        handoffs.transition(state, action, workspace)
    assert state == before


@pytest.mark.parametrize("stage", ["analysis", "dashboard"])
def test_existing_acknowledged_blocked_worker_recovery_remains_available(recovery, stage):
    state, action, workspace, _ = recovery
    job = state["jobs"]["job"]
    job.update(stage=stage, status="blocked")
    original = copy.deepcopy(job)
    handoffs.transition(state, action, workspace)
    assert job["status"] == "running"
    assert job["result"] == original["result"] and job["receipt_history"] == original["receipt_history"]
