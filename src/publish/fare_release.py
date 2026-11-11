"""Private fare-only gate; preserve and replay the current financial/source approvals."""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from pathlib import Path

from src.web_export.fare_averages import CONTRACT, export_fare_averages
from src.web_export.writer import write_json

from . import fare_scope
from . import manifest as manifests
from .records import PublicationRefused


def publish_from_gate(records, private_input, out):
    try:
        return publish_fares_only(records, private_input, out)
    except (ValueError, OSError, subprocess.CalledProcessError) as error:
        raise PublicationRefused(f"fare publication rejected: {error}") from error


def publish_fares_only(records: list[Path], private_input: Path, out: Path):
    from scripts.check_pages_publication import verify_site as verify_selected

    from . import gate
    from .presentation_release import _replay_release

    repo, ledger, out = gate.PATHS.root, gate.flow.ROOT, Path(out).resolve()
    manifests.refuse_if_build_inputs_dirty(root=repo)
    trusted = gate._trusted_site_commit(repo)
    gate.require_trusted_site_baseline(out, root=repo, trusted_commit=trusted)
    problems = verify_selected(out, repo)
    if problems:
        raise PublicationRefused(f"Existing strong release is invalid: {problems[:3]}")
    baseline = manifests.load_manifest(out)
    baseline_hash = fare_scope.sha((out / manifests.MANIFEST_NAME).read_bytes())
    policy = json.loads((repo / fare_scope.POLICY).read_bytes())
    if (
        policy.get("schema_version") != "fare_quotes_policy_v1"
        or policy.get("public_aggregates_authorized") is not True
    ):
        raise PublicationRefused("Public fare aggregate policy is missing")
    private_bytes = Path(private_input).read_bytes()
    private = json.loads(private_bytes)
    with gate.flow.writer(ledger):
        first = _replay_release(records, repo, trusted, baseline, ledger)
    # Work only in local generated output; the public site swap is last.
    gate.WEB_DATA_V1.mkdir(parents=True, exist_ok=True)
    for source in (out / "data/v1").rglob("*"):
        if source.is_file():
            target = gate.WEB_DATA_V1 / source.relative_to(out / "data/v1")
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
    exported = export_fare_averages(private, gate.WEB_DATA_V1)
    if not json.loads(exported.read_bytes())["groups"]:
        raise PublicationRefused("No verified observations can support a public fare average")
    aggregate_bytes = exported.read_bytes()
    proof = dict(
        schema_version=fare_scope.SCHEMA,
        baseline_commit=trusted,
        baseline_manifest_sha256=baseline_hash,
        aggregate_sha256=fare_scope.sha(aggregate_bytes),
        private_input_sha256=fare_scope.sha(private_bytes),
        policy_sha256=fare_scope.sha((repo / fare_scope.POLICY).read_bytes()),
        public_contract_sha256=fare_scope.sha((repo / "contracts/web" / CONTRACT).read_bytes()),
    )
    dist = gate.build_web(gate.WEB_DIR)
    if (dist / fare_scope.DATA).read_bytes() != aggregate_bytes:
        raise PublicationRefused("Frontend build changed public fare averages")
    with tempfile.TemporaryDirectory(prefix="fare-release-") as temporary:
        staged = Path(temporary) / "dist"
        shutil.copytree(out, staged)
        shutil.copyfile(dist / "index.html", staged / "index.html")
        for asset in (dist / "assets").rglob("*"):
            if asset.is_file():
                target = staged / asset.relative_to(dist)
                target.parent.mkdir(parents=True, exist_ok=True)
                if target.exists() and target.read_bytes() != asset.read_bytes():
                    raise PublicationRefused("Frontend reused an existing immutable asset name")
                shutil.copyfile(asset, target)
        (staged / fare_scope.DATA).write_bytes(aggregate_bytes)
        write_json(staged / fare_scope.PROOF, proof)
        contracts = {**baseline["contracts"], CONTRACT: proof["public_contract_sha256"]}

        def validate_candidate(candidate):
            errors = fare_scope.verify_fare_site(candidate, repo)
            if errors:
                raise ValueError(errors[:3])

        with gate.flow.writer(ledger):
            gate.require_trusted_site_baseline(out, root=repo, trusted_commit=trusted)
            if Path(private_input).read_bytes() != private_bytes:
                raise PublicationRefused(
                    "Private fare input changed during build; regenerate before publication"
                )
            current = _replay_release(records, repo, trusted, baseline, ledger)
            if current != first:
                raise PublicationRefused("Existing source/approval state changed during fare build")
            manifest = gate.assemble_site(
                staged,
                baseline["analysis_manifest"],
                out,
                contracts=contracts,
                validate_candidate=validate_candidate,
            )
    receipt = gate.write_receipt(manifest, first["afac"]["authorized"], out, root=ledger)
    return {"manifest": manifest, "receipt": receipt}
