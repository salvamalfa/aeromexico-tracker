"""Synthetic publication state tests; no deployment or native worker is created."""

import copy

import pytest

from scripts import source_update_handoff_nochange
from scripts import source_update_handoffs as handoffs
from tests.test_source_update_handoffs import ack, action, claim, result_receipt, start
from tests.test_source_update_handoffs import env as env


def dashboard_job(result, entity):
    return next(
        key
        for key, value in result["state"]["jobs"].items()
        if value["stage"] == "dashboard" and value["entity"] == entity
    )


def finished_dashboard(env, monkeypatch, status="site_built_verified"):
    workspace, observation, _ = env
    first = dashboard_job(start(env), "VIVA_AEROBUS")
    claim(workspace, first)
    ack(workspace, first)
    monkeypatch.setattr(handoffs, "verify_dashboard", lambda *args: None)
    monkeypatch.setattr(handoffs, "verify_release_binding", lambda *args: None)
    monkeypatch.setattr(source_update_handoff_nochange, "verify", lambda *args: None)
    receipt = result_receipt(workspace, first, status)
    result = action(
        workspace, "finish", "finish1", job_id=first, owner_lease_id="local_lease:test", receipt=receipt
    )
    other = copy.deepcopy(observation)
    other["item"]["product"] = "volaris_sec"
    result = action(workspace, "observe", "source2", observation=other)
    second = dashboard_job(result, "VOLARIS")
    return workspace, first, second


def test_built_publication_holds_writer_through_failed_and_successful_served_qa(env, monkeypatch):
    workspace, first, second = finished_dashboard(env, monkeypatch)
    with pytest.raises(ValueError, match="Another dashboard writer"):
        action(workspace, "claim", "claim2", job_id=second, owner_lease_id="local_lease:test")

    def stale_response(*args):
        raise ValueError("Served bytes do not match the verified build")

    monkeypatch.setattr(handoffs, "verify_served", stale_response)
    with pytest.raises(ValueError, match="Served bytes"):
        action(
            workspace, "served", "qa1", job_id=first, owner_lease_id="local_lease:test", paths=["index.html"]
        )
    assert handoffs.run(workspace)["state"]["jobs"][first]["status"] == "completed"
    with pytest.raises(ValueError, match="Another dashboard writer"):
        action(workspace, "claim", "claim2", job_id=second, owner_lease_id="local_lease:test")

    monkeypatch.setattr(handoffs, "verify_served", lambda *args: {"synthetic_verified": True})
    result = action(
        workspace, "served", "qa1", job_id=first, owner_lease_id="local_lease:test", paths=["index.html"]
    )
    assert result["state"]["jobs"][first]["status"] == "served_verified"
    result = action(workspace, "claim", "claim2", job_id=second, owner_lease_id="local_lease:test")
    assert result["state"]["jobs"][second]["status"] == "dispatch_intent"


def test_physically_verified_no_change_does_not_hold_publication_writer(env, monkeypatch):
    workspace, first, second = finished_dashboard(env, monkeypatch, "no_visual_change")
    assert handoffs.run(workspace)["state"]["jobs"][first]["status"] == "no_change"
    result = action(workspace, "claim", "claim2", job_id=second, owner_lease_id="local_lease:test")
    assert result["state"]["jobs"][second]["status"] == "dispatch_intent"
