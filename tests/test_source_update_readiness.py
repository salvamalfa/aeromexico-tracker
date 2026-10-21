"""Adversarial orchestration contracts; actual source replays are reported separately."""

import copy
import json
import shutil
from importlib import import_module
from pathlib import Path
from uuid import uuid4

import pytest

from src.source_updates import readiness
from src.source_updates.catalog import ROOT


@pytest.mark.parametrize("adapter", ["h10", "am_traffic_candidate", "aerocivil", "retained"])
@pytest.mark.parametrize("accepted_cutoff", [None, "2026-10-20T12:00:00-06:00", "2026-10-22T12:00:00-06:00"])
def test_direct_replay_rejects_changed_or_missing_cutoff_before_recalculation(
    workspace, monkeypatch, adapter, accepted_cutoff
):
    module = import_module(f"src.source_updates.{adapter}")
    names = {
        "h10": "h10-2026M09.json",
        "am_traffic_candidate": "am-traffic-2026M09.json",
        "aerocivil": "aerocivil-2026M09.json",
        "retained": "certified-afac_airports-2026M09.json",
    }
    # Minimal synthetic receipt: this tests rejection before source/frames IO,
    # not extraction or source acceptance. Full candidate fixtures test replay.
    receipt = workspace / "receipts" / names[adapter]
    receipt.parent.mkdir(parents=True)
    receipt.write_text(json.dumps({"effective_as_of": accepted_cutoff}))
    before = receipt.read_bytes()

    def forbidden(*args, **kwargs):
        pytest.fail("Changed replay cutoff reached recalculation")

    monkeypatch.setattr(module, "certify" if adapter == "h10" else "frames", forbidden)
    args = [workspace]
    if adapter == "retained":
        args += ["afac_airports"]
    args += ["2026M09", "2026-10-21T12:00:00-06:00"]
    if adapter != "h10":
        args += ["a" * 32]
    with pytest.raises(ValueError, match="Accepted candidate cutoff changed"):
        module.run(*args, check=True)
    assert receipt.read_bytes() == before
    assert list(workspace.rglob("*.*")) == [receipt]


@pytest.fixture
def workspace():
    path = ROOT / "tmp/source-updates" / ("pytest-readiness-" + uuid4().hex)
    yield path
    if path.exists():
        shutil.rmtree(path)


def task(workspace, key="first", *, product="am_traffic_ir", adapter="am_traffic_ir", required=True):
    return {
        "id": key,
        "product": product,
        "period": "2026M09",
        "adapter": adapter,
        "workspace": str(workspace.parent / (workspace.name + "-" + key)),
        "receipt_id": "a" * 32,
        "required": required,
        "candidate_as_of": "2026-10-21T12:00:00-06:00",
    }


def recipe(workspace):
    return {
        "version": 1,
        "as_of": "2026-10-21T12:00:00-06:00",
        "required_items": ["first"],
        "items": [task(workspace)],
    }


def test_dry_run_preflights_without_receipt_body_reads_or_writes(workspace, monkeypatch):
    def forbidden(*args):
        raise AssertionError("Dry run executed a source checker")

    monkeypatch.setattr(readiness, "check_task", forbidden)
    result = readiness.execute(recipe(workspace), workspace)
    assert result["status"] == "planned_not_executed"
    assert not result["ready_for_review"] and not workspace.exists()
    assert result["scheduled_executions"] == result["network_requests"] == 0


@pytest.mark.parametrize(
    "change",
    [
        lambda r, w: r.update(version=True),
        lambda r, w: r.update(as_of="2026-10-21T12:00:00"),
        lambda r, w: r.update(required_items=[]),
        lambda r, w: r.update(required_items=["missing"]),
        lambda r, w: r["items"][0].update(required="true"),
        lambda r, w: r["items"][0].update(period="2026M10"),
        lambda r, w: r["items"][0].update(period="2026Q0"),
        lambda r, w: r["items"][0].update(adapter="shell"),
        lambda r, w: r["items"][0].update(product="gdelt"),
        lambda r, w: r["items"][0].update(workspace=str(w)),
        lambda r, w: r["items"][0].update(workspace=str(w / "nested")),
        lambda r, w: r["items"][0].update(receipt_id="../file"),
        lambda r, w: r["items"][0].update(candidate_as_of="2026-10-22T12:00:00-06:00"),
        lambda r, w: r["items"].append(dict(r["items"][0])),
        lambda r, w: r["items"][0].update(unknown="ignored?"),
    ],
)
def test_invalid_static_recipes_block_before_any_callback_or_write(workspace, monkeypatch, change):
    value = recipe(workspace)
    change(value, workspace)
    monkeypatch.setattr(
        readiness, "check_task", lambda *args: pytest.fail("source callback before preflight")
    )
    with pytest.raises((ValueError, TypeError)):
        readiness.execute(value, workspace, write=True)
    assert not workspace.exists()


def passed(item, cutoff):
    return {
        "id": item["id"],
        "product": item["product"],
        "period": item["period"],
        "required": item["required"],
        "status": "checks_passed",
        "output_sha256": {"fixture_contract_only": "a" * 64},
    }


def test_receipt_is_immutable_and_recheck_is_idempotent(workspace, monkeypatch):
    monkeypatch.setattr(readiness, "check_task", passed)
    value = recipe(workspace)
    saved = readiness.execute(value, workspace, write=True)
    before = (workspace / "readiness.json").read_bytes()
    checked = readiness.execute(value, workspace, check=True)
    assert saved["results"] == checked["results"]
    assert before == (workspace / "readiness.json").read_bytes()
    assert saved["ready_for_review"]
    assert not saved["ready_for_calendar_incorporation"]
    assert not saved["ready_for_automatic_execution"]
    assert saved["catalogue_products_not_exercised"]
    with pytest.raises(ValueError, match="new empty"):
        readiness.execute(value, workspace, write=True)
    changed = copy.deepcopy(value)
    changed["items"][0]["receipt_id"] = "b" * 32
    with pytest.raises(ValueError, match="recipe differs"):
        readiness.execute(changed, workspace, check=True)


def test_required_failure_stops_but_optional_failure_does_not(workspace, monkeypatch):
    value = recipe(workspace)
    value["items"].append(task(workspace, "optional", product="gdelt", adapter="gdelt", required=False))
    value["items"].append(task(workspace, "required", product="h10", adapter="h10"))
    value["required_items"].append("required")
    value["items"].append(task(workspace, "later", product="aerocivil", adapter="aerocivil", required=False))
    calls = []

    def checker(item, cutoff):
        calls.append(item["id"])
        if item["id"] != "first":
            raise ValueError("Fixture failure, not real source availability")
        return passed(item, cutoff)

    monkeypatch.setattr(readiness, "check_task", checker)
    result = readiness.execute(value, workspace, write=True)
    assert calls == ["first", "optional", "required"]
    assert result["status"] == "blocked_required_source"
    assert result["results"][0]["status"] == "checks_passed"
    assert result["results"][-1]["status"] == "not_started_after_required_failure"
    assert not result["ready_for_review"]
    assert (workspace / "readiness.json").exists()


def test_checker_code_change_cannot_reuse_prior_readiness_receipt(workspace, monkeypatch):
    monkeypatch.setattr(readiness, "check_task", passed)
    value = recipe(workspace)
    readiness.execute(value, workspace, write=True)
    path = workspace / "readiness.json"
    receipt = json.loads(path.read_text())
    receipt["verifier_code_sha256"] = "0" * 64
    path.write_text(json.dumps(receipt))
    with pytest.raises(ValueError, match="verifier changed"):
        readiness.execute(value, workspace, check=True)


def test_receipt_cannot_gain_activation_or_full_calendar_readiness(workspace, monkeypatch):
    monkeypatch.setattr(readiness, "check_task", passed)
    value = recipe(workspace)
    readiness.execute(value, workspace, write=True)
    path = workspace / "readiness.json"
    receipt = json.loads(path.read_text())
    receipt["ready_for_automatic_execution"] = True
    receipt["ready_for_calendar_incorporation"] = True
    receipt["activation"] = "enabled"
    path.write_text(json.dumps(receipt))
    with pytest.raises(ValueError, match="replay differs"):
        readiness.execute(value, workspace, check=True)


def test_accepted_source_receipt_cannot_borrow_another_collection(workspace):
    item = task(workspace)
    candidate = ROOT / item["workspace"]
    try:
        (candidate / "receipts").mkdir(parents=True)
        (candidate / "receipts" / ("collection-" + "a" * 32 + ".json")).write_text(
            json.dumps({"status": "collected_unvalidated"})
        )
        (candidate / "receipts/am-traffic-2026M09.json").write_text(
            json.dumps({"collection_run_id": "b" * 32})
        )
        with pytest.raises(ValueError, match="explicitly selected acquisition"):
            readiness.check_task(item, recipe(workspace)["as_of"])
        (candidate / ".source-update.lock").write_text("another writer")
        with pytest.raises(ValueError, match="active writer"):
            readiness.check_task(item, recipe(workspace)["as_of"])
    finally:
        shutil.rmtree(candidate)


def prepared_source(workspace):
    item = task(workspace, product="am_financials", adapter="retained")
    item["period"] = "2026Q2"
    candidate = Path(item["workspace"])
    (candidate / "receipts").mkdir(parents=True)
    (candidate / "receipts" / ("retained-" + item["receipt_id"] + ".json")).write_text(
        json.dumps({"status": "retained_unvalidated"})
    )
    accepted = {
        "retention_run_id": item["receipt_id"],
        "status": "checks_passed",
        "activation": "none",
        "publication": "not_authorized",
        "effective_as_of": item["candidate_as_of"],
    }
    path = candidate / "receipts/certified-am_financials-2026Q2.json"
    path.write_text(json.dumps(accepted))
    return item, path, accepted


@pytest.mark.parametrize(
    "field,value",
    [
        ("status", "blocked"),
        ("activation", "enabled"),
        ("publication", "authorized"),
        ("effective_as_of", None),
        ("effective_as_of", ""),
    ],
)
def test_source_receipt_state_and_cutoff_are_required_before_any_checker(
    workspace, monkeypatch, field, value
):
    from src.source_updates import retained

    item, path, accepted = prepared_source(workspace)
    try:
        accepted[field] = value
        path.write_text(json.dumps(accepted))
        before = readiness.inventory(path.parent.parent)
        monkeypatch.setattr(retained, "run", lambda *a, **k: pytest.fail("unaccepted source was replayed"))
        with pytest.raises(ValueError, match="Accepted source receipt|zoned"):
            readiness.check_task(item, item["candidate_as_of"])
        assert readiness.inventory(path.parent.parent) == before
    finally:
        shutil.rmtree(path.parent.parent)


def checker_result():
    return {
        "status": "checks_passed",
        "output_sha256": {"contract_only": "a" * 64},
        "activation": "none",
        "publication": "not_authorized",
        "code_files": {"src/source_updates/retained.py": "b" * 64},
    }


@pytest.mark.parametrize("claim", ["activation", "publication", "missing_code", "invalid_code"])
def test_checker_cannot_smuggle_activation_or_omit_actual_code_fingerprints(workspace, monkeypatch, claim):
    from src.source_updates import retained

    item, path, _ = prepared_source(workspace)
    result = checker_result()
    if claim == "missing_code":
        result.pop("code_files")
    elif claim == "invalid_code":
        result["code_files"] = {"src/source_updates/retained.py": "not-a-hash"}
    else:
        result[claim] = "enabled"
    monkeypatch.setattr(retained, "run", lambda *a, **k: result)
    try:
        with pytest.raises(ValueError, match="claim|fingerprints"):
            readiness.check_task(item, item["candidate_as_of"])
    finally:
        shutil.rmtree(path.parent.parent)


def test_changed_child_checker_code_invalidates_readiness_replay(workspace, monkeypatch):
    from src.source_updates import retained

    item, path, _ = prepared_source(workspace)
    result = checker_result()
    monkeypatch.setattr(retained, "run", lambda *a, **k: result)
    value = recipe(workspace)
    value["items"] = [item]
    try:
        saved = readiness.execute(value, workspace, write=True)
        assert saved["results"][0]["checker_code_files"] == result["code_files"]
        result["code_files"] = {"src/source_updates/retained.py": "c" * 64}
        with pytest.raises(ValueError, match="replay differs"):
            readiness.execute(value, workspace, check=True)
    finally:
        shutil.rmtree(path.parent.parent)
