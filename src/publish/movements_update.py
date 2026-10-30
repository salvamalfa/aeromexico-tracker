"""Prepare and atomically publish only the reviewed Aerocivil movement correction."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path

from src.config import PATHS

from . import editorial as transport
from . import manifest as manifests
from .approval_cohorts import verify_approval_cohorts
from .issuer_authority import input_snapshot
from .issuer_update import _write_pins
from .records import PublicationRefused


def _file(path, repo):
    path = Path(path)
    path = path if path.is_absolute() else repo / path
    if (
        ".." in path.parts
        or not path.is_relative_to(repo)
        or any(p.is_symlink() for p in [path, *path.parents])
        or not path.is_file()
    ):
        raise ValueError("Movement private input is missing, outside the checkout or a symlink")
    return path


def _ref(ref, repo):
    if set(ref) != {"path", "sha256"} or not re.fullmatch("[a-f0-9]{64}", ref["sha256"]):
        raise ValueError("Movement input requires its exact physical SHA-256")
    path = _file(ref["path"], repo)
    if hashlib.sha256(path.read_bytes()).hexdigest() != ref["sha256"]:
        raise ValueError("Movement private input differs from its pinned SHA-256")
    return path


def _request(path, repo):
    path = _file(path, repo)
    request = json.loads(path.read_bytes())
    if (
        set(request) != {"schema_version", "source_profile", "record_paths", "authorization"}
        or request["schema_version"] != "aerocivil_movements_request_v1"
    ):
        raise ValueError("Unsupported movement publication request")
    profile = _ref(request["source_profile"], repo)
    records = [_file(p, repo) for p in request["record_paths"]]
    if len(records) != 7 or len(set(records)) != 7:
        raise ValueError("Select all seven distinct, already-published financial records")
    return request, profile, records


def _project(profile, baseline):
    from .movements_history import source_projection
    from .movements_scope import TARGETS

    result = source_projection(json.loads(profile.read_bytes()), baseline)
    required = {"source_binding", "source_evidence", "projection_rows", "network_outputs", "input_files"}
    if set(result) != required or set(result["network_outputs"]) != set(TARGETS):
        raise ValueError(
            "Movement source replay must provide its exact reviewed projection and input closure"
        )
    if not result["input_files"] or any(
        type(raw) is not bytes or not raw for raw in result["network_outputs"].values()
    ):
        raise ValueError("Movement replay has no physical evidence or encoded output")
    return result


def _pins(outputs):
    from .movements_scope import sha

    return [{"path": name, "sha256": sha(raw), "bytes": len(raw)} for name, raw in sorted(outputs.items())]


def _scope(spec):
    return {
        k: spec[k]
        for k in (
            "product",
            "period_id",
            "stage",
            "source_binding",
            "baseline_commit",
            "network_files",
            "producer_code_version",
        )
    }


def _authority(request, spec, repo):
    from .movements_scope import sha

    if request["authorization"] is None:
        raise ValueError("Movement publication requires the owner's retained, exact-scope authorization")
    path = _ref(request["authorization"], repo)
    digest = sha(path.read_bytes())
    expected = repo / "analysis_runs/dashboard_updates/authorizations" / (digest + ".json")
    if path != expected or digest != spec["authorization_sha256"]:
        raise ValueError("Retain movement authorization under its canonical private hash filename")
    value = json.loads(path.read_bytes())
    if (
        set(value) != {"schema_version", "status", "scope", "owner_consent"}
        or value["schema_version"] != "aerocivil_movements_authorization_v1"
        or value["status"] != "authorized"
        or value["scope"] != _scope(spec)
        or set(value["owner_consent"]) != {"source_reference", "instruction", "received_at"}
        or any(
            not isinstance(value["owner_consent"][k], str) or not value["owner_consent"][k].strip()
            for k in ("source_reference", "instruction", "received_at")
        )
    ):
        raise ValueError("Movement authorization is revoked, incomplete or names a different release")
    if datetime.fromisoformat(value["owner_consent"]["received_at"].replace("Z", "+00:00")).tzinfo is None:
        raise ValueError("Movement authority receipt must retain its actual timestamp and timezone")
    return path


def _snapshot(request_path, request, profile, records, projection, spec, repo):
    from .movements_scope import sha

    files = {_file(request_path, repo), profile}
    files.update(_file(p, repo) for p in projection["input_files"])
    if request["authorization"] is not None:
        files.add(_ref(request["authorization"], repo))
    financial = input_snapshot(records, {}, repo=repo)
    for path in files:
        financial[str(path.relative_to(repo))] = {
            "sha256": sha(path.read_bytes()),
            "library_identity": {
                key: sha(os.getxattr(path, key))
                for key in getattr(os, "listxattr", lambda _: ())(path)
                if key.startswith("user.library-")
            },
        }
    return financial


def _export(baseline, projection):
    from . import gate

    web = gate.WEB_DATA_V1
    if web.exists():
        shutil.rmtree(web)
    shutil.copytree(baseline / "data/v1", web)
    for name, raw in projection["network_outputs"].items():
        target = web / Path(name).relative_to("data/v1")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)
    return gate.build_web()


def inspect_movements(request_path):
    """Replay source/cohorts and build pins; never write authority, an anchor or site/."""
    from src.analysis_agent.entity_adapter import code_version

    from . import gate
    from .movements_scope import sha, verify_historical_baseline

    repo, baseline = PATHS.root, PATHS.root / "site"
    manifests.refuse_if_build_inputs_dirty()
    head = manifests.current_commit(repo)
    request, profile, records = _request(request_path, repo)
    commit = gate._trusted_site_commit(repo)
    gate.require_trusted_site_baseline(baseline, trusted_commit=commit)
    spec = {
        "schema_version": "aerocivil_movements_release_v1",
        "product": "aerocivil",
        "period_id": "2026Q3",
        "stage": "movements",
        "baseline_commit": commit,
        "baseline_manifest_sha256": sha((baseline / manifests.MANIFEST_NAME).read_bytes()),
        "producer_code_version": code_version(),
        "flights_contract_sha256": sha((repo / "contracts/web/flights.schema.json").read_bytes()),
        "authorization_sha256": request["authorization"]["sha256"] if request["authorization"] else None,
    }
    old = verify_historical_baseline(repo, spec, baseline)
    if len(old["analysis_manifest"]) != 7:
        raise ValueError("Movement baseline must include all seven released financial theses")
    with gate.flow.writer(gate.flow.ROOT):
        projection = _project(profile, baseline)
        spec.update({k: projection[k] for k in ("source_binding", "source_evidence", "projection_rows")})
        spec["network_files"] = _pins(projection["network_outputs"])
        snapshot = _snapshot(request_path, request, profile, records, projection, spec, repo)
        cohorts = verify_approval_cohorts(records, repo, commit, old, gate.flow.ROOT)
    dist = _export(baseline, projection)
    spec["frontend_files"] = transport.frontend_entries(dist)
    with gate.flow.writer(gate.flow.ROOT):
        if (
            _project(profile, baseline) != projection
            or verify_approval_cohorts(records, repo, commit, old, gate.flow.ROOT) != cohorts
        ):
            raise ValueError("Movement source or financial approvals changed while preparing pins")
        if _snapshot(request_path, request, profile, records, projection, spec, repo) != snapshot:
            raise ValueError("Movement physical inputs changed while preparing pins")
        gate.require_trusted_site_baseline(baseline, trusted_commit=commit)
        manifests.refuse_if_build_inputs_dirty()
        if manifests.current_commit(repo) != head or code_version() != spec["producer_code_version"]:
            raise ValueError("Movement producer changed while preparing pins")
    return {
        "status": "movement_pins_inspected_not_published",
        "anchor": spec,
        "authority_scope": _scope(spec),
    }


def prepare_movements(request_path):
    from .movements_scope import ANCHOR

    inspected = inspect_movements(request_path)
    request, _, _ = _request(request_path, PATHS.root)
    _authority(request, inspected["anchor"], PATHS.root)
    _write_pins([(ANCHOR, inspected["anchor"])])
    return {**inspected, "status": "movement_pins_prepared_not_published"}


def publish_movements(request_path, out_dir=PATHS.root / "site"):
    from src.analysis_agent.entity_adapter import code_version

    from . import gate
    from .movements_scope import (
        ANCHOR,
        PROOF,
        anchor,
        encoded,
        preserved_files,
        sha,
        verify_historical_baseline,
    )
    from .verify import _verify_site

    repo, baseline = PATHS.root, PATHS.root / "site"
    if Path(out_dir).resolve() != baseline.resolve():
        raise ValueError("Movement publication targets only this checkout's tracked site/")
    manifests.refuse_if_build_inputs_dirty()
    head, spec = manifests.current_commit(repo), anchor(repo)
    request, profile, records = _request(request_path, repo)
    if code_version() != spec["producer_code_version"]:
        raise ValueError("Movement runtime differs from its reviewed producer")
    if gate._trusted_site_commit(repo) != spec["baseline_commit"]:
        raise ValueError("Movement baseline is not current origin/master")
    gate.require_trusted_site_baseline(baseline, trusted_commit=spec["baseline_commit"])
    old = verify_historical_baseline(repo, spec, baseline)
    witness = transport.witness_remote(repo, spec)

    def verified():
        _authority(request, spec, repo)
        projection = _project(profile, baseline)
        if any(projection[k] != spec[k] for k in ("source_binding", "source_evidence", "projection_rows")):
            raise ValueError("Movement source replay differs from its reviewed source binding")
        if _pins(projection["network_outputs"]) != spec["network_files"]:
            raise ValueError("Movement projection differs from its reviewed output pins")
        cohorts = verify_approval_cohorts(records, repo, spec["baseline_commit"], old, gate.flow.ROOT)
        return projection, cohorts

    with gate.flow.writer(gate.flow.ROOT):
        first = verified()
        snapshot = _snapshot(request_path, request, profile, records, first[0], spec, repo)
    dist = _export(baseline, first[0])
    if transport.frontend_entries(dist) != spec["frontend_files"]:
        raise ValueError("Movement frontend build differs from its reviewed pins")
    with tempfile.TemporaryDirectory(prefix="movements-site-") as temporary:
        prepared = Path(temporary) / "site"
        shutil.copytree(baseline, prepared)
        for pin in spec["frontend_files"]:
            target = prepared / pin["path"]
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes((dist / pin["path"]).read_bytes())
        for name, raw in first[0]["network_outputs"].items():
            (prepared / name).write_bytes(raw)
        (prepared / manifests.MANIFEST_NAME).unlink()

        def proof(value):
            (prepared / PROOF).write_bytes(
                encoded(
                    {
                        "schema_version": "aerocivil_movements_publication_v1",
                        "anchor_sha256": sha((repo / ANCHOR).read_bytes()),
                        "remote_witness": value,
                    }
                )
            )

        proof(witness)

        def validate(candidate):
            problems = _verify_site(
                candidate, preserved_approval_files=preserved_files(candidate, repo, spec)
            )
            if problems:
                raise ValueError(f"Movement candidate rejected: {problems[:3]}")
            manifests.refuse_if_build_inputs_dirty()
            if anchor(repo) != spec or manifests.current_commit(repo) != head:
                raise ValueError("Movement release or build code changed before the final swap")
            if code_version() != spec["producer_code_version"]:
                raise ValueError("Movement runtime changed before the final swap")
            remote = transport._git(repo, "ls-remote", "origin", "refs/heads/master").decode().split()[0]
            if remote != spec["baseline_commit"]:
                raise ValueError("Remote movement baseline moved before the final swap")
            if _snapshot(request_path, request, profile, records, first[0], spec, repo) != snapshot:
                raise ValueError("Movement source, authority or approvals changed before the final swap")

        with gate.flow.writer(gate.flow.ROOT):
            gate.require_trusted_site_baseline(baseline, trusted_commit=spec["baseline_commit"])
            if verified() != first:
                raise ValueError("Movement source or approvals changed during publication")
            if _snapshot(request_path, request, profile, records, first[0], spec, repo) != snapshot:
                raise ValueError("Movement private inputs changed during the final replay")
            proof(transport.witness_remote(repo, spec))
            contracts = {**old["contracts"], "flights.schema.json": spec["flights_contract_sha256"]}
            manifest = gate.assemble_site(
                prepared,
                old["analysis_manifest"],
                Path(out_dir),
                contracts=contracts,
                validate_candidate=validate,
            )
    return {
        "manifest": manifest,
        "receipt": gate.write_receipt(manifest, first[1]["authorized"], Path(out_dir)),
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--inspect", type=Path)
    mode.add_argument("--prepare", type=Path)
    mode.add_argument("--request", type=Path)
    parser.add_argument("--out", type=Path, default=PATHS.root / "site")
    args = parser.parse_args(argv)
    try:
        if args.inspect:
            result = inspect_movements(args.inspect)
        elif args.prepare:
            result = prepare_movements(args.prepare)
        else:
            result = publish_movements(args.request, args.out)
            result = {"site_built_verified": True, "manifest_sha256": result["receipt"]["manifest_sha256"]}
        print(json.dumps(result, ensure_ascii=False))
        return 0
    except (
        ValueError,
        OSError,
        KeyError,
        TypeError,
        subprocess.SubprocessError,
        PublicationRefused,
    ) as error:
        print(f"Movement publication refused: {error}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
