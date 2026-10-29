"""Adversarial operational state tests; all authorization/releases are synthetic."""

import copy
import hashlib
import json
import socket

import pytest

from scripts import source_update_coordinator as coordinator
from src.source_updates import collection

NOW = "2026-10-29T04:00:00Z"
DUE = "2026-11-17T08:00:00-06:00"


def releases(entities=("AEROMEXICO", "VOLARIS"), day="2026-10-26"):
    return [
        {
            "entity": entity,
            "period": "2026Q3",
            "kind": "financial_report",
            "confirmed": True,
            "publication_precision": "day",
            "published_on": day,
            "published_at": None,
            "document_url": "https://example.test/financial-report",
        }
        for entity in entities
    ]


@pytest.fixture
def ledger(tmp_path, monkeypatch):
    monkeypatch.setattr(collection, "ROOT", tmp_path)

    def no_network(*args, **kwargs):
        raise AssertionError("Coordinator must not make network requests")

    monkeypatch.setattr(socket.socket, "connect", no_network)
    workspace = tmp_path / "tmp/source-updates/coordinator"
    request = {"as_of": NOW, "start": "2026-11", "months": 2, "quarter": "2026Q3", "releases": releases()}
    output = coordinator.run(workspace, request=request, now=NOW)
    return workspace, request, output


def record(workspace, action, at=NOW):
    action = {"at": at, **action}
    return coordinator.run(workspace, action=action, now=at)


def bind(workspace):
    record(
        workspace,
        {
            "operation_id": "activation-1",
            "action": "activation_intent",
            "activation_authorized": True,
            "authorization_reference": "synthetic-user-consent",
            "owner_turn_id": "parent-turn",
        },
    )
    return record(
        workspace,
        {
            "operation_id": "binding-1",
            "action": "bind_authorized_automation",
            "intent_id": "activation-1",
            "automation_id": "synthetic-automation",
            "reconciliation_reference": "synthetic-native-success",
        },
    )


def dispatch(workspace, key, operation="dispatch-1", at=DUE):
    event = coordinator.run(workspace, now=at)["next_trigger"]
    return record(
        workspace,
        {
            "operation_id": operation,
            "action": "dispatch_intent",
            "task_key": key,
            "automation_id": "synthetic-automation",
            "event_id": event["event_id"],
            "owner_turn_id": "owner-turn",
        },
        at,
    )


def finish_action(key, kind, operation, **extra):
    return {
        "operation_id": operation,
        "action": kind,
        "task_key": key,
        "automation_id": "synthetic-automation",
        "owner_turn_id": "owner-turn",
        **extra,
    }


def test_future_dates_periods_and_separate_authorizations(ledger):
    workspace, request, output = ledger
    state = output["state"]
    assert [r["date"] for r in state["monthly_rounds"]] == ["2026-11-17", "2026-12-15"]
    assert [r["period"] for r in state["monthly_rounds"]] == ["2026M10", "2026M11"]
    assert state["next_quarterly"]["date"] is None
    assert state["next_quarterly"]["missing_central_reports"] == ["VIVA_AEROBUS"]
    assert state["activation_authorized"] is False and state["automation_id"] is None
    assert output["scheduled_executions"] == output["network_requests"] == 0
    assert output["publication_authorized"] is False
    assert all(t["certification"] is None and t["receipts"] == [] for t in state["tasks"].values())
    payload = output["next_trigger"]["payload"]
    assert "20261117T080000" in payload["schedule"] and "RRULE" not in payload["schedule"]
    assert payload["timing_mode"] == "flexible_schedule"
    assert payload["default_timezone"] == "America/Mexico_City"
    assert str(workspace) in payload["prompt"]


def test_prepare_is_byte_idempotent_and_cannot_replace_existing_state(ledger):
    workspace, request, _ = ledger
    before = (workspace / "state.json").read_bytes()
    coordinator.run(workspace, request=request, now=NOW)
    assert (workspace / "state.json").read_bytes() == before
    with pytest.raises(ValueError, match="cannot be replaced"):
        coordinator.run(workspace, request={**request, "months": 1}, now=NOW)
    assert (workspace / "state.json").read_bytes() == before


@pytest.mark.parametrize("change", [{"start": "2027-01"}, {"start": "2026-10"}, {"months": True}])
def test_unverified_year_past_round_and_bad_count_are_blocked(ledger, change):
    _, request, _ = ledger
    with pytest.raises(ValueError):
        coordinator.prepare({**request, **change})


def test_writer_lock_and_moved_ledger_fail_closed(ledger):
    workspace, _, _ = ledger
    with collection.writer(workspace):
        before = (workspace / "state.json").read_bytes()
        with pytest.raises(FileExistsError):
            bind(workspace)
        assert (workspace / "state.json").read_bytes() == before
    moved = workspace.parent / "copy"
    moved.mkdir()
    (moved / "state.json").write_bytes(before)
    with pytest.raises(ValueError, match="moved or copied"):
        coordinator.run(moved, now=NOW)


@pytest.mark.parametrize("value", [False, "true", 1, None])
def test_exact_authorization_boolean_required(ledger, value):
    workspace, _, _ = ledger
    with pytest.raises(ValueError, match="Explicit activation"):
        record(
            workspace,
            {
                "operation_id": "bad-auth",
                "action": "activation_intent",
                "activation_authorized": value,
                "authorization_reference": "synthetic",
                "owner_turn_id": "turn",
            },
        )


def test_uncertain_create_does_not_allow_second_automation_or_binding_without_intent(ledger):
    workspace, _, _ = ledger
    with pytest.raises(ValueError, match="exact authorized creation"):
        record(workspace, {"operation_id": "bad-bind", "action": "bind_authorized_automation"})
    intent = {
        "operation_id": "create-intent",
        "action": "activation_intent",
        "activation_authorized": True,
        "authorization_reference": "synthetic",
        "owner_turn_id": "turn",
    }
    record(workspace, intent)
    before = (workspace / "state.json").read_bytes()
    record(workspace, intent)
    assert (workspace / "state.json").read_bytes() == before
    with pytest.raises(ValueError, match="uncertain automation"):
        record(workspace, {**intent, "operation_id": "another-create"})
    with pytest.raises(ValueError, match="Uncertain creation"):
        record(
            workspace,
            {
                "operation_id": "no-proof",
                "action": "activation_not_created",
                "intent_id": "create-intent",
                "reconciliation_reference": "no response",
            },
        )


def test_dispatch_gates_due_event_id_single_writer_and_operation_replay(ledger):
    workspace, _, output = ledger
    keys = output["next_trigger"]["pending_task_keys"]
    with pytest.raises(ValueError, match="not authorized"):
        dispatch(workspace, keys[0])
    bind(workspace)
    with pytest.raises(ValueError, match="not due"):
        dispatch(workspace, keys[0], at=NOW)
    first = dispatch(workspace, keys[0])
    before = (workspace / "state.json").read_bytes()
    dispatch(workspace, keys[0])
    assert (workspace / "state.json").read_bytes() == before
    assert len(first["state"]["tasks"][keys[0]]["dispatches"]) == 1
    with pytest.raises(ValueError, match="single writer"):
        dispatch(workspace, keys[1], "other-dispatch")
    with pytest.raises(ValueError, match="reused with different"):
        dispatch(workspace, keys[1], "dispatch-1")


def test_receipts_require_exact_task_intent_and_hash_and_do_not_certify_new_period(ledger):
    workspace, _, output = ledger
    key = output["next_trigger"]["pending_task_keys"][0]
    bind(workspace)
    dispatch(workspace, key)
    receipt = workspace / "received.json"
    receipt.write_text(json.dumps({"task_key": key, "intent_id": "wrong", "receipt_id": "native-receipt"}))
    action = finish_action(
        key,
        "complete",
        "complete-1",
        receipt_file=receipt.name,
        receipt_sha256=hashlib.sha256(receipt.read_bytes()).hexdigest(),
    )
    with pytest.raises(ValueError, match="different task or dispatch"):
        record(workspace, action, DUE)
    receipt.write_text(
        json.dumps({"task_key": key, "intent_id": "dispatch-1", "receipt_id": "native-receipt"})
    )
    with pytest.raises(ValueError, match="hash differs"):
        record(workspace, action, DUE)
    action["receipt_sha256"] = hashlib.sha256(receipt.read_bytes()).hexdigest()
    completed = record(workspace, action, DUE)["state"]
    assert completed["tasks"][key]["status"] == "completed"
    assert completed["tasks"][key]["certification"] is None
    assert completed["publication_authorized"] is False
    other = key.replace("2026M10", "2026M11")
    assert completed["tasks"][other]["status"] == "planned"
    assert completed["tasks"][other]["receipts"] == []
    assert completed["tasks"][other]["certification"] is None
    with pytest.raises(ValueError, match="cannot be dispatched"):
        dispatch(workspace, key, "repeat-completed")


def test_uncertain_send_retains_writer_until_positive_reconciliation(ledger):
    workspace, _, output = ledger
    key, other = output["next_trigger"]["pending_task_keys"][:2]
    bind(workspace)
    dispatch(workspace, key)
    with pytest.raises(ValueError, match="Uncertain delivery"):
        record(workspace, finish_action(key, "retry", "retry-no-proof", reason="technical"), DUE)
    state = record(
        workspace,
        finish_action(
            key, "uncertain", "uncertain-1", reconciliation_reference="synthetic-lookup-inconclusive"
        ),
        DUE,
    )["state"]
    assert state["tasks"][key]["status"] == "blocked_for_decision"
    assert state["active_task"] == key
    with pytest.raises(ValueError, match="single writer"):
        dispatch(workspace, key, "repeat-uncertain")
    with pytest.raises(ValueError, match="single writer"):
        dispatch(workspace, other, "independent-task")
    record(
        workspace,
        finish_action(
            key,
            "retry",
            "stopped-proof",
            reason="technical",
            confirmed_stopped_or_not_sent=True,
            reconciliation_reference="synthetic-positive-stop-evidence",
        ),
        DUE,
    )
    assert dispatch(workspace, other, "independent-task")["state"]["tasks"][other]["status"] == "running"


def test_retry_limit_is_shared_by_batch_and_preserved_across_products(ledger):
    workspace, _, output = ledger
    bind(workspace)
    statuses = []
    for number, key in enumerate(output["next_trigger"]["pending_task_keys"][:3]):
        dispatch(workspace, key, f"dispatch-{number}")
        state = record(
            workspace,
            finish_action(
                key,
                "retry",
                f"retry-{number}",
                reason="technical",
                confirmed_stopped_or_not_sent=True,
                reconciliation_reference="synthetic-positive-stop-evidence",
            ),
            DUE,
        )["state"]
        statuses.append(state["tasks"][key]["status"])
    assert statuses == ["retry_pending", "retry_pending", "blocked_for_decision"]
    assert state["reschedules"] == {"monthly:2026M10": 2}


def test_report_refresh_uses_existing_calendar_and_cannot_dispatch_combined_round_early(ledger):
    workspace, _, _ = ledger
    bind(workspace)
    all_reports = releases(("AEROMEXICO", "VOLARIS", "VIVA_AEROBUS"), "2026-11-13")
    output = record(
        workspace,
        {"operation_id": "reports-1", "action": "refresh_reports", "releases": all_reports},
        "2026-11-14T08:00:00-06:00",
    )
    assert output["state"]["next_quarterly"]["date"] == "2026-11-18"
    assert output["next_trigger"]["date"] == "2026-11-18"
    assert len(output["next_trigger"]["members"]) == 2
    key = next(key for key in output["next_trigger"]["pending_task_keys"] if key.startswith("monthly:"))
    with pytest.raises(ValueError, match="not due"):
        dispatch(workspace, key)
    dispatch(workspace, key, at="2026-11-18T08:00:00-06:00")


def test_common_calendar_news_is_selected_and_discovery_providers_are_optional(ledger):
    _, _, output = ledger
    tasks = output["state"]["tasks"]
    assert tasks["monthly:2026M10:editorial_news"]["selected"] is True
    assert tasks["monthly:2026M10:rss"]["selected"] is False
    assert tasks["monthly:2026M10:gdelt"]["selected"] is False
    assert len(output["next_trigger"]["pending_task_keys"]) == 15


def test_monitor_can_append_only_viva_without_erasing_prior_confirmations(ledger):
    workspace, request, _ = ledger
    before = copy.deepcopy(request["releases"])
    output = record(
        workspace,
        {
            "operation_id": "viva-monitor",
            "action": "refresh_reports",
            "releases": releases(("VIVA_AEROBUS",), "2026-11-13"),
        },
        "2026-11-14T08:00:00-06:00",
    )
    assert output["state"]["next_quarterly"]["date"] == "2026-11-18"
    assert output["state"]["next_quarterly"]["missing_central_reports"] == []
    assert output["state"]["request"]["releases"] == before
    assert output["state"]["releases"][:2] == before


def test_combined_event_identity_and_date_survive_completion_of_one_cadence(ledger):
    workspace, _, _ = ledger
    all_reports = releases(("AEROMEXICO", "VOLARIS", "VIVA_AEROBUS"), "2026-11-10")
    output = record(
        workspace,
        {"operation_id": "reports", "action": "refresh_reports", "releases": all_reports},
        "2026-11-11T08:00:00-06:00",
    )
    before = output["next_trigger"]
    state = copy.deepcopy(output["state"])
    for key in before["task_keys"]:
        if key.startswith("monthly:"):
            state["tasks"][key]["status"] = "completed"
    after = coordinator.trigger(state, "2026-11-11T08:00:00-06:00")
    assert before["date"] == after["date"] == "2026-11-17"
    assert before["event_id"] == after["event_id"]
    assert len(after["members"]) == 2
    assert after["pending_task_keys"] and all(k.startswith("quarterly:") for k in after["pending_task_keys"])


def test_overdue_payload_is_not_silently_moved_to_tomorrow(ledger):
    workspace, _, _ = ledger
    output = coordinator.run(workspace, now="2026-11-18T08:00:00-06:00")
    assert output["next_trigger"]["payload"] is None
    assert "reconciliation" in output["next_trigger"]["reason"]


def test_changed_holidays_fail_before_mutation_and_future_action_is_rejected(ledger, monkeypatch):
    workspace, _, _ = ledger
    before = (workspace / "state.json").read_bytes()
    with pytest.raises(ValueError, match="future action"):
        coordinator.run(
            workspace, action={"operation_id": "future", "action": "activation_intent", "at": DUE}, now=NOW
        )
    changed = copy.deepcopy(coordinator.holidays())
    changed["years"]["2026"]["dates"].append("2026-11-17")
    monkeypatch.setattr(coordinator, "holidays", lambda: changed)
    with pytest.raises(ValueError, match="holiday inputs changed"):
        bind(workspace)
    assert (workspace / "state.json").read_bytes() == before


def test_reconciliation_cannot_predate_dispatch_and_jump_over_retry_delay(ledger):
    workspace, _, output = ledger
    key = output["next_trigger"]["pending_task_keys"][0]
    bind(workspace)
    dispatch(workspace, key)
    action = {
        "at": "2026-11-10T08:00:00-06:00",
        **finish_action(
            key,
            "retry",
            "retroactive-retry",
            reason="technical",
            confirmed_stopped_or_not_sent=True,
            reconciliation_reference="synthetic-stop",
        ),
    }
    with pytest.raises(ValueError, match="predates the last recorded"):
        coordinator.run(workspace, action=action, now=DUE)
