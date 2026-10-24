"""Explicit, scoped financial publication over an already-published reading."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from src.config import PATHS
from src.analysis_agent.entity_adapter import code_version
from . import editorial as transport
from . import manifest as manifests
from .financial_scope import ANCHOR, EXECUTIVE, PROOF, anchor, encoded, sha, verify_financial, preserved_files
from .financial_sources import approved_projection, authorization, source_snapshot


def publish_financial(record_paths: list[Path], out_dir: Path):
    from . import gate

    repo = PATHS.root
    baseline_dir = repo / "site"
    out_dir = Path(out_dir).resolve()
    manifests.refuse_if_build_inputs_dirty()
    start_head = transport._git(repo, "rev-parse", "HEAD")
    spec = anchor(repo)
    if code_version() != spec["producer_code_version"]:
        raise ValueError("Financial build code differs from independent review")
    if gate._trusted_site_commit(repo) != spec["baseline_commit"]:
        raise ValueError("Financial baseline is not current origin/master")
    gate.require_trusted_site_baseline(baseline_dir, trusted_commit=spec["baseline_commit"])
    first_witness = transport.witness_remote(repo, spec)
    old, _ = transport.baseline(repo, spec)
    with gate.flow.writer(gate.flow.ROOT):
        executive = approved_projection(record_paths, spec, gate.flow.ROOT)
        snapshot = source_snapshot(record_paths, spec, gate.flow.ROOT)
    web = gate.WEB_DATA_V1
    if web.exists():
        shutil.rmtree(web)
    shutil.copytree(baseline_dir / "data/v1", web)
    (web / "executive.json").write_bytes(encoded(executive))
    dist = gate.build_web()
    if transport.frontend_entries(dist) != spec["frontend_files"]:
        raise ValueError("Financial frontend differs from reviewed pins")
    old_names = {row["path"] for row in old["files"]}
    kept = old_names | {row["path"] for row in spec["frontend_files"]} | {PROOF}
    for path in dist.rglob("*"):
        if path.is_file() and path.relative_to(dist).as_posix() not in kept:
            if path.parent != dist / "assets":
                raise ValueError("Financial build introduced an unrelated surface")
            path.unlink()
    for item in old["files"]:
        name = item["path"]
        if name in {"index.html", EXECUTIVE}:
            continue
        target = dist / name
        expected = (baseline_dir / name).read_bytes()
        if name.startswith("data/v1/") and (not target.is_file() or target.read_bytes() != expected):
            raise ValueError("Financial build changed unrelated data")
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(baseline_dir / name, target)
    if (dist / EXECUTIVE).read_bytes() != encoded(executive):
        raise ValueError("Financial build changed the reviewed projection")
    final_witness = transport.witness_remote(repo, spec)
    if final_witness["deployment_commit"] != first_witness["deployment_commit"]:
        raise ValueError("Financial baseline deployment changed during build")
    proof = {
        "schema_version": "financial_publication_v1",
        "anchor_sha256": sha((repo / ANCHOR).read_bytes()),
        "remote_witness": final_witness,
        "authorization_sha256": spec["authorization_sha256"],
    }
    (dist / PROOF).write_text(json.dumps(proof, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    def final_state():
        manifests.refuse_if_build_inputs_dirty()
        if transport._git(repo, "rev-parse", "HEAD") != start_head or anchor(repo) != spec:
            raise ValueError("Financial HEAD or reviewed anchor changed")
        if code_version() != spec["producer_code_version"]:
            raise ValueError("Financial producer changed")
        gate.require_trusted_site_baseline(baseline_dir, trusted_commit=spec["baseline_commit"])
        if (
            transport._git(repo, "ls-remote", "origin", "refs/heads/master").decode().split()[0]
            != spec["baseline_commit"]
        ):
            raise ValueError("Remote financial baseline changed")
        authorization(spec)
        if source_snapshot(record_paths, spec, gate.flow.ROOT) != snapshot:
            raise ValueError("Financial sources, review or approval changed")

    def validate(candidate):
        problems = verify_financial(candidate)
        if problems:
            raise ValueError(f"Financial candidate refused: {problems[:3]}")
        preserved_files(candidate, repo, spec)
        final_state()

    with gate.flow.writer(gate.flow.ROOT):
        final_state()
        current = approved_projection(record_paths, spec, gate.flow.ROOT)
        if current != executive:
            raise ValueError("Financial approved projection changed during build")
        final_state()
        manifest = gate.assemble_site(
            dist, old["analysis_manifest"], out_dir, contracts=old["contracts"], validate_candidate=validate
        )
    # This receipt records this local generation, never proof of a remote deploy.
    receipt = gate.write_receipt(manifest, [spec["analysis_entry"]], out_dir)
    return {"manifest": manifest, "receipt": receipt}
