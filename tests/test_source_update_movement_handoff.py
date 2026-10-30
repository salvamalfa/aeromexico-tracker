"""Synthetic movement routing checks; no native send or publication occurs."""

import copy
import json
import sys
from types import ModuleType

import pytest

from scripts import source_update_handoff_routing as routing
from scripts import source_update_handoffs as handoffs
from tests.test_source_update_aerocivil_operational import provisional_result
from tests.test_source_update_handoffs import action, start, write
from tests.test_source_update_handoffs import env as env


def item(workspace):
    return {
        "id": "aerocivil-quarterly",
        "product": "aerocivil",
        "period": "2026Q3",
        "source_period": "2026M07",
        "adapter": "aerocivil",
        "workspace": str(workspace),
        "receipt_id": "a" * 32,
        "candidate_as_of": "2026-10-21T01:06:33.087948+00:00",
        "required": True,
        "cadence": "quarterly",
        "used": True,
        "depends_on": [],
        "availability": {"source_scope": "aerocivil_retained_maximum_month_v1"},
    }


def test_quarterly_job_uses_its_explicit_native_month_without_relabeling(tmp_path):
    declared = item(tmp_path)
    native = routing.native_item(declared)
    assert native["period"] == "2026M07" and native["required"] is True
    assert not set(native) & {"source_period", "cadence", "used", "depends_on"}
    assert declared["period"] == "2026Q3" and declared["source_period"] == "2026M07"


@pytest.mark.parametrize(
    "change",
    [
        {"period": "2026Q4"},
        {"source_period": "2026M08"},
        {"source_period": None},
        {"adapter": "retained"},
        {"used": False},
        {"required": False},
        {"depends_on": ["unverified-source"]},
        {"cadence": "monthly"},
        {"unrecognized": True},
    ],
)
def test_new_period_scope_or_omitted_dependencies_do_not_silently_pass(tmp_path, change):
    with pytest.raises(ValueError):
        routing.native_item({**item(tmp_path), **change})


def test_source_arrival_dispatches_one_dashboard_and_zero_financial_analyses(env):
    workspace, observation, _ = env
    observation["item"] = item(workspace.parent / "source")
    result = start(env)
    source = next(iter(result["state"]["sources"].values()))
    job = next(iter(result["state"]["jobs"].values()))
    assert len(result["ready_jobs"]) == len(result["state"]["jobs"]) == 1
    assert job["stage"] == "dashboard" and job["release_kind"] == "movements"
    assert job["entity"] == "AEROMEXICO" and job["period"] == "2026Q3" and job["dependency"] is None
    assert source["public_impact"]["status"] == "recorded_movements_in_existing_flights_map"
    assert handoffs.expected_binding(source)["period"] == "2026M07"
    assert result["native_sends"] == result["publication_requests"] == result["schedule_changes"] == 0
    result = action(
        workspace,
        "observe",
        "same-data-new-capture",
        observation={**observation, "change_reason": "same edition"},
    )
    assert len(result["state"]["jobs"]) == 1
    changed = copy.deepcopy(observation)
    changed["synthetic_version"] = "c" * 64
    result = action(workspace, "observe", "actual-revision", observation=changed)
    assert len(result["state"]["jobs"]) == 2 and len(result["ready_jobs"]) == 1


@pytest.mark.parametrize("product", ["aerocivil", "viva_financials", "volaris_sec", "am_financials"])
def test_native_envelope_keeps_existing_movement_aggregate_separate_from_editorial(env, product):
    workspace, observation, _ = env
    observation["item"]["product"] = product
    result = start(env)
    call = result["ready_jobs"][0]
    message = call["arguments"]["message"]
    instruction = json.loads(message[message.index("{") :])
    scope = instruction["publication_scope"]
    if product == "aerocivil":
        assert instruction["job"]["release_kind"] == "movements"
        assert "39 existing flight-data payloads" in scope
        assert "existing INDUSTRY aggregate" in scope
        assert "preserve seven theses" in scope
        assert "no new periods, source values, Industry editorial" in scope
        assert "exclude Industria" not in scope
    else:
        assert "exclude Industria and unrelated products" in scope
        assert "existing INDUSTRY aggregate" not in scope


def test_native_replay_and_operational_policy_are_both_required(tmp_path, monkeypatch):
    observation = {"item": item(tmp_path), "as_of": "2026-10-30T14:48:52+00:00"}
    observed = []

    def preflight(recipe, workspace):
        observed.append(recipe)
        return recipe["items"]

    monkeypatch.setattr(handoffs.readiness, "preflight", preflight)
    monkeypatch.setattr(handoffs.readiness, "check_task", lambda *args: provisional_result())
    monkeypatch.setattr(
        handoffs,
        "meaningful_data",
        lambda value, checked: {**value, "tables": {"gold/fact_synthetic": [{"value": 1}]}},
    )
    result = handoffs.verify_candidate(observation, tmp_path / "receipt")
    assert observed[0]["items"][0]["period"] == "2026M07"
    assert result["source_binding"]["item"]["period"] == "2026Q3"
    checked = provisional_result()
    checked["operational_acceptance"]["official_confirmation"] = True
    monkeypatch.setattr(handoffs.readiness, "check_task", lambda *args: checked)
    with pytest.raises(ValueError, match="provisional"):
        handoffs.verify_candidate(observation, tmp_path / "receipt")


def test_original_candidate_code_fingerprint_failure_is_never_ignored(tmp_path, monkeypatch):
    observation = {"item": item(tmp_path), "as_of": "2026-10-30T14:48:52+00:00"}
    monkeypatch.setattr(handoffs.readiness, "preflight", lambda recipe, workspace: recipe["items"])

    def changed_code(*args):
        raise ValueError("Candidate checker fingerprint changed; certify a new isolated candidate")

    monkeypatch.setattr(handoffs.readiness, "check_task", changed_code)
    with pytest.raises(ValueError, match="fingerprint changed"):
        handoffs.verify_candidate(observation, tmp_path / "receipt")


def test_movements_require_their_own_exact_release_binding(tmp_path, monkeypatch):
    module = ModuleType("src.publish.movements_scope")
    source = {
        "product": "aerocivil",
        "source_binding": {"item": item(tmp_path)},
        "checked": {"output_sha256": {"gold/fact": "f" * 64}},
    }
    binding = handoffs.expected_binding(source)
    spec = {"source_binding": binding, "product": "aerocivil", "period_id": "2026Q3", "stage": "movements"}
    module.anchor = lambda: spec
    monkeypatch.setitem(sys.modules, "src.publish.movements_scope", module)
    job = {"release_kind": "movements", "entity": "AEROMEXICO", "period": "2026Q3"}
    handoffs.verify_release_binding(job, source)
    spec["source_binding"] = {**binding, "period": "2026Q3"}
    with pytest.raises(ValueError, match="Movement release"):
        handoffs.verify_release_binding(job, source)
    spec["source_binding"] = binding
    with pytest.raises(ValueError, match="Movement release"):
        handoffs.verify_release_binding({**job, "release_kind": "data"}, source)


def test_invalid_movements_proof_cannot_fall_back_to_financial_or_generic_verifier(env, monkeypatch):
    workspace, _, _ = env
    site = workspace.parents[2] / "site"
    site.mkdir()
    manifest = write(site / "publication_manifest.json", {})
    write(site / "aerocivil-movements-publication.json", {"invalid": True})
    write(site / "issuer-publication.json", {"would_be_selected_before_fix": True})
    module = ModuleType("src.publish.movements_scope")
    module.verify_movements = lambda path: ["invalid movement source proof"]
    monkeypatch.setitem(sys.modules, "src.publish.movements_scope", module)
    from scripts import check_pages_publication

    monkeypatch.setattr(
        check_pages_publication, "verifier_for", lambda site, repo: "src.publish.movements_scope"
    )
    with pytest.raises(ValueError, match="invalid movement source proof"):
        handoffs.verify_dashboard({"site_path": str(site), "manifest": manifest})


def test_financial_source_cannot_alias_the_movements_stage():
    source = {"product": "viva_financials", "source_binding": {"item": {"product": "viva_financials"}}}
    with pytest.raises(ValueError, match="financial source"):
        routing.verify_release({"release_kind": "movements"}, source, {})
