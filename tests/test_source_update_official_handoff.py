"""Synthetic retained originals test the consumer boundary, never real publication."""

import copy
import hashlib
import json
from pathlib import Path

import pandas as pd
import pytest

from scripts import source_update_handoff_nochange as nochange
from scripts import source_update_handoffs as handoffs
from scripts import source_update_monthly_handoff as monthly
from src.dashboard.official_routes_contract import encoded
from src.source_updates import official_routes_handoff as official
from tests.test_source_update_handoffs import ack, action, claim, only_job, start, write
from tests.test_source_update_handoffs import env as env


@pytest.fixture
def official_env(env, monkeypatch):
    workspace, observation, original = env
    root = workspace.parents[2]
    for name in official.CODE:
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("Synthetic consumer code", encoding="utf-8")
    observation["item"].update(product="afac_margins", period="2026M10", source_period="2026M09")
    snapshot = write(
        workspace / "evidence/calendar.json",
        {
            "coordinator_id": "airlines-tracker-source-calendar",
            "activation_authorized": True,
            "automation_id": "synthetic-existing-id",
            "consumers": ["official_routes"],
            "conditional_products": ["afac_margins"],
            "run_id": "synthetic-map-v2",
            "continuation": {"synthetic": True},
        },
    )
    outputs = {}
    for name, hashes in (("fact_afac_retained_margins", ["1" * 64, "2" * 64]),):
        path = Path(observation["item"]["workspace"]) / "data/gold" / (name + ".parquet")
        path.parent.mkdir(parents=True, exist_ok=True)
        pd.DataFrame({"source_hash": hashes, "value": [1, 2]}).to_parquet(path)
        outputs["gold/" + name] = handoffs.file_hash(path)
    base_verify = handoffs.verify_candidate

    def verify(value, target):
        return {
            **base_verify(value, target),
            "calendar_snapshot": snapshot,
            "checked": {"status": "checks_passed", "output_sha256": outputs.copy()},
        }

    monkeypatch.setattr(handoffs, "verify_source", verify)
    monkeypatch.setattr(handoffs, "verify_candidate", verify)
    output = start(env)
    job_id = only_job(output)
    job = output["state"]["jobs"][job_id]
    source = output["state"]["sources"][job["source_id"]]
    payload = json.loads((Path(__file__).parent / "fixtures/official-routes.example.json").read_bytes())
    raw = encoded(payload)
    profile = {
        "period": "2026M09",
        "dataset_version": payload["dataset_version"],
        "output_sha256": hashlib.sha256(raw).hexdigest(),
    }
    selection = {
        "source_as_of": "2026-11-05T00:00:00Z",
        "afac": [{"period": "2026M09", "routes": {"sha256": "1" * 64}, "carriers": {"sha256": "2" * 64}}],
        "bts": [{"period": "2026M07", "archive": {"sha256": "3" * 64}}],
    }
    from src.publish import official_routes_projection, source_data_scope
    from src.source_updates import catalog

    monkeypatch.setattr(catalog, "ROOT", root)
    # The expensive original parser/gate has its own retained-source suite; boundary is explicit.
    monkeypatch.setattr(official_routes_projection, "_replay", lambda p, repo: (raw, selection, []))
    _, _, binding = official.replay_profile(source, profile, root)
    spec = dict(
        product="official_routes",
        period_id=profile["period"],
        source_binding=binding,
        projection=dict(
            profile=profile,
            dataset_version=payload["dataset_version"],
            payload_sha256=hashlib.sha256(raw).hexdigest(),
        ),
        data_files=source_data_scope.pins({official.PUBLIC_PATH: raw}),
        frontend_files=[],
        baseline_commit="b" * 40,
        producer_code_version="c" * 64,
        contract_changes={},
        authorization_sha256="d" * 64,
    )
    monkeypatch.setattr(source_data_scope, "anchor", lambda repo: spec)
    gate_calls = []
    monkeypatch.setattr(
        source_data_scope, "verify_source_data", lambda site, repo: gate_calls.append(site) or []
    )
    return dict(
        env=env,
        root=root,
        job=job,
        source=source,
        raw=raw,
        payload=payload,
        profile=profile,
        selection=selection,
        spec=spec,
        gate_calls=gate_calls,
        outputs=outputs,
        snapshot=snapshot,
    )


def consent(context):
    from src.publish.source_data_scope import scope

    value = dict(
        schema_version="source_data_authorization_v1",
        status="authorized",
        scope=scope(context["spec"]),
        owner_consent=dict(
            source_reference="synthetic-test-only",
            instruction="synthetic exact scope",
            received_at="2026-11-04T00:00:00Z",
        ),
    )
    raw = encoded(value)
    digest = hashlib.sha256(raw).hexdigest()
    path = context["root"] / "analysis_runs/dashboard_updates/authorizations" / (digest + ".json")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)
    context["spec"]["authorization_sha256"] = digest
    return path


def test_opt_in_outbox_pins_source_and_official_consumers_without_approving(official_env):
    ctx = official_env
    assert ctx["job"]["release_kind"] == "source_data" and ctx["job"]["entity"] is None
    impact = ctx["source"]["public_impact"]
    assert impact["status"] == "official_routes_candidate_requires_exact_release"
    assert set(impact["consumer_code"]) == set(official.CODE)
    assert (
        monthly.release_kind("afac_margins")
        == monthly.release_kind("bts_segments")
        == "source_dependency_assessment"
    )
    assert "never use a legacy" in monthly.scope_or_financial("afac_margins", ctx["source"])
    with pytest.raises(ValueError, match="evidence changed|missing"):
        official.verify_release(ctx["job"], ctx["source"], ctx["root"])
    assert ctx["gate_calls"] == []


def test_finish_requires_exact_authority_and_real_gate_after_readiness(official_env, monkeypatch):
    ctx = official_env
    workspace = ctx["env"][0]
    job = ctx["job"]["job_id"]
    claim(workspace, job)
    ack(workspace, job)
    monkeypatch.setattr(handoffs, "verify_dashboard", lambda result: None)
    receipt = {
        "status": "site_built_verified",
        "job_id": job,
        "data_version": "a" * 64,
        "entity": None,
        "period": "2026M10",
    }
    ref = write(workspace / "build.json", receipt)
    before = (workspace / "state.json").read_bytes()
    with pytest.raises(ValueError, match="missing"):
        action(workspace, "finish", "finish", job_id=job, owner_lease_id="local_lease:test", receipt=ref)
    assert (workspace / "state.json").read_bytes() == before
    consent(ctx)
    from src.publish import source_data_scope

    monkeypatch.setattr(
        source_data_scope, "verify_source_data", lambda site, root: ["synthetic gate rejection"]
    )
    with pytest.raises(ValueError, match="real source-data gate"):
        action(workspace, "finish", "finish", job_id=job, owner_lease_id="local_lease:test", receipt=ref)
    assert (workspace / "state.json").read_bytes() == before
    monkeypatch.setattr(source_data_scope, "verify_source_data", lambda site, root: [])
    result = action(workspace, "finish", "finish", job_id=job, owner_lease_id="local_lease:test", receipt=ref)
    assert result["state"]["jobs"][job]["status"] == "completed"
    assert "served_verification" not in result["state"]["jobs"][job]


@pytest.mark.parametrize("status", ["checks_passed", "candidate", "source_dependency_assessment"])
def test_candidate_and_assessment_are_never_finish_receipts(official_env, status):
    workspace = official_env["env"][0]
    job = official_env["job"]["job_id"]
    claim(workspace, job)
    ack(workspace, job)
    ref = write(
        workspace / "candidate.json",
        {"status": status, "job_id": job, "data_version": "a" * 64, "entity": None, "period": "2026M10"},
    )
    with pytest.raises(ValueError, match="verified build"):
        action(workspace, "finish", "bad-finish", job_id=job, owner_lease_id="local_lease:test", receipt=ref)
    assert handoffs.run(workspace)["state"]["jobs"][job]["status"] == "running"


@pytest.mark.parametrize("mutation", ["native_hash", "native_period", "dataset", "coverage", "release_kind"])
def test_exact_source_and_release_pins_cannot_be_substituted(official_env, mutation):
    ctx = official_env
    consent(ctx)
    if mutation == "native_hash":
        ctx["selection"]["afac"][0]["routes"]["sha256"] = "9" * 64
    elif mutation == "native_period":
        ctx["selection"]["afac"][0]["period"] = "2026M08"
    elif mutation == "dataset":
        ctx["spec"]["projection"]["dataset_version"] = "9" * 64
    elif mutation == "coverage":
        ctx["spec"]["data_files"][0]["sha256"] = "9" * 64
    else:
        ctx["job"]["release_kind"] = "source_dependency_assessment"
    with pytest.raises(ValueError):
        official.verify_release(ctx["job"], ctx["source"], ctx["root"])
    assert ctx["gate_calls"] == []


def test_nochange_uses_official_json_full_coverage_and_never_legacy(official_env, monkeypatch):
    ctx = official_env
    from scripts import source_update_bts_nochange
    from src.publish import source_data_update

    monkeypatch.setattr(source_update_bts_nochange, "verify", lambda *a, **kw: pytest.fail("legacy fallback"))
    profile = write(ctx["env"][0] / "profile.json", ctx["profile"])
    calls = []

    def physical_gate(path, binding, *, site):
        calls.append(binding)
        assert binding["product"] == "official_routes" and site == ctx["root"] / "site"
        return dict(status="no_visual_change", source_binding=binding, data_files=ctx["spec"]["data_files"])

    monkeypatch.setattr(source_data_update, "verify_no_visual_change", physical_gate)
    proof = official.verify_nochange(ctx["source"], Path(profile["path"]), ctx["root"])
    assert proof["dataset_version"] == ctx["payload"]["dataset_version"]
    assert len(proof["coverage"]) == len(ctx["payload"]["networks"])
    result = {
        "status": "no_visual_change",
        "source_profile": profile,
        "equivalence_proof": write(ctx["env"][0] / "proof.json", proof),
    }
    nochange.verify(ctx["job"], ctx["source"], result, handoffs.expected_binding(ctx["source"]), ctx["root"])
    assert len(calls) == 2
    ctx["spec"]["data_files"][0]["sha256"] = "9" * 64
    with pytest.raises(ValueError, match="complete official dataset"):
        official.verify_nochange(ctx["source"], Path(profile["path"]), ctx["root"])


def test_revised_source_and_new_calendar_month_queue_independent_versions(official_env):
    workspace, observation, _ = official_env["env"]
    revised = action(
        workspace, "observe", "revision", observation={**observation, "synthetic_version": "f" * 64}
    )
    assert len(revised["state"]["sources"]) == 2 and len(revised["ready_jobs"]) == 1
    next_month = copy.deepcopy(observation)
    next_month["item"]["period"] = "2026M11"
    result = action(workspace, "observe", "newmonth", observation=next_month)
    assert len(result["state"]["sources"]) == 3 and len(result["ready_jobs"]) == 2
    assert {s["period"] for s in result["state"]["sources"].values()} == {"2026M10", "2026M11"}
    assert all(j["status"] == "planned" for j in result["state"]["jobs"].values())
    assert result["publication_requests"] == result["schedule_changes"] == 0


def test_mode_cannot_silently_change_existing_outbox(official_env):
    ctx = official_env
    prior = copy.deepcopy(ctx["source"])
    prior.pop("calendar_snapshot")
    with pytest.raises(ValueError, match="NEW versioned outbox"):
        official.same_mode(prior, ctx["source"])


def test_bts_nochange_binds_actual_observed_month_and_zip_not_legacy(official_env, monkeypatch):
    ctx = official_env
    source = copy.deepcopy(ctx["source"])
    item = source["source_binding"]["item"]
    item.update(product="bts_segments", source_period="2026M07")
    path = Path(item["workspace"]) / "data/silver/bts_t100_segment.parquet"
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame({"source_hash": ["3" * 64], "departures_performed": [7]}).to_parquet(path)
    source["checked"]["output_sha256"].update(
        {
            "silver/bts_t100_segment": handoffs.file_hash(path),
            "gold/fact_route_traffic": next(iter(ctx["outputs"].values())),
            "gold/bridge_record_lineage": "f" * 64,
        }
    )
    # The BTS native verifier requires the pinned route fact in addition to its literal ZIP hash.
    fact = Path(item["workspace"]) / "data/gold/fact_route_traffic.parquet"
    fact.write_bytes((fact.parent / "fact_afac_retained_margins.parquet").read_bytes())
    from scripts import source_update_bts_nochange
    from src.publish import source_data_update

    monkeypatch.setattr(source_update_bts_nochange, "verify", lambda *a, **kw: pytest.fail("legacy fallback"))
    monkeypatch.setattr(
        source_data_update,
        "verify_no_visual_change",
        lambda profile, binding, site: dict(
            status="no_visual_change", source_binding=binding, data_files=ctx["spec"]["data_files"]
        ),
    )
    profile = write(ctx["env"][0] / "bts-profile.json", ctx["profile"])
    result = official.verify_nochange(source, Path(profile["path"]), ctx["root"])
    assert result["dataset_version"] == ctx["payload"]["dataset_version"]
    assert source["source_binding"]["item"]["period"] == "2026M10"
    ctx["selection"]["bts"][0]["period"] = "2026M06"
    with pytest.raises(ValueError, match="exact native source edition"):
        official.verify_nochange(source, Path(profile["path"]), ctx["root"])


def test_revised_original_with_same_business_values_still_assesses_official_map(official_env):
    ctx = official_env
    workspace, observation, _ = ctx["env"]
    revised = copy.deepcopy(observation)
    candidate = ctx["root"] / "tmp/source-updates/revised"
    path = candidate / "data/gold/fact_afac_retained_margins.parquet"
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame({"source_hash": ["8" * 64, "2" * 64], "value": [1, 2]}).to_parquet(path)
    revised["item"]["workspace"] = str(candidate)
    ctx["outputs"]["gold/fact_afac_retained_margins"] = handoffs.file_hash(path)
    result = action(workspace, "observe", "same-values-revised-original", observation=revised)
    assert len(result["state"]["sources"]) == 2 and len(result["ready_jobs"]) == 1
    assert len({s["data_version"] for s in result["state"]["sources"].values()}) == 1
    assert result["state"]["jobs"][only_job(result)]["status"] == "planned"
