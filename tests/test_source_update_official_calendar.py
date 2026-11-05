"""Synthetic new-run continuation checks; no native job or approval is created."""

import copy
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

from scripts import source_update_coordinator as coordinator
from src.source_updates import collection
from src.source_updates.coordinator_consumers import PROMPT_DELTA
from tests.test_source_update_coordinator_state import NOW, bind, record
from tests.test_source_update_coordinator_state import releases as financial_releases


@pytest.fixture
def continuation(tmp_path, monkeypatch):
    monkeypatch.setattr(collection, "ROOT", tmp_path)
    old = tmp_path / "tmp/source-updates/old"
    request = {"as_of": NOW, "start": "2026-11", "months": 2, "quarter": "2026Q3", "releases": []}
    coordinator.run(old, request=request, now=NOW)
    bind(old)
    path = old / "state.json"
    from scripts.source_update_handoffs import file_ref

    selected = {
        **request,
        "run_id": "official-map-v2",
        "conditional_products": ["afac_margins"],
        "consumers": ["official_routes"],
        "continuation": {"previous_state": file_ref(path)},
    }
    return tmp_path / "tmp/source-updates/new", old, selected


def test_new_checkpoint_preserves_native_id_dates_and_old_bytes(continuation):
    new, old, request = continuation
    before = (old / "state.json").read_bytes()
    output = coordinator.run(new, request=request, now=NOW)
    state = output["state"]
    assert state["run_id"] == "official-map-v2" and state["automation_id"] is None
    assert state["continuation"]["existing_automation_id"] == "synthetic-automation"
    assert state["monthly_rounds"] == coordinator.load(old / "state.json")["monthly_rounds"]
    assert all(t["selected"] for t in state["tasks"].values() if t["product"] == "afac_margins")
    assert all(t["publication_authorized"] is False for t in state["tasks"].values())
    assert output["publication_authorized"] is False and output["scheduled_executions"] == 0
    assert output["next_trigger"]["payload"]["prompt"].endswith(PROMPT_DELTA)
    with pytest.raises(ValueError, match="never create another"):
        record(new, {"action": "activation_intent", "operation_id": "bad", "activation_authorized": True})
    result = record(
        new,
        {
            "action": "bind_existing_automation",
            "operation_id": "same-calendar",
            "automation_id": "synthetic-automation",
            "authorization_reference": "synthetic-scope",
            "reconciliation_reference": "synthetic-native-live-read-update-receipt",
        },
    )
    assert result["state"]["automation_id"] == "synthetic-automation"
    assert result["state"]["automation_creation"] is None
    assert (old / "state.json").read_bytes() == before


@pytest.mark.parametrize(
    "change",
    [
        {"run_id": None},
        {"conditional_products": []},
        {"conditional_products": ["afac_carriers"]},
        {"consumers": ["official_routes", "official_routes"]},
        {"continuation": None},
    ],
)
def test_bad_explicit_selection_never_creates_state(continuation, change):
    new, old, request = continuation
    before = (old / "state.json").read_bytes()
    with pytest.raises((ValueError, TypeError)):
        coordinator.run(new, request={**request, **change}, now=NOW)
    assert not (new / "state.json").exists() and (old / "state.json").read_bytes() == before


def test_reprepare_options_rejected_without_mutating_old_or_new(continuation):
    new, old, request = continuation
    old_before = (old / "state.json").read_bytes()
    with pytest.raises(ValueError, match="NEW run_id"):
        coordinator.run(old, request=request, now=NOW)
    coordinator.run(new, request=request, now=NOW)
    before = (new / "state.json").read_bytes()
    coordinator.run(new, request=request, now=NOW)
    assert (new / "state.json").read_bytes() == before
    with pytest.raises(ValueError, match="cannot be replaced"):
        coordinator.run(new, request={**request, "consumers": []}, now=NOW)
    assert (old / "state.json").read_bytes() == old_before
    assert (new / "state.json").read_bytes() == before


def test_changed_previous_snapshot_or_wrong_native_id_blocks(continuation):
    new, old, request = continuation
    coordinator.run(new, request=request, now=NOW)
    before = (new / "state.json").read_bytes()
    action = {
        "action": "bind_existing_automation",
        "operation_id": "bind",
        "automation_id": "other-id",
        "authorization_reference": "synthetic",
        "reconciliation_reference": "synthetic",
    }
    with pytest.raises(ValueError, match="reuse the existing"):
        record(new, action)
    (old / "state.json").write_bytes((old / "state.json").read_bytes() + b" ")
    with pytest.raises(ValueError, match="changed"):
        record(new, {**action, "automation_id": "synthetic-automation"})
    assert (new / "state.json").read_bytes() == before


@pytest.mark.parametrize("status", ["retry_pending", "blocked_for_decision", "completed"])
def test_continuation_never_resets_existing_attempt_history(continuation, status):
    new, old, request = continuation
    previous = coordinator.load(old / "state.json")
    task = next(t for t in previous["tasks"].values() if t["selected"] and t["cadence"] == "monthly")
    task.update(status=status, reschedules=1, dispatches=[{"synthetic": True}])
    path = old / "state.json"
    path.write_text(json.dumps(previous), encoding="utf-8")
    from scripts.source_update_handoffs import file_ref

    request["continuation"]["previous_state"] = file_ref(path)
    before = path.read_bytes()
    with pytest.raises(ValueError, match="reconciled|never reset"):
        coordinator.run(new, request=request, now=NOW)
    assert not (new / "state.json").exists() and path.read_bytes() == before


@pytest.mark.parametrize("change", [{"months": 1}, {"months": 3}, {"start": "2026-12"}])
def test_continuation_preserves_complete_future_horizon(continuation, change, monkeypatch):
    new, old, request = continuation
    before = (old / "state.json").read_bytes()
    bank = copy.deepcopy(coordinator.holidays())
    bank["years"]["2027"] = {
        "dates": []
    }  # Synthetic only: reach horizon guard instead of the real 2027 block.
    monkeypatch.setattr(coordinator, "holidays", lambda: bank)
    with pytest.raises(ValueError, match="complete future monthly calendar"):
        coordinator.run(new, request={**request, **change}, now=NOW)
    assert not (new / "state.json").exists() and (old / "state.json").read_bytes() == before


def test_continuation_preserves_undated_pending_quarter(continuation):
    new, old, request = continuation
    before = (old / "state.json").read_bytes()
    with pytest.raises(ValueError, match="omit an existing selected pending"):
        coordinator.run(new, request={**request, "quarter": "2026Q2"}, now=NOW)
    assert not (new / "state.json").exists() and (old / "state.json").read_bytes() == before


@pytest.mark.parametrize("pending", [False, True])
def test_completed_past_quarter_is_retained_without_new_dispatch(continuation, pending):
    new, old, request = continuation
    historical = old.parent / "completed-history"
    reports = financial_releases(entities=("AEROMEXICO", "VOLARIS", "VIVA_AEROBUS"), day="2026-10-23")
    original_request = {k: request[k] for k in ("start", "months", "quarter")}
    original_request.update(as_of="2026-10-24T00:00:00Z", releases=reports)
    coordinator.run(historical, request=original_request, now=NOW)
    bind(historical)
    previous = coordinator.load(historical / "state.json")
    selected = {
        key for key, task in previous["tasks"].items() if task["selected"] and task["cadence"] == "quarterly"
    }
    # Synthetic terminal history only: never presented as actual source certification.
    for key in selected:
        previous["tasks"][key].update(
            status="completed", dispatches=[{"synthetic": True}], receipts=[{"synthetic": True}]
        )
    if pending:
        previous["tasks"][sorted(selected)[0]]["status"] = "planned"
    path = historical / "state.json"
    path.write_text(json.dumps(previous), encoding="utf-8")
    from scripts.source_update_handoffs import file_ref

    request.update(releases=reports, continuation={"previous_state": file_ref(path)})
    before = path.read_bytes()
    if pending:
        with pytest.raises(ValueError, match="same original fully completed"):
            coordinator.run(new, request=request, now=NOW)
        assert not (new / "state.json").exists()
    else:
        output = coordinator.run(new, request=request, now=NOW)
        state = output["state"]
        assert selected.isdisjoint(state["tasks"])
        assert set(state["continuation"]["retained_completed_task_keys"]) == selected
        assert all(
            state["tasks"][key]["cadence"] == "monthly" for key in output["next_trigger"]["pending_task_keys"]
        )
        assert all(task["status"] == "planned" for task in state["tasks"].values())
        assert all(task["publication_authorized"] is False for task in state["tasks"].values())
        assert all(event["task_keys"] for event in state["events"].values())
    assert path.read_bytes() == before


def test_continuation_cannot_turn_previously_selected_conditional_off(continuation):
    new, old, request = continuation
    previous = coordinator.load(old / "state.json")
    for task in previous["tasks"].values():
        if task["product"] == "afac_margins":
            task["selected"] = True
    path = old / "state.json"
    path.write_text(json.dumps(previous), encoding="utf-8")
    from scripts.source_update_handoffs import file_ref

    request.update(continuation={"previous_state": file_ref(path)}, conditional_products=[], consumers=[])
    with pytest.raises(ValueError, match="omit an existing selected pending"):
        coordinator.run(new, request=request, now=NOW)


def test_default_preparation_and_prompt_match_k2_exactly(tmp_path):
    """Run the unchanged baseline implementation, rather than mirror its data in an assertion."""
    root = Path(__file__).resolve().parents[1]
    baseline = subprocess.check_output(
        ["git", "show", "29cdba0f:scripts/source_update_coordinator.py"], cwd=root
    )
    module_path = tmp_path / "baseline.py"
    module_path.write_bytes(baseline)
    spec = importlib.util.spec_from_file_location("baseline_calendar", module_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    request = {"as_of": NOW, "start": "2026-11", "months": 2, "quarter": "2026Q3", "releases": []}
    original = module.prepare(copy.deepcopy(request))
    current = coordinator.prepare(copy.deepcopy(request))
    assert original == current
    original["workspace"] = current["workspace"] = str(tmp_path)
    assert module.trigger(original, NOW) == coordinator.trigger(current, NOW)
    assert coordinator.digest(original) == module.digest(current)


def test_cli_help_retains_existing_options():
    result = subprocess.run(
        [sys.executable, "-m", "scripts.source_update_coordinator", "--help"],
        capture_output=True,
        text=True,
        check=True,
    )
    assert all(option in result.stdout for option in ("--workspace", "--prepare", "--record", "--now"))
