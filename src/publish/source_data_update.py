"""Inspect, pin and atomically publish one independently validated monthly source."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import tempfile
from datetime import UTC, datetime
from pathlib import Path

from src.config import PATHS

from . import editorial as transport
from . import manifest as manifests
from .approval_cohorts import verify_approval_cohorts
from .issuer_authority import input_snapshot
from .issuer_update import _write_pins
from .source_data_scope import (
    ANCHOR,
    PROOF,
    adapter,
    anchor,
    encoded,
    pins,
    preserved_files,
    scope,
    sha,
    verify_historical_baseline,
)


def physical_path(path, repo):
    path = Path(path)
    path = path if path.is_absolute() else repo / path
    if (
        not path.is_relative_to(repo)
        or ".." in path.parts
        or any(p.is_symlink() for p in [path, *path.parents])
        or not path.is_file()
    ):
        raise ValueError("Selective source input is missing, outside its checkout or a symlink")
    return path


def file_ref(value, repo):
    if set(value) != {"path", "sha256"}:
        raise ValueError("Selective source input requires its exact retained reference")
    path = physical_path(value["path"], repo)
    if sha(path.read_bytes()) != value["sha256"]:
        raise ValueError("Selective source input differs from its exact retained reference")
    return path


def request_inputs(path, repo):
    path = physical_path(path, repo)
    request = json.loads(path.read_bytes())
    if (
        set(request)
        != {"schema_version", "product", "period", "source_profile", "record_paths", "authorization"}
        or request["schema_version"] != "source_data_request_v1"
    ):
        raise ValueError("Unsupported selective source request")
    adapter(request["product"])
    profile = file_ref(request["source_profile"], repo)
    records = [physical_path(p, repo) for p in request["record_paths"]]
    if not records or len(set(records)) != len(records):
        raise ValueError("Select every distinct record from the released analysis manifest")
    return path, request, profile, records


def replay(request, profile, baseline, repo):
    module = adapter(request["product"])
    value = module.replay(json.loads(profile.read_bytes()), baseline)
    if set(value) != {"source_binding", "projection", "input_files"} or not value["input_files"]:
        raise ValueError("Source adapter did not supply a physical input closure")
    if (value["source_binding"]["product"], value["source_binding"]["period"]) != (
        request["product"],
        request["period"],
    ):
        raise ValueError("Source replay names another product or period")
    before = {name: (baseline / name).read_bytes() for name in module.TARGETS}
    outputs = module.public_outputs(before, value["projection"])
    if set(outputs) != set(module.TARGETS) or any(type(b) is not bytes or not b for b in outputs.values()):
        raise ValueError("Source adapter changed an undeclared surface")
    for raw_path in value["input_files"]:
        p = Path(raw_path)
        p = p if p.is_absolute() else repo / p
        file_ref({"path": str(p), "sha256": sha(p.read_bytes())}, repo)
    return value, outputs


def authority(request, spec, repo):
    if request["authorization"] is None:
        raise ValueError("Source exposure requires retained owner consent for this exact inspected scope")
    path = file_ref(request["authorization"], repo)
    digest = sha(path.read_bytes())
    if (
        path != repo / "analysis_runs/dashboard_updates/authorizations" / (digest + ".json")
        or digest != spec["authorization_sha256"]
    ):
        raise ValueError("Retain source exposure authorization under its canonical hash filename")
    value = json.loads(path.read_bytes())
    if (
        set(value) != {"schema_version", "status", "scope", "owner_consent"}
        or value["schema_version"] != "source_data_authorization_v1"
        or value["status"] != "authorized"
        or value["scope"] != scope(spec)
    ):
        raise ValueError("Source authorization is revoked or names another exact release")
    consent = value["owner_consent"]
    if set(consent) != {"source_reference", "instruction", "received_at"} or any(
        not isinstance(v, str) or not v.strip() for v in consent.values()
    ):
        raise ValueError("Source owner consent must retain its actual instruction and provenance")
    at = datetime.fromisoformat(consent["received_at"].replace("Z", "+00:00"))
    if at.tzinfo is None or at > datetime.now(UTC):
        raise ValueError("Source owner consent timestamp is missing its zone or is in the future")
    return path


def snapshot(path, request, profile, records, value, repo):
    result = input_snapshot(records, {}, repo=repo)
    files = [path, profile, *[Path(p) for p in value["input_files"]]]
    if request["authorization"] is not None:
        files.append(file_ref(request["authorization"], repo))
    for p in files:
        p = p if p.is_absolute() else repo / p
        import os

        result[str(p.relative_to(repo))] = {
            "sha256": sha(p.read_bytes()),
            "library_identity": {
                k: sha(os.getxattr(p, k)) for k in os.listxattr(p) if k.startswith("user.library-")
            },
        }
    return result


def export(baseline, outputs):
    from . import gate

    if gate.WEB_DATA_V1.exists():
        shutil.rmtree(gate.WEB_DATA_V1)
    shutil.copytree(baseline / "data/v1", gate.WEB_DATA_V1)
    for name, raw in outputs.items():
        target = gate.WEB_DATA_V1 / Path(name).relative_to("data/v1")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)
    return gate.build_web()


def inspect_source(path):
    from src.analysis_agent.entity_adapter import code_version

    from . import gate

    repo, baseline = PATHS.root, PATHS.root / "site"
    manifests.refuse_if_build_inputs_dirty()
    head = manifests.current_commit(repo)
    path, request, profile, records = request_inputs(path, repo)
    baseline_commit = gate._trusted_site_commit(repo)
    gate.require_trusted_site_baseline(baseline, trusted_commit=baseline_commit)
    spec = {
        "schema_version": "source_data_release_v1",
        "product": request["product"],
        "period_id": request["period"],
        "baseline_commit": baseline_commit,
        "baseline_manifest_sha256": sha((baseline / manifests.MANIFEST_NAME).read_bytes()),
        "producer_code_version": code_version(),
        "authorization_sha256": request["authorization"]["sha256"] if request["authorization"] else None,
        "contract_changes": {
            n: sha((repo / "contracts/web" / n).read_bytes()) for n in adapter(request["product"]).CONTRACTS
        },
    }
    old = verify_historical_baseline(repo, spec, baseline)
    if not old["analysis_manifest"]:
        raise ValueError("Source baseline must retain its complete released analysis manifest")
    with gate.flow.writer(gate.flow.ROOT):
        first = replay(request, profile, baseline, repo)
        spec.update(
            source_binding=first[0]["source_binding"],
            projection=first[0]["projection"],
            data_files=pins(first[1]),
        )
        initial = snapshot(path, request, profile, records, first[0], repo)
        cohorts = verify_approval_cohorts(records, repo, baseline_commit, old, gate.flow.ROOT)
    spec["frontend_files"] = transport.frontend_entries(export(baseline, first[1]))
    with gate.flow.writer(gate.flow.ROOT):
        if (
            replay(request, profile, baseline, repo) != first
            or snapshot(path, request, profile, records, first[0], repo) != initial
        ):
            raise ValueError("Source inputs changed while inspecting the release")
        if verify_approval_cohorts(records, repo, baseline_commit, old, gate.flow.ROOT) != cohorts:
            raise ValueError("Financial approvals changed while inspecting the source release")
        gate.require_trusted_site_baseline(baseline, trusted_commit=baseline_commit)
        manifests.refuse_if_build_inputs_dirty()
        if manifests.current_commit(repo) != head or code_version() != spec["producer_code_version"]:
            raise ValueError("Source producer changed while inspecting release pins")
    return {"status": "source_pins_inspected_not_published", "anchor": spec, "authority_scope": scope(spec)}


def prepare_source(path):
    result = inspect_source(path)
    _, request, _, _ = request_inputs(path, PATHS.root)
    authority(request, result["anchor"], PATHS.root)
    _write_pins([(ANCHOR, result["anchor"])])
    return {**result, "status": "source_pins_prepared_not_published"}


def publish_source(path, out):
    from src.analysis_agent.entity_adapter import code_version

    from . import gate
    from .verify import _verify_site

    repo, baseline = PATHS.root, PATHS.root / "site"
    if Path(out).resolve() != baseline.resolve():
        raise ValueError("Source publication targets only this checkout's tracked site/")
    manifests.refuse_if_build_inputs_dirty()
    head, spec = manifests.current_commit(repo), anchor(repo)
    path, request, profile, records = request_inputs(path, repo)
    if (request["product"], request["period"]) != (spec["product"], spec["period_id"]):
        raise ValueError("Source request differs from committed release")
    if (
        code_version() != spec["producer_code_version"]
        or gate._trusted_site_commit(repo) != spec["baseline_commit"]
    ):
        raise ValueError("Source producer or remote baseline moved")
    gate.require_trusted_site_baseline(baseline, trusted_commit=spec["baseline_commit"])
    old = verify_historical_baseline(repo, spec, baseline)

    def verify():
        authority(request, spec, repo)
        value, outputs = replay(request, profile, baseline, repo)
        if (
            value["source_binding"] != spec["source_binding"]
            or value["projection"] != spec["projection"]
            or pins(outputs) != spec["data_files"]
        ):
            raise ValueError("Source replay differs from exact authorized release")
        cohort = verify_approval_cohorts(records, repo, spec["baseline_commit"], old, gate.flow.ROOT)
        return value, outputs, cohort

    with gate.flow.writer(gate.flow.ROOT):
        first = verify()
        initial = snapshot(path, request, profile, records, first[0], repo)
    dist = export(baseline, first[1])
    if transport.frontend_entries(dist) != spec["frontend_files"]:
        raise ValueError("Source frontend differs from committed release pins")
    with tempfile.TemporaryDirectory(prefix="source-data-site-") as temporary:
        prepared = Path(temporary) / "site"
        shutil.copytree(baseline, prepared)
        for pin in spec["frontend_files"]:
            (prepared / pin["path"]).parent.mkdir(parents=True, exist_ok=True)
            (prepared / pin["path"]).write_bytes((dist / pin["path"]).read_bytes())
        for name, raw in first[1].items():
            (prepared / name).write_bytes(raw)
        (prepared / manifests.MANIFEST_NAME).unlink()

        def validate(candidate):
            problems = _verify_site(
                candidate, preserved_approval_files=preserved_files(candidate, repo, spec)
            )
            if problems:
                raise ValueError(f"Source candidate refused: {problems[:3]}")
            manifests.refuse_if_build_inputs_dirty()
            if (
                anchor(repo) != spec
                or manifests.current_commit(repo) != head
                or code_version() != spec["producer_code_version"]
            ):
                raise ValueError("Source release or producer changed before final swap")
            remote = transport._git(repo, "ls-remote", "origin", "refs/heads/master").decode().split()[0]
            if (
                remote != spec["baseline_commit"]
                or snapshot(path, request, profile, records, first[0], repo) != initial
            ):
                raise ValueError("Source baseline or physical evidence changed before final swap")

        with gate.flow.writer(gate.flow.ROOT):
            gate.require_trusted_site_baseline(baseline, trusted_commit=spec["baseline_commit"])
            if verify() != first or snapshot(path, request, profile, records, first[0], repo) != initial:
                raise ValueError("Source evidence or approvals changed during build")
            (prepared / PROOF).write_bytes(
                encoded(
                    {
                        "schema_version": "source_data_publication_v1",
                        "anchor_sha256": sha((repo / ANCHOR).read_bytes()),
                        "remote_witness": transport.witness_remote(repo, spec),
                    }
                )
            )
            manifest = gate.assemble_site(
                prepared,
                old["analysis_manifest"],
                Path(out),
                contracts={**old["contracts"], **spec["contract_changes"]},
                validate_candidate=validate,
            )
    return {"manifest": manifest, "receipt": gate.write_receipt(manifest, first[2]["authorized"], Path(out))}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    for name in ("inspect", "prepare", "request"):
        mode.add_argument("--" + name, type=Path)
    parser.add_argument("--out", type=Path, default=PATHS.root / "site")
    args = parser.parse_args(argv)
    try:
        result = (
            inspect_source(args.inspect)
            if args.inspect
            else prepare_source(args.prepare)
            if args.prepare
            else publish_source(args.request, args.out)
        )
        print(json.dumps(result, ensure_ascii=False))
        return 0
    except (ValueError, RuntimeError, OSError, KeyError, TypeError, subprocess.SubprocessError) as exc:
        print(f"Selective source publication refused: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
