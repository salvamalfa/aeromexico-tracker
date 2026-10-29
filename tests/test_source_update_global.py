"""Global orchestration tests; synthetic contracts never stand in for extraction."""

import copy
import json
import shutil
from uuid import uuid4

import pytest

from src.source_updates import global_readiness as gate
from src.source_updates import round_tasks
from src.source_updates.catalog import ROOT


def recipe():
    return {
        "version": 1,
        "round": "monthly",
        "as_of": "2026-10-21T12:00:00-06:00",
        "monthly_period": "2026M09",
        "quarterly_period": "2026Q3",
        "items": [],
        "releases": [],
    }


def task(product="afac_airports", cadence="monthly"):
    return {
        "id": product,
        "product": product,
        "cadence": cadence,
        "period": "2026M09" if cadence == "monthly" else "2026Q3",
        "used": True,
        "depends_on": [],
        "adapter": "unsupported",
        "workspace": "tmp/source-updates/contract-only-" + product,
        "receipt_id": "a" * 32,
        "candidate_as_of": "2026-10-21T12:00:00-06:00",
    }


@pytest.fixture
def workspace():
    path = ROOT / "tmp/source-updates" / ("pytest-global-" + uuid4().hex)
    yield path
    if path.exists():
        shutil.rmtree(path)


def test_empty_dry_run_lists_obligations_without_source_io(workspace, monkeypatch):
    monkeypatch.setattr(gate, "verify", lambda *a: pytest.fail("Dry run read source"))
    result = gate.execute(recipe(), workspace)
    assert len(result["blockers"]) == 15  # Fourteen data tasks plus the editorial task.
    assert "monthly:editorial_news:not_verified" in result["blockers"]
    assert not result["core_ready"] and not result["requested_bundle_ready"]
    assert result["status"] == "planned_not_executed"
    assert not workspace.exists()
    assert result["network_requests"] == result["scheduled_executions"] == 0


def test_actual_unsupported_path_writes_blocked_receipt_and_exact_replay(workspace):
    r = recipe()
    r["items"] = [task()]
    result = gate.execute(r, workspace, write=True)
    assert result["results"]["afac_airports"]["status"] == "blocked"
    assert "whole-product" in result["results"]["afac_airports"]["reason"]
    assert result["results"][round_tasks.EDITORIAL_ID]["status"] == "pending_native_editorial_review"
    assert not result["ready_for_calendar_incorporation"]
    before = (workspace / "global-readiness.json").read_bytes()
    replay = gate.execute(r, workspace, check=True)
    assert replay["receipt_sha256"]
    assert before == (workspace / "global-readiness.json").read_bytes()
    with pytest.raises(ValueError, match="new empty workspace"):
        gate.execute(r, workspace, write=True)


def test_receipt_rejects_policy_or_input_drift(workspace, monkeypatch):
    r = recipe()
    gate.execute(r, workspace, write=True)
    original = gate.fingerprints
    monkeypatch.setattr(gate, "fingerprints", lambda: {**original(), "policy": "changed"})
    with pytest.raises(ValueError, match="changed"):
        gate.execute(r, workspace, check=True)
    monkeypatch.setattr(gate, "fingerprints", original)
    changed = copy.deepcopy(r)
    changed["as_of"] = "2026-10-22T12:00:00-06:00"
    with pytest.raises(ValueError, match="changed"):
        gate.execute(changed, workspace, check=True)


def test_replay_cannot_accept_tampered_decision(workspace):
    r = recipe()
    gate.execute(r, workspace, write=True)
    path = workspace / "global-readiness.json"
    data = json.loads(path.read_text())
    data["ready_for_calendar_incorporation"] = True
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="differs"):
        gate.execute(r, workspace, check=True)


def test_execute_blocks_network_even_for_accidental_checker_call(workspace, monkeypatch):
    import socket

    def accidental(*args):
        socket.create_connection(("example.com", 443))

    monkeypatch.setattr(gate, "verify", accidental)
    r = recipe()
    r["items"] = [task()]
    result = gate.execute(r, workspace, write=True)
    assert result["results"]["afac_airports"]["status"] == "blocked"
    assert not result["requested_bundle_ready"]


def test_one_calendar_executes_independent_sources_even_when_optional_provider_and_news_are_pending(
    workspace, monkeypatch
):
    r = recipe()
    r["items"] = [task("gdelt"), task("afac_airports"), task("banxico")]
    calls = []

    def check(item, *_args):
        calls.append(item["product"])
        return {
            "status": "blocked" if item["product"] == "gdelt" else "checks_passed",
            "latest_source_availability_verified": item["product"] != "gdelt",
        }

    monkeypatch.setattr(gate, "verify", check)
    result = gate.execute(r, workspace, write=True)
    assert calls == ["gdelt", "afac_airports", "banxico"]
    assert result["results"]["afac_airports"]["status"] == "checks_passed"
    assert result["results"]["banxico"]["status"] == "checks_passed"
    assert result["results"]["gdelt"]["status"] == "blocked"
    assert result["results"][round_tasks.EDITORIAL_ID]["status"] == "pending_native_editorial_review"
    tasks = {task["id"]: task for task in result["calendar_tasks"]}
    assert tasks["afac_airports"]["prepared_for_review"] and tasks["banxico"]["prepared_for_review"]
    assert not tasks["gdelt"]["required"] and not tasks["gdelt"]["prepared_for_review"]
    assert tasks[round_tasks.EDITORIAL_ID]["required"]
    assert "monthly:editorial_news:not_verified" in result["blockers"]
    assert not result["core_ready"] and not result["ready_for_calendar_incorporation"]
    assert result["activation"] == "none" and result["publication"] == "not_authorized"


def test_candidates_cannot_overlap_global_receipt_even_before_dry_run(workspace):
    r = recipe()
    i = task()
    i.update(adapter="retained", workspace=str(workspace))
    r["items"] = [i]
    with pytest.raises(ValueError, match="disjoint"):
        gate.execute(r, workspace)
    assert not workspace.exists()


def test_native_lag_is_explicit_not_equivalence_or_current_availability():
    r = recipe()
    i = task("afac_carriers")
    i["source_period"] = "2026M07"
    r["items"] = [i]
    gate.preflight(r)
    i["source_period"] = "2026M10"
    with pytest.raises(ValueError, match="not equivalent"):
        gate.preflight(r)
    i.update(product="am_traffic_ir", source_period="2026M07")
    with pytest.raises(ValueError, match="not equivalent"):
        gate.preflight(r)


def test_aerocivil_native_month_does_not_become_a_quarter():
    r = recipe()
    i = task("aerocivil", "quarterly")
    i.update(adapter="aerocivil", source_period="2026M07")
    r["items"] = [i]
    gate.preflight(r)
    i["source_period"] = "2026M06"
    with pytest.raises(ValueError, match="belong"):
        gate.preflight(r)


def test_cli_does_not_accept_supplied_check_results(workspace, capsys, tmp_path):
    r = recipe()
    r["results"] = {"status": "checks_passed"}
    path = tmp_path / "recipe.json"
    path.write_text(json.dumps(r))
    assert gate.main(["--recipe", str(path), "--workspace", str(workspace), "--execute"]) == 1
    assert json.loads(capsys.readouterr().out)["status"] == "blocked"
    assert not workspace.exists()


def test_fingerprints_cover_reusable_checks_contracts_calendar_catalogue():
    files = gate.fingerprints()
    for name in (
        "src/source_updates/global_readiness.py",
        "src/source_updates/readiness.py",
        "src/source_updates/retained.py",
        "src/source_updates/checks.py",
        "config/source_update_holidays.json",
        "config/source_catalog.yaml",
        "config/silver_schema_contracts.yaml",
        "config/gold_schema_contracts.yaml",
    ):
        assert name in files and files[name] == gate.readiness.sha(ROOT / name)
