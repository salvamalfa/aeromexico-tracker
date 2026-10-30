"""Persistent per-product outbox from verified source candidates to native agents.

The host coordinating agent invokes returned envelopes. This CLI does not spawn
workers, promote Gold, approve analysis, publish, or install another schedule.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from datetime import UTC, datetime
from pathlib import Path

from scripts import source_update_handoff_routing as routing
from scripts import source_update_semantic_identity as semantic
from scripts.source_update_coordinator import digest, load, persist
from src.source_updates import readiness
from src.source_updates.calendar import local_time
from src.source_updates.catalog import ROOT
from src.source_updates.closed_editions import accepted as source_evidence_accepted
from src.source_updates.collection import safe_workspace, writer

ENTITIES = {"am_financials": "AEROMEXICO", "volaris_sec": "VOLARIS", "viva_financials": "VIVA_AEROBUS"}
IMPACTS = {
    **{k: [v] for k, v in ENTITIES.items()},
    **{k: [] for k in ("banxico", "fuel", "equities")},
    "aerocivil": ["AEROMEXICO"],
}
CONSUMERS = [
    "src/dashboard/executive_summary.py",
    "src/dashboard/market.py",
    "src/web_export/executive.py",
    "src/web_export/market.py",
    "src/dashboard/international_routes.py",
    "src/dashboard/recorded_movements.py",
    "src/web_export/flights.py",
]
PROVENANCE = semantic.LEGACY_PROVENANCE

SKILLS = {
    "analysis": ".agents/skills/aeromexico-tracker-analysis/SKILL.md",
    "dashboard": ".agents/skills/airline-update-dashboard/SKILL.md",
}


def file_hash(path: Path) -> str:
    if not path.is_file() or path.is_symlink():
        raise ValueError(f"Missing regular evidence file: {path}")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def file_ref(path: Path) -> dict:
    path = path.absolute()
    return {"path": str(path), "sha256": file_hash(path)}


def checked_ref(value: dict) -> Path:
    path = Path(value["path"])
    if not path.is_absolute() or path.resolve() != path or file_hash(path) != value["sha256"]:
        raise ValueError("Evidence bytes/path differ from their exact reference")
    return path


def meaningful_data(item: dict, checked: dict) -> dict:
    """Ignore capture/lineage churn; preserve every numerical bit and business field."""
    import pandas as pd

    def scalar(value):
        if isinstance(value, (list, tuple)):
            return [scalar(part) for part in value]
        if value is None or pd.isna(value):
            return None
        if hasattr(value, "item"):
            value = value.item()
        if isinstance(value, float):
            if not math.isfinite(value):
                raise ValueError("Nonfinite numerical input")
            return {"float_hex": value.hex()}
        return value if isinstance(value, (str, bool, int)) else str(value)

    tables = {}
    for name, expected in sorted(checked["output_sha256"].items()):
        if not name.startswith("gold/fact_"):
            continue
        path = Path(item["workspace"]) / "data" / (name + ".parquet")
        if file_hash(path) != expected:
            raise ValueError("Verified candidate changed while fingerprinting")
        frame = pd.read_parquet(path)
        columns = sorted(set(frame.columns) - PROVENANCE)
        rows = [{key: scalar(row[key]) for key in columns} for row in frame.to_dict("records")]
        tables[name] = sorted(rows, key=lambda row: json.dumps(row, sort_keys=True, allow_nan=False))
    if not tables or not any(tables.values()):
        raise ValueError("No nonempty verified business fact table for this product")
    return {"product": item["product"], "period": item["period"], "tables": tables}


def verify_source(observation: dict, workspace: Path) -> dict:
    item = observation["item"]
    product = item["product"]
    if product not in IMPACTS:
        raise ValueError("Product has no authorized impact route; preserve its source result separately")
    if not observation.get("authorization_reference") or not observation.get("change_reason"):
        raise ValueError("Explicit authorization provenance and change reason are required")
    state_path = checked_ref(observation["calendar_state"])
    state_bytes = state_path.read_bytes()
    if hashlib.sha256(state_bytes).hexdigest() != observation["calendar_state"]["sha256"]:
        raise ValueError("Canonical calendar changed while observing; read its current reference")
    calendar = json.loads(state_bytes)
    if calendar.get("coordinator_id") != "airlines-tracker-source-calendar" or not calendar.get(
        "automation_id"
    ):
        raise ValueError("A bound canonical source calendar is required")
    if (
        Path(calendar["workspace"]) / "state.json" != state_path
        or calendar.get("activation_authorized") is not True
    ):
        raise ValueError("Source calendar identity/path/activation is not reconciled")
    mode = observation.get("mode")
    if mode not in {"scheduled_result", "recovery_from_validated_result", "validated_publication_arrival"}:
        raise ValueError("Distinguish the scheduled result from recovery of existing evidence")
    if mode == "validated_publication_arrival":
        # A confirmed individual report does not wait for the consolidated round.
        if product not in ENTITIES:
            raise ValueError("Publication-arrival route is limited to the three issuer financials")
        checked_ref(observation["publication_evidence"])
    else:
        task = calendar["tasks"][observation["source_task_key"]]
        if (task["product"], task["period"]) != (product, item["period"]):
            raise ValueError("Source task does not identify this product and period")
        if mode == "scheduled_result" and task["status"] != "completed":
            raise ValueError("Scheduled source result has not completed in its actual ledger")
    if mode == "scheduled_result":
        dispatch = task["dispatches"][-1]
        candidate = Path(item["workspace"])
        worker = Path(dispatch["worker_workspace"])
        if dispatch.get("delivery") != "reconciled_completed" or not candidate.is_relative_to(worker):
            raise ValueError("Candidate is not inside the reconciled scheduled worker workspace")
        receipt = task["receipts"][-1]
        checked_ref({"path": str(state_path.parent / receipt["file"]), "sha256": receipt["sha256"]})
    verified = verify_candidate(observation, workspace)
    snapshots = workspace / "evidence"
    snapshots.mkdir(parents=True, exist_ok=True)
    snapshot = snapshots / f"calendar-{observation['calendar_state']['sha256']}.json"
    if snapshot.exists():
        checked_ref({"path": str(snapshot), "sha256": observation["calendar_state"]["sha256"]})
    else:
        with snapshot.open("xb") as stream:
            stream.write(state_bytes)
            stream.flush()
            os.fsync(stream.fileno())
    return {**verified, "calendar_snapshot": file_ref(snapshot)}


def verify_candidate(observation: dict, workspace: Path) -> dict:
    item, cutoff = routing.native_item(observation["item"]), observation["as_of"]
    recipe = {"version": 1, "as_of": cutoff, "required_items": [item["id"]], "items": [item]}
    selected = readiness.preflight(recipe, workspace)[0]
    checked = readiness.check_task(selected, item["candidate_as_of"], cutoff)
    if not source_evidence_accepted(selected, checked):
        raise ValueError("This product needs its own verified availability or exact closed edition")
    if item["product"] == "aerocivil":
        routing.verify_movement_acceptance(checked)
    if observation.get("mode") == "validated_publication_arrival":
        import pandas as pd

        original = checked_ref(observation["publication_evidence"])
        source_hashes = set()
        for name in checked["output_sha256"]:
            if name.startswith("gold/fact_"):
                frame = pd.read_parquet(Path(item["workspace"]) / "data" / (name + ".parquet"))
                if "source_hash" in frame:
                    source_hashes.update(frame["source_hash"].dropna().tolist())
        if file_hash(original) not in source_hashes:
            raise ValueError("Publication document is not the original used by the verified financial rows")
    identity = meaningful_data(observation["item"], checked)
    return {
        "checked": checked,
        **semantic.versions(observation["item"], identity),
        "source_binding": observation,
    }


def enqueue(
    state: dict,
    stage: str,
    source_id: str,
    entity: str | None,
    dependency: str | None = None,
    release_kind: str | None = None,
):
    source = state["sources"][source_id]
    identity = {
        "stage": stage,
        "source_id": source_id,
        "entity": entity,
        "dependency": dependency,
        "release_kind": release_kind,
    }
    job_id = digest(identity)
    state["jobs"].setdefault(
        job_id,
        {
            **identity,
            "job_id": job_id,
            "period": source["period"],
            "status": "planned",
            "attempt": None,
            "native_response": None,
            "result": None,
        },
    )


def observe(state: dict, observation: dict, workspace: Path):
    verified = verify_source(observation, workspace)
    if "calendar_snapshot" in verified:
        observation = {**observation, "calendar_snapshot": verified["calendar_snapshot"]}
    item = observation["item"]
    key = f"{item['product']}:{item['period']}"
    previous_id = state["heads"].get(key)
    prior = state["sources"].get(previous_id)
    if prior and semantic.same_observation(
        prior, verified, lambda binding: verify_candidate(binding, workspace)
    ):
        # New availability/capture evidence is retained without creating another thesis.
        if observation not in prior["observations"]:
            prior["observations"].append(observation)
        return
    source_id = digest(
        {
            "product": item["product"],
            "period": item["period"],
            "version": verified["data_version"],
            "previous_source_id": previous_id,
        }
    )
    state["sources"][source_id] = {
        **verified,
        "product": item["product"],
        "period": item["period"],
        "observations": [observation],
        "previous_source_id": state["heads"].get(key),
        "public_impact": {
            "status": routing.impact_status(item["product"]),
            "consumer_code": {name: file_hash(ROOT / name) for name in CONSUMERS},
        },
    }
    state["heads"][key] = source_id
    if item["product"] in ENTITIES:
        enqueue(state, "analysis", source_id, ENTITIES[item["product"]])
        enqueue(state, "dashboard", source_id, ENTITIES[item["product"]], release_kind="data")
    elif item["product"] == "aerocivil":
        enqueue(state, "dashboard", source_id, "AEROMEXICO", release_kind="movements")
    # Macro inputs currently have no public chart consumer. Preserve the result
    # without inventing a dashboard job or forcing an unrelated thesis rewrite.


def is_current(state: dict, job: dict) -> bool:
    source = state["sources"][job["source_id"]]
    return state["heads"][f"{source['product']}:{source['period']}"] == job["source_id"]


def envelope(state: dict, job: dict) -> dict:
    source = state["sources"][job["source_id"]]
    path = ROOT / SKILLS[job["stage"]]
    skill = file_ref(path)
    instruction = {
        "job": job,
        "source": source,
        "skill": skill,
        "ledger": str(Path(state["workspace"]) / "state.json"),
        "scope": IMPACTS[source["product"]],
        "publication_scope": "AEROMEXICO,VIVA_AEROBUS,VOLARIS; exclude Industria and unrelated products",
        "dependency_result": state["jobs"][job["dependency"]]["result"] if job["dependency"] else None,
    }
    return {
        "tool": "collaboration.spawn_agent",
        "arguments": {
            "task_name": (
                f"{job['stage']}_{(job['entity'] or source['product']).lower()}_"
                f"{job['period'].lower()}_{job['job_id'][:10]}"
            ),
            "message": (
                "Lee la skill exacta y verifica su SHA. Ejecuta este handoff real con los insumos cerrados. "
                "Conserva versiones, fechas y fuentes. No escribas el ledger común "
                "ni adquieras otras fuentes. "
                "No esperes a otras aerolíneas. Si bloquea, conserva el resultado y explica el control. "
                "Devuelve un recibo JSON con job_id, data_version, entity, period, status "
                "y referencias físicas/hash. "
                "El coordinador reconcilia la intención; no te declares publicado desde un build. "
                + json.dumps(instruction, ensure_ascii=False, sort_keys=True)
            ),
        },
    }


def expected_binding(source: dict) -> dict:
    item = routing.native_item(source["source_binding"]["item"])
    return {
        "product": item["product"],
        "period": item["period"],
        "receipt_id": item["receipt_id"],
        "candidate_as_of": item["candidate_as_of"],
        "output_sha256": source["checked"]["output_sha256"],
    }


def verify_analysis(job: dict, source: dict, result: dict) -> dict:
    from src.analysis_agent import lifecycle

    record = load(checked_ref(result["record"]))
    entity, period, _ = lifecycle.record_identity(record)
    if (entity, period) != (job["entity"], job["period"]):
        raise ValueError("Analysis record entity/period differs from the handoff")
    # Canonical lifecycle performs exact version, evidence, audit and approval checks.
    payload = lifecycle.consumer_payload(record)
    package, _, _ = lifecycle.verified_inputs(record)
    binding = package.get("source_binding")
    if binding != expected_binding(source):
        raise ValueError("Approved evidence capsule does not bind this exact verified source candidate")
    if result["data_version"] != source["data_version"]:
        raise ValueError("Analysis did not consume this exact source data version")
    return payload


def verify_release_binding(job: dict, source: dict):
    routing.verify_release(job, source, expected_binding(source))


def verify_dashboard(result: dict) -> None:
    site = Path(result["site_path"])
    if site != (ROOT / "site").absolute():
        raise ValueError("Dashboard result must identify this checkout's generated site")
    manifest = checked_ref(result["manifest"])
    if manifest != site / "publication_manifest.json":
        raise ValueError("Publication manifest is not inside the verified site")
    # Select one current, witnessed publication; a failed strong gate never falls back.
    errors = routing.verify_site(site, ROOT)
    if errors:
        raise ValueError(f"Generated site failed its canonical verification: {errors}")


def verify_served(result: dict, files: list[str]) -> dict:
    """Explicit post-deployment read, separate from the offline build receipt."""
    import httpx

    verify_dashboard(result)
    site = Path(result["site_path"])
    manifest = load(checked_ref(result["manifest"]))
    known = {entry["path"]: entry["sha256"] for entry in manifest["files"]}
    known["publication_manifest.json"] = result["manifest"]["sha256"]
    if not isinstance(files, list) or not files or len(set(files)) != len(files):
        raise ValueError("Choose the nonempty exact changed payloads and pages to verify")
    for name in files:
        if name not in known or (site / name).resolve() != site / name:
            raise ValueError("Served QA path is not part of the verified publication manifest")
    observations = []
    with httpx.Client(follow_redirects=False, timeout=30) as client:
        for name in dict.fromkeys(["publication_manifest.json", *files]):
            url = "https://salvamalfa.github.io/aeromexico-tracker/" + name
            response = client.get(url)
            actual = hashlib.sha256(response.content).hexdigest()
            if response.status_code != 200 or actual != known[name]:
                raise ValueError(f"Served bytes do not match the verified build: {url}")
            observations.append({"url": url, "http_status": 200, "sha256": actual})
    return {"checked_at": datetime.now(UTC).isoformat(), "files": observations}


def transition(state: dict, action: dict, workspace: Path):
    kind = action["action"]
    if kind == "observe":
        observe(state, action["observation"], workspace)
        return
    job = state["jobs"][action["job_id"]]
    if kind in {"claim", "continue_existing_worker"} and job["stage"] == "dashboard":
        if any(
            other["job_id"] != job["job_id"]
            and other["stage"] == "dashboard"
            and other["status"] in {"dispatch_intent", "running", "completed"}
            for other in state["jobs"].values()
        ):
            raise ValueError("Another dashboard writer must be reconciled before this handoff")
    if kind == "claim":
        if job["status"] != "planned" or not is_current(state, job):
            raise ValueError("Only a current planned job can be sent; reconcile existing intent")
        source = state["sources"][job["source_id"]]
        fresh = verify_candidate(source["source_binding"], workspace)
        if not semantic.bound_matches(source, fresh):
            raise ValueError("Source candidate changed before dispatch")
        owner = action["owner_lease_id"]
        if not isinstance(owner, str) or not owner.startswith("local_lease:") or not owner[12:]:
            raise ValueError("Use a labeled local owner lease, not an invented native turn ID")
        # Pin the exact envelope BEFORE the external send. Unknown outcome never returns to planned.
        job.update(
            status="dispatch_intent",
            attempt={"operation_id": action["operation_id"], "owner_lease_id": owner, "at": action["at"]},
        )
        job["attempt"]["native_call"] = envelope(state, job)
        return
    if job["attempt"] is None or action.get("owner_lease_id") != job["attempt"]["owner_lease_id"]:
        raise ValueError("Handoff belongs to another owner or has no dispatch intent")
    if kind == "acknowledge":
        if job["status"] not in {"dispatch_intent", "running"}:
            raise ValueError("Only an outstanding native send can be acknowledged")
        response = load(checked_ref(action["native_response"]))
        if not isinstance(response.get("native_task_name"), str) or not response["native_task_name"]:
            raise ValueError("Retain the actual native task name from the tool response")
        if job["native_response"] and job["native_response"] != action["native_response"]:
            raise ValueError("Another native worker is already bound to this intention")
        job.update(status="running", native_response=action["native_response"])
    elif kind == "refresh_analysis_approval":
        from scripts.source_update_handoff_review import refresh

        refresh(state, job, action, ROOT)
    elif kind == "finish":
        if job["status"] != "running":
            raise ValueError("A real acknowledged worker must complete this handoff")
        result = load(checked_ref(action["receipt"]))
        source = state["sources"][job["source_id"]]
        if (result.get("job_id"), result.get("data_version"), result.get("entity"), result.get("period")) != (
            job["job_id"],
            source["data_version"],
            job["entity"],
            job["period"],
        ):
            raise ValueError("Worker receipt does not bind the exact job/data/entity/period")
        job.setdefault("receipt_history", []).append(action["receipt"])
        if result.get("status") == "blocked":
            if not result.get("reason"):
                raise ValueError("Retain the concrete blocking control")
            job.update(status="blocked", result=action["receipt"])
            return
        if result.get("status") in {"no_visual_change", "no_material_analysis_change"}:
            from scripts.source_update_handoff_nochange import verify

            verify(job, source, result, expected_binding(source), ROOT)
            job.update(
                status="no_change" if is_current(state, job) else "superseded", result=action["receipt"]
            )
            return
        if job["stage"] == "analysis":
            if result.get("status") != "analysis_approved":
                raise ValueError("Analysis must pass the canonical lifecycle before dashboard handoff")
            verify_analysis(job, source, result)
        else:
            if result.get("status") != "site_built_verified":
                raise ValueError("Dashboard completion is a verified build, never an inferred deployment")
            verify_dashboard(result)
            verify_release_binding(job, source)
            if job["dependency"]:
                parent = state["jobs"][job["dependency"]]
                approved = verify_analysis(parent, source, load(checked_ref(parent["result"])))
                manifest = load(checked_ref(result["manifest"]))
                if not any(
                    entry.get("entity_key", "AEROMEXICO") == job["entity"]
                    and all(
                        entry.get(key) == approved[key]
                        for key in (
                            "period_id",
                            "version",
                            "content_hash",
                            "approval_event",
                            "audit_hash",
                        )
                    )
                    for entry in manifest["analysis_manifest"]
                ):
                    raise ValueError("Generated site does not contain the exact currently approved analysis")
        job.update(status="completed" if is_current(state, job) else "superseded", result=action["receipt"])
        if job["stage"] == "analysis" and job["status"] == "completed":
            enqueue(state, "dashboard", job["source_id"], job["entity"], job["job_id"], "editorial")
    elif kind == "reconcile_not_sent":
        if job["status"] != "dispatch_intent" or job["native_response"]:
            raise ValueError("A known worker must be followed, not resent")
        checked_ref(action["positive_nonexecution_evidence"])
        # This is an operator assertion backed by retained evidence, not automatic proof of absence.
        job.update(status="blocked", reconciliation=action["positive_nonexecution_evidence"])
    elif kind == "continue_existing_worker":
        if job["status"] != "blocked" or job["native_response"] is None or not is_current(state, job):
            raise ValueError("Continue only the acknowledged blocked worker; never create a duplicate")
        checked_ref(action["reconciliation"])
        job.update(status="running", reconciliation=action["reconciliation"])
    elif kind == "served":
        if job["stage"] != "dashboard" or job["status"] != "completed":
            raise ValueError("Served QA follows this completed dashboard build, never an analysis receipt")
        source = state["sources"][job["source_id"]]
        verify_release_binding(job, source)
        if job["dependency"]:
            parent = state["jobs"][job["dependency"]]
            verify_analysis(parent, source, load(checked_ref(parent["result"])))
        job["served_verification"] = {
            **verify_served(load(checked_ref(job["result"])), action["paths"]),
            "is_current_source": is_current(state, job),
        }
        job["status"] = "served_verified"
    else:
        raise ValueError("Unknown handoff transition")


def run(workspace: Path, *, action: dict | None = None) -> dict:
    workspace = safe_workspace(workspace)
    path = workspace / "state.json"
    if action is not None:
        with writer(workspace):
            state = (
                load(path)
                if path.exists()
                else {
                    "version": 1,
                    "workspace": str(workspace),
                    "sources": {},
                    "heads": {},
                    "jobs": {},
                    "operations": {},
                }
            )
            if state["workspace"] != str(workspace):
                raise ValueError("Do not operate a copied handoff ledger")
            operation_id = action["operation_id"]
            if not isinstance(operation_id, str) or not operation_id:
                raise ValueError("An explicit stable operation ID is required")
            previous = state["operations"].get(operation_id)
            if previous is not None:
                if previous != digest(action):
                    raise ValueError("Operation ID reused with different contents")
            else:
                at = local_time(action["at"])
                if at > local_time(datetime.now(UTC).isoformat()):
                    raise ValueError("Cannot record a future operation")
                if state.get("last_recorded_at") and at < local_time(state["last_recorded_at"]):
                    raise ValueError("Cannot reorder prior handoff operations")
                transition(state, action, workspace)
                state["operations"][operation_id] = digest(action)
                state["last_recorded_at"] = action["at"]
                persist(workspace, state)
    else:
        state = load(path)
    if state["workspace"] != str(workspace):
        raise ValueError("Do not operate a copied handoff ledger")
    return {
        "state": state,
        "ready_jobs": [
            envelope(state, job)
            for job in state["jobs"].values()
            if job["status"] == "planned" and is_current(state, job)
        ],
        "unreconciled_jobs": [
            job["job_id"] for job in state["jobs"].values() if job["status"] in {"dispatch_intent", "running"}
        ],
        "native_sends": 0,
        "publication_requests": 0,
        "schedule_changes": 0,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", required=True, type=Path)
    parser.add_argument("--record", type=Path)
    args = parser.parse_args(argv)
    try:
        result = run(args.workspace, action=load(args.record) if args.record else None)
        print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
        return 0
    except (KeyError, ValueError, OSError, TypeError, ImportError) as exc:
        print(json.dumps({"status": "blocked", "reason": str(exc), "native_sends": 0}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
