"""Parallel isolated skill workers share one persistent coordinator, never a Bronze writer."""

import hashlib
import json

import pytest

from scripts import source_update_coordinator as coordinator
from src.source_updates.aerocivil_operational import POLICY
from tests.test_source_update_coordinator_state import DUE, NOW, bind, finish_action, record
from tests.test_source_update_coordinator_state import ledger as ledger


def dispatch(workspace, key, number, *, owner="owner-turn", worker=None):
    event = coordinator.run(workspace, now=DUE)["next_trigger"]
    return record(
        workspace,
        {
            "operation_id": f"isolated-{number}",
            "action": "dispatch_intent",
            "task_key": key,
            "event_id": event["event_id"],
            "automation_id": "synthetic-automation",
            "owner_turn_id": owner,
            "execution_mode": "isolated_skill_worker",
            "worker_workspace": str(worker or workspace.parent / f"worker-{number}"),
        },
        DUE,
    )


def complete(workspace, key, intent, operation):
    path = workspace / f"{operation}.json"
    path.write_text(
        json.dumps(
            {"task_key": key, "intent_id": intent, "receipt_id": f"local-operational-wrapper:{operation}"}
        )
    )
    return record(
        workspace,
        finish_action(
            key,
            "complete",
            operation,
            receipt_file=path.name,
            receipt_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        ),
        DUE,
    )


def test_same_owner_can_dispatch_isolated_workers_and_retains_lease_until_all_finish(ledger):
    workspace, _, output = ledger
    first, second, third = output["next_trigger"]["pending_task_keys"][:3]
    bind(workspace)
    dispatch(workspace, first, 1)
    state = dispatch(workspace, second, 2)["state"]
    assert set(state["active_tasks"]) == {first, second}
    assert state["active_task"] == first
    assert coordinator.trigger(state, NOW)["payload"] is None
    with pytest.raises(ValueError, match="single writer"):
        dispatch(workspace, third, 3, owner="different-coordinator")
    state = complete(workspace, first, "isolated-1", "finished-1")["state"]
    assert set(state["active_tasks"]) == {second} and state["active_task"] == second
    state = complete(workspace, second, "isolated-2", "finished-2")["state"]
    assert state["active_tasks"] == {} and state["active_task"] is None


def test_uncertain_isolated_worker_cannot_repeat_but_independent_same_owner_can_continue(ledger):
    workspace, _, output = ledger
    first, second = output["next_trigger"]["pending_task_keys"][:2]
    bind(workspace)
    dispatch(workspace, first, 1)
    record(
        workspace,
        finish_action(
            first,
            "uncertain",
            "uncertain-isolated",
            reconciliation_reference="synthetic-uncertain-tool-result",
        ),
        DUE,
    )
    with pytest.raises(ValueError):
        dispatch(workspace, first, 9)
    with pytest.raises(ValueError, match="single writer"):
        dispatch(workspace, second, 2, owner="new-owner")
    state = dispatch(workspace, second, 2)["state"]
    assert state["tasks"][first]["status"] == "blocked_for_decision"
    assert set(state["active_tasks"]) == {first, second}


@pytest.mark.parametrize("kind", ["same", "ancestor", "descendant", "coordinator"])
def test_worker_paths_never_overlap_shared_or_historical_candidate_workspaces(ledger, kind):
    workspace, _, output = ledger
    first, second = output["next_trigger"]["pending_task_keys"][:2]
    bind(workspace)
    original = workspace.parent / "workers" / "retained-worker"
    dispatch(workspace, first, 1, worker=original)
    complete(workspace, first, "isolated-1", "positive-first")
    target = {
        "same": original,
        "ancestor": original.parent,
        "descendant": original / "child",
        "coordinator": workspace,
    }[kind]
    with pytest.raises(ValueError, match="overlaps"):
        dispatch(workspace, second, 2, worker=target)


def test_worker_acquisition_inputs_cannot_overwrite_an_existing_unrelated_directory(ledger):
    workspace, _, output = ledger
    bind(workspace)
    occupied = workspace.parent / "unrelated"
    occupied.mkdir()
    (occupied / "original").write_bytes(b"preserve")
    with pytest.raises(ValueError, match="empty candidate"):
        dispatch(workspace, output["next_trigger"]["pending_task_keys"][0], 1, worker=occupied)
    assert (occupied / "original").read_bytes() == b"preserve"


def test_native_acknowledgement_does_not_invent_missing_message_or_turn_ids_or_complete_work(ledger):
    workspace, _, output = ledger
    first, second = output["next_trigger"]["pending_task_keys"][:2]
    bind(workspace)
    dispatch(workspace, first, 1)
    dispatch(workspace, second, 2)
    response = {"task_name": "/synthetic/rehearsal-worker"}
    action = finish_action(
        first,
        "acknowledge",
        "native-ack",
        native_task_name=response["task_name"],
        native_response_sha256=coordinator.digest(response),
    )
    state = record(workspace, action, DUE)["state"]
    observed = state["tasks"][first]["dispatches"][-1]
    assert observed["native_task_name"] == response["task_name"]
    assert observed["worker_turn_id"] is observed["message_id"] is None
    assert state["tasks"][first]["status"] == "running"
    with pytest.raises(ValueError, match="another dispatch"):
        record(workspace, {**action, "operation_id": "wrong-worker-reuse", "task_key": second}, DUE)


def test_lost_active_pointer_cannot_release_an_unresolved_worker(ledger):
    workspace, _, output = ledger
    bind(workspace)
    dispatch(workspace, output["next_trigger"]["pending_task_keys"][0], 1)
    state = json.loads((workspace / "state.json").read_text())
    state.update(active_task=None, active_tasks={})
    (workspace / "state.json").write_text(json.dumps(state))
    with pytest.raises(ValueError, match="persistent coordinator lease"):
        dispatch(workspace, output["next_trigger"]["pending_task_keys"][1], 2)


def test_conditional_consent_records_preparation_but_cannot_activate_on_unverified_booleans(ledger):
    workspace, _, _ = ledger
    recorded = record(
        workspace,
        {
            "operation_id": "conditional-consent",
            "action": "record_conditional_authorization",
            "operational_policy_id": POLICY,
            "authorization_reference": "synthetic-conditional-owner-consent",
        },
    )
    assert recorded["state"]["activation_authorized"] is False
    assert recorded["state"]["automation_id"] is None
    assert recorded["state"]["publication_authorized"] is False
    intent = {
        "operation_id": "conditional-activation",
        "action": "activation_intent",
        "activation_authorized": True,
        "authorization_reference": "synthetic-conditional-owner-consent",
        "owner_turn_id": "parent-turn",
    }
    with pytest.raises(ValueError, match="Conditional activation"):
        record(workspace, intent)
    conditions = {
        "viva_financials_verified": True,
        "required_round_data_verified": True,
        "single_coordinator_reconciled": True,
        "native_dispatch_verified": "true",
    }
    with pytest.raises(ValueError, match="Conditional activation"):
        record(
            workspace,
            {
                **intent,
                "verified_conditions": conditions,
                "conditions_verified_reference": "synthetic-evidence",
            },
        )


def test_host_without_native_owner_turn_id_uses_a_labelled_local_lease(ledger):
    workspace, _, output = ledger
    bind(workspace)
    key = output["next_trigger"]["pending_task_keys"][0]
    result = record(
        workspace,
        {
            "operation_id": "local-lease-dispatch",
            "action": "dispatch_intent",
            "task_key": key,
            "event_id": output["next_trigger"]["event_id"],
            "automation_id": "synthetic-automation",
            "owner_lease_id": "local_lease:synthetic-fixture",
            "execution_mode": "isolated_skill_worker",
            "worker_workspace": str(workspace.parent / "local-owner-worker"),
        },
        DUE,
    )
    native = result["state"]["tasks"][key]["dispatches"][-1]
    assert native["owner_lease_id"] == "local_lease:synthetic-fixture"
    assert native["owner_turn_id"] is native["native_owner_turn_id"] is None
