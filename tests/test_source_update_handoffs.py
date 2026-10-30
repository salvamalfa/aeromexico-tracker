"""Synthetic outbox tests; these never certify real sources or approval."""

import copy
import json
from pathlib import Path

import pandas as pd
import pytest

from scripts import source_update_handoffs as handoffs
from src.source_updates import collection

NOW = "2026-10-30T13:00:00Z"


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")
    return handoffs.file_ref(path)


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(handoffs, "ROOT", tmp_path)
    monkeypatch.setattr(collection, "ROOT", tmp_path)
    for name in [*handoffs.SKILLS.values(), *handoffs.CONSUMERS]:
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("Synthetic test skill")
    workspace = tmp_path / "tmp/source-updates/handoffs"
    source = tmp_path / "tmp/source-updates/source"
    original = write(source / "original.json", {"synthetic": True})
    observation = {
        "item": {
            "product": "viva_financials",
            "period": "2026Q3",
            "workspace": str(source),
            "receipt_id": "synthetic-retention",
            "candidate_as_of": NOW,
        },
        "as_of": NOW,
        "authorization_reference": "synthetic-consent",
        "change_reason": "first edition",
    }

    def verify(value, workspace):
        handoffs.checked_ref(original)
        version = value.get("synthetic_version", "a" * 64)
        return {
            "data_version": version,
            "legacy_data_version": version,
            "meaningful_identity": {"schema_version": handoffs.semantic.SCHEMA, "sha256": version},
            "checked": {"output_sha256": {"gold/fact_test": "b" * 64}},
            "source_binding": value,
        }

    monkeypatch.setattr(handoffs, "verify_source", verify)
    monkeypatch.setattr(handoffs, "verify_candidate", verify)
    return workspace, observation, original


def action(workspace, kind, operation, **kwargs):
    return handoffs.run(workspace, action={"action": kind, "operation_id": operation, "at": NOW, **kwargs})


def start(env):
    workspace, observation, _ = env
    return action(workspace, "observe", "source1", observation=observation)


def only_job(result):
    return next(iter(result["state"]["jobs"]))


def claim(workspace, job):
    return action(workspace, "claim", "claim1", job_id=job, owner_lease_id="local_lease:test")


def ack(workspace, job):
    response = write(workspace / "native.json", {"native_task_name": "/root/synthetic_worker"})
    return action(
        workspace,
        "acknowledge",
        "ack1",
        job_id=job,
        owner_lease_id="local_lease:test",
        native_response=response,
    )


def test_one_airline_arrival_advances_without_other_airlines(env):
    result = start(env)
    assert len(result["ready_jobs"]) == 2
    assert len(result["state"]["sources"]) == 1
    job = result["state"]["jobs"][only_job(result)]
    assert job["entity"] == "VIVA_AEROBUS" and job["stage"] == "analysis"
    assert "collaboration.spawn_agent" == result["ready_jobs"][0]["tool"]
    assert result["native_sends"] == result["schedule_changes"] == result["publication_requests"] == 0


def test_repeat_operation_preserves_bytes_and_changed_args_rejected(env):
    workspace, observation, _ = env
    start(env)
    before = (workspace / "state.json").read_bytes()
    start(env)
    assert (workspace / "state.json").read_bytes() == before
    with pytest.raises(ValueError, match="Operation ID"):
        action(workspace, "observe", "source1", observation={**observation, "change_reason": "changed"})
    assert (workspace / "state.json").read_bytes() == before


def test_second_capture_with_same_data_does_not_queue_second_thesis(env):
    workspace, observation, _ = env
    start(env)
    result = action(
        workspace, "observe", "source2", observation={**observation, "change_reason": "availability"}
    )
    assert len(result["state"]["sources"]) == 1
    assert len(result["ready_jobs"]) == 2
    assert len(next(iter(result["state"]["sources"].values()))["observations"]) == 2


def test_changed_values_supersede_pending_and_reversion_is_real_change(env):
    workspace, observation, _ = env
    old = only_job(start(env))
    result = action(
        workspace, "observe", "source2", observation={**observation, "synthetic_version": "c" * 64}
    )
    assert len(result["ready_jobs"]) == 2
    with pytest.raises(ValueError, match="Only a current"):
        claim(workspace, old)
    result = action(workspace, "observe", "source3", observation=observation)
    assert len(result["state"]["sources"]) == 3
    assert len(result["ready_jobs"]) == 2


def test_uncertain_send_persists_and_cannot_be_reclaimed(env):
    workspace, _, _ = env
    job = only_job(start(env))
    result = claim(workspace, job)
    assert len(result["ready_jobs"]) == 1 and result["unreconciled_jobs"] == [job]
    assert result["state"]["jobs"][job]["attempt"]["native_call"]["tool"] == "collaboration.spawn_agent"
    with pytest.raises(ValueError, match="reconcile"):
        action(workspace, "claim", "claim2", job_id=job, owner_lease_id="local_lease:test")
    assert handoffs.run(workspace)["state"]["jobs"][job]["status"] == "dispatch_intent"


def test_ownership_unknown_ids_and_ack_content(env):
    workspace, _, _ = env
    job = only_job(start(env))
    with pytest.raises(ValueError, match="labeled"):
        action(workspace, "claim", "badowner", job_id=job, owner_lease_id="pretend-native-turn")
    claim(workspace, job)
    response = write(workspace / "badresponse.json", {"message_id": None})
    with pytest.raises(ValueError, match="actual native task"):
        action(
            workspace,
            "acknowledge",
            "badack",
            job_id=job,
            owner_lease_id="local_lease:test",
            native_response=response,
        )
    result = ack(workspace, job)
    assert result["state"]["jobs"][job]["status"] == "running"
    with pytest.raises(ValueError, match="another owner"):
        action(workspace, "finish", "wrongowner", job_id=job, owner_lease_id="local_lease:other")


def test_physical_source_mutation_after_observe_blocks_dispatch(env):
    workspace, _, original = env
    job = only_job(start(env))
    Path(original["path"]).write_text("mutated")
    with pytest.raises(ValueError, match="Evidence bytes"):
        claim(workspace, job)


def result_receipt(workspace, job, status="analysis_approved", **kwargs):
    return write(
        workspace / "worker-receipt.json",
        {
            "job_id": job,
            "data_version": "a" * 64,
            "entity": "VIVA_AEROBUS",
            "period": "2026Q3",
            "status": status,
            **kwargs,
        },
    )


def test_approved_analysis_queues_only_its_dashboard_and_never_self_approves(env, monkeypatch):
    workspace, _, _ = env
    job = only_job(start(env))
    claim(workspace, job)
    ack(workspace, job)
    calls = []
    monkeypatch.setattr(handoffs, "verify_analysis", lambda *args: calls.append(args))
    receipt = result_receipt(workspace, job)
    result = action(
        workspace, "finish", "finish1", job_id=job, owner_lease_id="local_lease:test", receipt=receipt
    )
    assert len(calls) == 1 and len(result["ready_jobs"]) == 2
    downstream = [
        value
        for value in result["state"]["jobs"].values()
        if value["stage"] == "dashboard" and value["release_kind"] == "editorial"
    ]
    assert len(downstream) == 1 and downstream[0]["dependency"] == job
    assert downstream[0]["entity"] == "VIVA_AEROBUS"


def test_blocked_analysis_does_not_block_another_airline_or_dispatch_dashboard(env):
    workspace, observation, _ = env
    job = only_job(start(env))
    claim(workspace, job)
    ack(workspace, job)
    receipt = result_receipt(workspace, job, "blocked", reason="missing audit")
    action(workspace, "finish", "finish1", job_id=job, owner_lease_id="local_lease:test", receipt=receipt)
    other = copy.deepcopy(observation)
    other["item"]["product"] = "volaris_sec"
    result = action(workspace, "observe", "volaris1", observation=other)
    assert len(result["ready_jobs"]) == 3
    assert not any(value["release_kind"] == "editorial" for value in result["state"]["jobs"].values())


def test_receipt_cross_entity_or_version_cannot_finish(env):
    workspace, _, _ = env
    job = only_job(start(env))
    claim(workspace, job)
    ack(workspace, job)
    receipt = result_receipt(workspace, job, entity="INDUSTRY")
    with pytest.raises(ValueError, match="exact job"):
        action(workspace, "finish", "finish1", job_id=job, owner_lease_id="local_lease:test", receipt=receipt)


def test_context_refresh_records_no_public_impact_without_inventing_chart_update(env):
    workspace, observation, _ = env
    observation["item"]["product"] = "fuel"
    result = start(env)
    assert result["ready_jobs"] == [] and result["state"]["jobs"] == {}
    source = next(iter(result["state"]["sources"].values()))
    assert source["public_impact"]["status"] == "no_public_impact"


def test_meaningful_hash_ignores_provenance_and_row_order_but_keeps_small_revisions(tmp_path):
    root = tmp_path / "data/gold"
    root.mkdir(parents=True)
    path = root / "fact_example.parquet"
    frame = pd.DataFrame(
        {
            "period_id": ["2026Q3"] * 2,
            "metric": ["a", "b"],
            "value": [1.0, 2.0],
            "source_hash": ["old"] * 2,
            "ingested_at": ["old"] * 2,
        }
    )
    item = {"workspace": str(tmp_path), "product": "fuel", "period": "2026Q3"}

    def fingerprint(value):
        value.to_parquet(path)
        return handoffs.digest(
            handoffs.meaningful_data(
                item,
                {
                    "output_sha256": {"gold/fact_example": handoffs.file_hash(path)},
                },
            )
        )

    original = fingerprint(frame)
    moved = frame.iloc[::-1].assign(source_hash="new", ingested_at="now")
    assert fingerprint(moved) == original
    moved.loc[moved["metric"] == "a", "value"] += 0.0000000000000002
    assert fingerprint(moved) != original


def test_copied_state_writer_lock_and_future_transition_fail_closed(env):
    workspace, _, _ = env
    job = only_job(start(env))
    with collection.writer(workspace), pytest.raises(FileExistsError):
        claim(workspace, job)
    with pytest.raises(ValueError, match="future"):
        handoffs.run(
            workspace, action={"action": "claim", "operation_id": "future", "at": "2099-01-01T00:00:00Z"}
        )
    copied = workspace.parent / "copy"
    copied.mkdir()
    (copied / "state.json").write_bytes((workspace / "state.json").read_bytes())
    with pytest.raises(ValueError, match="copied"):
        handoffs.run(copied)


def test_older_inflight_analysis_result_preserved_without_downstream(env, monkeypatch):
    workspace, observation, _ = env
    job = only_job(start(env))
    claim(workspace, job)
    ack(workspace, job)
    action(workspace, "observe", "source2", observation={**observation, "synthetic_version": "d" * 64})
    monkeypatch.setattr(handoffs, "verify_analysis", lambda *args: None)
    receipt = result_receipt(workspace, job)
    result = action(
        workspace, "finish", "finish1", job_id=job, owner_lease_id="local_lease:test", receipt=receipt
    )
    assert result["state"]["jobs"][job]["status"] == "superseded"
    assert not any(value["release_kind"] == "editorial" for value in result["state"]["jobs"].values())


def test_analysis_approved_word_does_not_bypass_exact_capsule_binding(tmp_path, monkeypatch):
    from src.analysis_agent import lifecycle

    record = write(tmp_path / "record.json", {"entity_key": "VIVA_AEROBUS"})
    monkeypatch.setattr(lifecycle, "record_identity", lambda value: ("VIVA_AEROBUS", "2026Q3", "v1"))
    monkeypatch.setattr(lifecycle, "consumer_payload", lambda value: {"approved": True})
    monkeypatch.setattr(lifecycle, "verified_inputs", lambda value: ({}, {}, {}))
    with pytest.raises(ValueError, match="does not bind"):
        handoffs.verify_analysis(
            {"entity": "VIVA_AEROBUS", "period": "2026Q3"},
            {
                "source_binding": {
                    "item": {
                        "product": "viva_financials",
                        "period": "2026Q3",
                        "receipt_id": "r",
                        "candidate_as_of": NOW,
                    }
                },
                "checked": {"output_sha256": {}},
                "data_version": "x",
            },
            {"record": record, "data_version": "x"},
        )


def test_served_http_matches_exact_build_and_rejects_stale_payload(env, monkeypatch):
    import httpx

    from src.publish import verify

    workspace, _, _ = env
    root = workspace.parents[2]
    site = root / "site"
    site.mkdir()
    payload = b"validated-payload"
    (site / "data.json").write_bytes(payload)
    manifest = write(
        site / "publication_manifest.json",
        {
            "files": [{"path": "data.json", "sha256": handoffs.file_hash(site / "data.json")}],
        },
    )
    monkeypatch.setattr(verify, "verify_site", lambda path: [])
    result = {"site_path": str(site), "manifest": manifest}
    manifest_bytes = (site / "publication_manifest.json").read_bytes()

    def transport(request):
        body = manifest_bytes if request.url.path.endswith("publication_manifest.json") else payload
        return httpx.Response(200, content=body)

    client = httpx.Client
    monkeypatch.setattr(httpx, "Client", lambda **kwargs: client(transport=httpx.MockTransport(transport)))
    checked = handoffs.verify_served(result, ["data.json"])
    assert len(checked["files"]) == 2
    payload = b"stale-old-release"
    with pytest.raises(ValueError, match="Served bytes"):
        handoffs.verify_served(result, ["data.json"])
    with pytest.raises(ValueError, match="not part"):
        handoffs.verify_served(result, ["../secret"])


def test_revocation_in_canonical_lifecycle_blocks_finish(env, monkeypatch):
    from src.analysis_agent import lifecycle

    workspace, _, _ = env
    job = only_job(start(env))
    claim(workspace, job)
    ack(workspace, job)
    record = write(workspace / "analysis.json", {})
    monkeypatch.setattr(lifecycle, "record_identity", lambda value: ("VIVA_AEROBUS", "2026Q3", "v1"))

    def revoked(value):
        raise ValueError("Publication blocked: revoked approval")

    monkeypatch.setattr(lifecycle, "consumer_payload", revoked)
    receipt = result_receipt(workspace, job, record=record)
    with pytest.raises(ValueError, match="revoked"):
        action(workspace, "finish", "revoked", job_id=job, owner_lease_id="local_lease:test", receipt=receipt)
    assert len(handoffs.run(workspace)["state"]["jobs"]) == 2


def test_publication_arrival_needs_its_original_but_no_other_report_or_round_barrier(tmp_path, monkeypatch):
    monkeypatch.setattr(collection, "ROOT", tmp_path)
    workspace = tmp_path / "tmp/source-updates/outbox"
    candidate = tmp_path / "tmp/source-updates/candidate"
    calendar_path = tmp_path / "tmp/source-updates/calendar/state.json"
    calendar = write(
        calendar_path,
        {
            "coordinator_id": "airlines-tracker-source-calendar",
            "automation_id": "synthetic-id",
            "workspace": str(calendar_path.parent),
            "activation_authorized": True,
            "tasks": {},
        },
    )
    original = write(candidate / "original.json", {"synthetic": True})
    frame = pd.DataFrame({"value": [1.0], "unit": ["USD"], "source_hash": [original["sha256"]]})
    path = candidate / "data/gold/fact_example.parquet"
    path.parent.mkdir(parents=True)
    frame.to_parquet(path)
    item = {
        "id": "single",
        "required": True,
        "workspace": str(candidate),
        "period": "2026Q3",
        "product": "viva_financials",
        "candidate_as_of": NOW,
    }
    checked = {
        "status": "checks_passed",
        "latest_source_availability_verified": True,
        "output_sha256": {"gold/fact_example": handoffs.file_hash(path)},
    }
    monkeypatch.setattr(handoffs.readiness, "preflight", lambda recipe, target: [recipe["items"][0]])
    monkeypatch.setattr(handoffs.readiness, "check_task", lambda *args: checked)
    observation = {
        "item": item,
        "as_of": NOW,
        "calendar_state": calendar,
        "authorization_reference": "synthetic-current-authority",
        "change_reason": "report arrived",
        "mode": "validated_publication_arrival",
        "publication_evidence": original,
    }
    monkeypatch.setattr(handoffs.semantic, "primary_context", lambda value: {"synthetic": "context"})
    verified = handoffs.verify_source(observation, workspace)
    assert verified["checked"] == checked
    snapshot = handoffs.checked_ref(verified["calendar_snapshot"])
    calendar_path.write_text('{"legitimate_later_progress":true}')
    assert json.loads(snapshot.read_text())["automation_id"] == "synthetic-id"
    calendar = write(
        calendar_path,
        {
            "coordinator_id": "airlines-tracker-source-calendar",
            "automation_id": "synthetic-id",
            "workspace": str(calendar_path.parent),
            "activation_authorized": True,
            "tasks": {},
        },
    )
    observation["calendar_state"] = calendar
    unrelated = write(candidate / "unrelated.json", {"unrelated": True})
    with pytest.raises(ValueError, match="not the original"):
        handoffs.verify_source({**observation, "publication_evidence": unrelated}, workspace)


def test_dashboard_build_writers_are_serial_even_when_sources_are_independent(env):
    workspace, observation, _ = env
    result = start(env)
    first = next(k for k, v in result["state"]["jobs"].items() if v["stage"] == "dashboard")
    other = copy.deepcopy(observation)
    other["item"]["product"] = "volaris_sec"
    result = action(workspace, "observe", "source2", observation=other)
    second = next(k for k, v in result["state"]["jobs"].items() if v["stage"] == "dashboard" and k != first)
    claim(workspace, first)
    with pytest.raises(ValueError, match="Another dashboard writer"):
        action(workspace, "claim", "claim2", job_id=second, owner_lease_id="local_lease:test")


def test_valid_old_dashboard_is_not_proof_of_new_source_consumption(monkeypatch):
    import sys
    from types import ModuleType

    module = ModuleType("src.publish.issuer_scope")
    source = {
        "source_binding": {
            "item": {
                "product": "viva_financials",
                "period": "2026Q3",
                "receipt_id": "retained",
                "candidate_as_of": NOW,
            }
        },
        "checked": {"output_sha256": {"gold/fact_test": "a" * 64}},
    }
    binding = handoffs.expected_binding(source)
    spec = {
        "entity_key": "VIVA_AEROBUS",
        "period_id": "2026Q3",
        "stage": "data_only",
        "source_binding": binding,
    }
    module.anchor = lambda: spec
    monkeypatch.setitem(sys.modules, "src.publish.issuer_scope", module)
    job = {"release_kind": "data", "entity": "VIVA_AEROBUS", "period": "2026Q3"}
    handoffs.verify_release_binding(job, source)
    spec["source_binding"] = {**binding, "receipt_id": "older-candidate"}
    with pytest.raises(ValueError, match="does not consume"):
        handoffs.verify_release_binding(job, source)
    spec["source_binding"] = binding
    spec["stage"] = "editorial_only"
    with pytest.raises(ValueError, match="does not consume"):
        handoffs.verify_release_binding(job, source)


def test_invalid_scoped_proof_cannot_fall_back_to_generic_site_verification(env, monkeypatch):
    import sys
    from types import ModuleType

    from src.publish import verify

    workspace, _, _ = env
    site = workspace.parents[2] / "site"
    site.mkdir()
    manifest = write(site / "publication_manifest.json", {})
    write(site / "issuer-publication.json", {"invalid": True})
    module = ModuleType("src.publish.issuer_scope")
    module.verify_issuer = lambda path: ["invalid strict proof"]
    monkeypatch.setitem(sys.modules, "src.publish.issuer_scope", module)
    monkeypatch.setattr(verify, "verify_site", lambda path: [])
    from scripts import check_pages_publication

    monkeypatch.setattr(
        check_pages_publication, "verifier_for", lambda site, repo: "src.publish.issuer_scope"
    )
    with pytest.raises(ValueError, match="invalid strict proof"):
        handoffs.verify_dashboard({"site_path": str(site), "manifest": manifest})


def test_no_visual_change_receipt_is_replayed_not_accepted_from_status(tmp_path, monkeypatch):
    import sys
    from types import ModuleType

    from scripts.source_update_handoff_nochange import verify

    module = ModuleType("src.publish.issuer_update")
    observed = {"status": "no_visual_change", "source_binding": {"exact": True}}
    module.verify_no_visual_change = lambda *args, **kwargs: observed
    monkeypatch.setitem(sys.modules, "src.publish.issuer_update", module)
    result = {
        "status": "no_visual_change",
        "package": write(tmp_path / "package.json", {}),
        "equivalence_proof": write(tmp_path / "proof.json", observed),
    }
    job = {"entity": "VIVA_AEROBUS", "stage": "dashboard", "release_kind": "data"}
    verify(job, {}, result, {"exact": True}, tmp_path)
    observed["source_binding"] = {"different": True}
    with pytest.raises(ValueError, match="differs from"):
        verify(job, {}, result, {"exact": True}, tmp_path)


def test_no_material_change_finishes_without_new_editorial_job(env, monkeypatch):
    from scripts import source_update_handoff_nochange

    workspace, _, _ = env
    job = only_job(start(env))
    claim(workspace, job)
    ack(workspace, job)
    calls = []
    monkeypatch.setattr(source_update_handoff_nochange, "verify", lambda *args: calls.append(args))
    receipt = result_receipt(workspace, job, "no_material_analysis_change")
    result = action(
        workspace, "finish", "nochange1", job_id=job, owner_lease_id="local_lease:test", receipt=receipt
    )
    assert calls and result["state"]["jobs"][job]["status"] == "no_change"
    assert not any(value["release_kind"] == "editorial" for value in result["state"]["jobs"].values())
