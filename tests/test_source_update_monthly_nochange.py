"""Monthly data-only no-change goes through the existing outbox lifecycle."""

import pytest
from test_source_update_handoffs import ack, action, claim, only_job, start, write
from test_source_update_handoffs import env as env

from scripts import source_update_handoffs as handoffs


@pytest.mark.parametrize("product,entity", [("am_traffic_ir", "AEROMEXICO"), ("aicm_traffic", None)])
def test_monthly_no_change_replays_its_own_source_after_native_ack(env, monkeypatch, product, entity):
    from src.publish import source_data_update

    workspace, observation, _ = env
    observation["item"].update(product=product, period="2026M09")
    result = start(env)
    assert len(result["ready_jobs"]) == 1
    job_id = only_job(result)
    job = result["state"]["jobs"][job_id]
    assert (job["stage"], job["release_kind"], job["entity"]) == ("dashboard", "source_data", entity)
    claim(workspace, job_id)
    ack(workspace, job_id)
    binding = handoffs.expected_binding(result["state"]["sources"][job["source_id"]])
    observed = {"status": "no_visual_change", "source_binding": binding, "synthetic_test_only": True}
    calls = []

    def replay(profile, expected, *, site):
        calls.append((profile, expected, site))
        return observed

    monkeypatch.setattr(source_data_update, "verify_no_visual_change", replay)
    receipt = {
        "status": "no_visual_change",
        "job_id": job_id,
        "data_version": "a" * 64,
        "entity": entity,
        "period": "2026M09",
        "source_profile": write(workspace / "profile.json", {"synthetic": True}),
        "equivalence_proof": write(workspace / "equivalence.json", observed),
    }
    response = write(workspace / "result.json", receipt)
    final = action(
        workspace,
        "finish",
        "finish-monthly",
        job_id=job_id,
        owner_lease_id="local_lease:test",
        receipt=response,
    )
    assert final["state"]["jobs"][job_id]["status"] == "no_change"
    assert calls and calls[0][1] == binding
    assert final["ready_jobs"] == []
    assert final["publication_requests"] == 0
