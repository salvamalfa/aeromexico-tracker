"""Inspect, pin and publish an explicitly authorized original-source Q3 release.

The three superseded Q3 records remain in the private ledger and Git history.
Their source replay is explicitly unavailable and they are never inputs to the
new text/data. Q2 retains full original verifier/source/approval reproduction.
"""

from __future__ import annotations

import argparse
import json
import shutil
import tempfile
from datetime import UTC, datetime
from pathlib import Path

from src.analysis_agent import lifecycle as flow
from src.analysis_agent.quarterly_story import PROFILE, code_version
from src.config import PATHS

from . import editorial as transport
from . import gate
from . import manifest as manifests
from .approval_cohorts import approval_plan
from .frozen_data import verify_baseline_approvals
from .quarterly_story_data import encoded
from .quarterly_story_data import outputs as data_outputs
from .quarterly_story_scope import ANCHOR, ENTITIES, PROOF, SCHEMA, analysis_slots, anchor, preserved_files
from .records import _analysis_manifest_entry, load_records
from .source_data_scope import pins, sha
from .source_data_update import file_ref, physical_path
from .story_historical_pins import verify_historical_baseline


def request_inputs(path):
    path = physical_path(path, PATHS.root)
    value = json.loads(path.read_bytes())
    if (
        set(value) != {"schema_version", "record_paths", "sources", "authorization"}
        or value["schema_version"] != "quarterly_story_request_v1"
    ):
        raise ValueError("Unknown quarterly story request")
    paths = [physical_path(p, PATHS.root) for p in value["record_paths"]]
    records = load_records(paths)
    if len(set(paths)) != 4 or {r["draft"].get("entity_key") for r in records} != ENTITIES:
        raise ValueError("Select exactly four distinct new Q3 story records")
    packages = None
    for record in records:
        if record["draft"].get("source_profile") != PROFILE:
            raise ValueError("New Q3 release requires its reviewed source-replayed story profile")
        flow.require_current_presentation(record)
        package, _, _ = flow.verified_inputs(record)
        if packages is not None and packages != package["source_packages"]:
            raise ValueError("Four stories must share the exact reviewed source versions")
        packages = package["source_packages"]
    if packages["VOLARIS"].get("source_profile") != "volaris_original_quarter_v1":
        raise ValueError("New replacement must use the four original SEC HTTP documents")
    return value, paths, records, packages


def _old_record(entry):
    path = PATHS.root / "analysis_runs/drafts"
    if "entity_key" in entry:
        path /= entry["entity_key"]
    path = path / entry["period_id"] / (entry["version"] + ".json")
    return path, json.loads(path.read_bytes())


def historical_approvals(spec, old):
    groups, payloads = approval_plan(PATHS.root, spec["baseline_commit"], old)
    retained, superseded = [], []
    for group in groups:
        entries = group["analysis_manifest"]
        if all(e["period_id"] == "2026Q2" for e in entries):
            paths = [_old_record(e)[0] for e in entries]
            replayed = verify_baseline_approvals(
                paths, group["implementation_commit"], flow.ROOT, include_public_payloads=True
            )
            if [_analysis_manifest_entry(a) for a in replayed["authorized"]] != entries:
                raise ValueError("Retained Q2 approvals changed or were revoked")
            for e, payload in zip(entries, replayed["payloads"]):
                if payload != payloads["data/v1/" + manifests.analysis_relative_path(e).as_posix()]:
                    raise ValueError("Retained Q2 source replay differs from its exact public bytes")
            retained.extend(entries)
        elif all(
            e["period_id"] == "2026Q3" and manifests.analysis_identity(e)[0] != "INDUSTRY" for e in entries
        ):
            for entry in entries:
                _, record = _old_record(entry)
                state = flow.state(record)
                if (
                    state["state"] not in {"approved", "published"}
                    or record["content_hash"] != entry["content_hash"]
                    or record["draft"]["evidence_fingerprint"] != entry["evidence_fingerprint"]
                    or state["approval"]["event_hash"] != entry["approval_event"]
                    or state["audit"]["audit_hash"] != entry["audit_hash"]
                ):
                    raise ValueError("Superseded Q3 ledger history changed, missing or revoked")
                superseded.append(entry)
        else:
            raise ValueError("Historical source policy cannot exempt another quarter or entity")
    analysis_slots(retained, ENTITIES, "2026Q2")
    analysis_slots(superseded, ENTITIES - {"INDUSTRY"}, "2026Q3")
    return retained, superseded


def inspect(path):
    manifests.refuse_if_build_inputs_dirty()
    request, paths, records, packages = request_inputs(path)
    baseline = PATHS.root / "site"
    commit = gate._trusted_site_commit(PATHS.root)
    gate.require_trusted_site_baseline(baseline, trusted_commit=commit)
    raw = (baseline / manifests.MANIFEST_NAME).read_bytes()
    spec = dict(baseline_commit=commit, baseline_manifest_sha256=sha(raw))
    old = verify_historical_baseline(PATHS.root, spec, baseline)
    with flow.writer(flow.ROOT):
        retained, superseded = historical_approvals(spec, old)
        outputs = data_outputs(request["sources"], baseline, packages)
    scope = dict(
        schema_version="quarterly_story_authority_scope_v1",
        **spec,
        producer_code_version=code_version(),
        records=[
            dict(
                entity_key=r["draft"]["entity_key"],
                period_id=r["draft"]["period_id"],
                version=r["version"],
                content_hash=r["content_hash"],
                evidence_fingerprint=r["draft"]["evidence_fingerprint"],
            )
            for r in sorted(records, key=lambda r: r["draft"]["entity_key"])
        ],
        source_packages={
            e: dict(package_id=p["package_id"], evidence_fingerprint=p["evidence_fingerprint"])
            for e, p in packages.items()
        },
        data_files=pins(outputs),
        retained_analysis_manifest=retained,
        superseded_analysis_manifest=superseded,
        historical_source_status="superseded_Q3_source_not_replayed_not_consumed",
    )
    return scope, outputs, request, paths, records


def authority(request, scope):
    if request["authorization"] is None:
        raise ValueError("Original-source replacement requires the owner's new exact-scope decision")
    path = file_ref(request["authorization"], PATHS.root)
    raw = path.read_bytes()
    if path != PATHS.root / "analysis_runs/dashboard_updates/authorizations" / (sha(raw) + ".json"):
        raise ValueError("Retain exact replacement authority under its canonical hash path")
    value = json.loads(raw)
    if (
        set(value) != {"schema_version", "state", "scope", "source_audit", "owner_consent"}
        or value["schema_version"] != "quarterly_story_authorization_v1"
        or value["state"] != "authorized"
        or value["scope"] != scope
    ):
        raise ValueError("Replacement authority revoked or bound to another source, text, code or data")
    consent = value["owner_consent"]
    if set(consent) != {"source_reference", "instruction", "received_at"} or any(
        not isinstance(v, str) or not v.strip() for v in consent.values()
    ):
        raise ValueError("Replacement owner consent must retain the actual message and provenance")
    at = datetime.fromisoformat(consent["received_at"].replace("Z", "+00:00"))
    if at.tzinfo is None or at > datetime.now(UTC):
        raise ValueError("Replacement authorization needs its real zoned timestamp")
    audit_path = file_ref(value["source_audit"], PATHS.root)
    audit = json.loads(audit_path.read_bytes())
    if (
        audit_path
        != PATHS.root / "analysis_runs/dashboard_updates/audits" / (sha(audit_path.read_bytes()) + ".json")
        or audit.get("schema_version") != "quarterly_story_source_audit_v1"
        or audit.get("status") != "passed"
        or audit.get("scope") != scope
        or audit.get("unresolved_findings") != []
        or not audit.get("reviewer_reference")
    ):
        raise ValueError("Replacement needs an independent audit of the exact inspected source/data scope")
    return sha(raw), sha(audit_path.read_bytes())


def prepare(path):
    scope, outputs, request, paths, records = inspect(path)
    authority_sha, audit_sha = authority(request, scope)
    entries = gate.verify_records(records)
    for record, authorized, package, calculations in entries:
        payload = gate._analysis_payload(record, authorized, package, calculations)
        outputs["data/v1/" + manifests.analysis_relative_path(payload).as_posix()] = encoded(payload)
    dist = _build(outputs)
    spec = dict(
        schema_version=SCHEMA,
        baseline_commit=scope["baseline_commit"],
        baseline_manifest_sha256=scope["baseline_manifest_sha256"],
        producer_code_version=scope["producer_code_version"],
        scope=scope,
        analysis_manifest=[_analysis_manifest_entry(e[1]) for e in entries],
        retained_analysis_manifest=scope["retained_analysis_manifest"],
        superseded_analysis_manifest=scope["superseded_analysis_manifest"],
        data_files=pins(outputs),
        frontend_files=transport.frontend_entries(dist),
        contracts=manifests.contract_hashes(),
        authorization_sha256=authority_sha,
        independent_audit_sha256=audit_sha,
    )
    (PATHS.root / ANCHOR).write_bytes(encoded(spec))
    return spec


def _build(outputs):
    if gate.WEB_DATA_V1.exists():
        shutil.rmtree(gate.WEB_DATA_V1)
    shutil.copytree(PATHS.root / "site/data/v1", gate.WEB_DATA_V1)
    # Remove every superseded Q3 source document before exposing the new set.
    (gate.WEB_DATA_V1 / "analysis/2026Q3.json").unlink(missing_ok=True)
    for name, raw in outputs.items():
        target = gate.WEB_DATA_V1 / Path(name).relative_to("data/v1")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)
    return gate.build_web()


def publish(path, out):
    if Path(out).resolve() != (PATHS.root / "site").resolve():
        raise ValueError("Story release targets only tracked site/")
    spec = anchor()
    scope, outputs, request, paths, records = inspect(path)
    if scope != spec["scope"] or authority(request, scope) != (
        spec["authorization_sha256"],
        spec["independent_audit_sha256"],
    ):
        raise ValueError("Committed release differs from its current exact authority")
    first = gate.verify_records(records)
    for record, authorized, package, calculations in first:
        payload = gate._analysis_payload(record, authorized, package, calculations)
        outputs["data/v1/" + manifests.analysis_relative_path(payload).as_posix()] = encoded(payload)
    if pins(outputs) != spec["data_files"]:
        raise ValueError("Source or approved story changed after release preparation")
    dist = _build(outputs)
    if transport.frontend_entries(dist) != spec["frontend_files"]:
        raise ValueError("Story frontend differs from committed release")
    witness = transport.witness_remote(PATHS.root, spec)
    with tempfile.TemporaryDirectory(prefix="quarterly-story-site-") as temporary:
        prepared = Path(temporary) / "site"
        shutil.copytree(PATHS.root / "site", prepared)
        (prepared / "data/v1/analysis/2026Q3.json").unlink(missing_ok=True)
        for name, raw in outputs.items():
            (prepared / name).parent.mkdir(parents=True, exist_ok=True)
            (prepared / name).write_bytes(raw)
        for pin in spec["frontend_files"]:
            (prepared / pin["path"]).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(dist / pin["path"], prepared / pin["path"])
        (prepared / PROOF).write_bytes(
            encoded(
                dict(
                    schema_version="quarterly_story_publication_v1",
                    anchor_sha256=sha((PATHS.root / ANCHOR).read_bytes()),
                    remote_witness=witness,
                    historical_source_status="superseded_Q3_source_not_replayed_not_consumed",
                )
            )
        )
        # Replay mutable inputs under the ledger lock before the atomic swap.
        final_scope, final_outputs, final_request, _, _ = inspect(path)
        if final_scope != scope or final_outputs != {
            k: v for k, v in outputs.items() if not k.startswith("data/v1/analysis/")
        }:
            raise ValueError("Story source inputs changed during the build")
        with flow.writer(flow.ROOT):
            old, _ = transport.baseline(PATHS.root, spec)
            if historical_approvals(spec, old) != (
                scope["retained_analysis_manifest"],
                scope["superseded_analysis_manifest"],
            ):
                raise ValueError("Historical approval changed immediately before the atomic swap")
            if (
                data_outputs(final_request["sources"], PATHS.root / "site", first[0][2]["source_packages"])
                != final_outputs
            ):
                raise ValueError("Source data changed immediately before the atomic swap")
            if gate._verify_under_lock(records, flow.ROOT) != first or authority(final_request, scope) != (
                spec["authorization_sha256"],
                spec["independent_audit_sha256"],
            ):
                raise ValueError("Story approvals or data authority changed during the build")
            if anchor() != spec or code_version() != spec["producer_code_version"]:
                raise ValueError("Story release producer changed during the build")
            gate.require_trusted_site_baseline(PATHS.root / "site", trusted_commit=spec["baseline_commit"])
            if gate._trusted_site_commit(PATHS.root) != spec["baseline_commit"]:
                raise ValueError("Remote baseline changed before the atomic swap")

            def validate(candidate):
                from .verify import _verify_site

                problems = _verify_site(
                    candidate, preserved_approval_files=preserved_files(candidate, PATHS.root, spec)
                )
                if problems:
                    raise ValueError(f"Story publication candidate refused: {problems[:3]}")
                manifests.refuse_if_build_inputs_dirty()

            manifest = gate.assemble_site(
                prepared,
                spec["retained_analysis_manifest"] + spec["analysis_manifest"],
                out,
                contracts=spec["contracts"],
                validate_candidate=validate,
            )
    return dict(manifest=manifest, receipt=gate.write_receipt(manifest, [e[1] for e in first], out))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--inspect", type=Path)
    modes.add_argument("--prepare", type=Path)
    modes.add_argument("--request", type=Path)
    parser.add_argument("--out", type=Path, default=PATHS.root / "site")
    args = parser.parse_args()
    result = (
        inspect(args.inspect)[0]
        if args.inspect
        else prepare(args.prepare)
        if args.prepare
        else publish(args.request, args.out)
    )
    print(json.dumps(result, ensure_ascii=False))


def publish_from_gate(path, out):
    import subprocess

    try:
        return publish(path, out)
    except (ValueError, OSError, subprocess.CalledProcessError) as error:
        raise gate.PublicationRefused(f"Quarterly story publication rejected: {error}") from error


if __name__ == "__main__":
    main()
