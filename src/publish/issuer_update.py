"""Publish one approved issuer quarter independently over a verified live baseline."""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from pathlib import Path

from src.config import PATHS

from . import editorial as transport
from . import manifest as manifests
from .approval_cohorts import verify_approval_cohorts
from .issuer_projection import executive_projection, require_scope
from .issuer_scope import (
    ANCHOR,
    EXECUTIVE,
    PROOF,
    anchor,
    encoded,
    preserved_files,
    sha,
    verify_historical_baseline,
)


def prepare_issuer(record_path: Path):
    """Materialize only reproducible public pins from a currently approved record.

    No approval, source acquisition, commit, native handoff or publication occurs.
    The final producer and its skill must be frozen before the analysis approval.
    """
    from src.analysis_agent.entity_adapter import code_version

    from . import gate
    from .approval_cohorts import CONFIG, _cohorts, _optional_config

    repo, baseline = PATHS.root, PATHS.root / "site"
    commit = gate._trusted_site_commit(repo)
    gate.require_trusted_site_baseline(baseline, trusted_commit=commit)
    old = manifests.load_manifest(baseline)
    record = gate.load_records([record_path])[0]
    if record["draft"].get("source_profile") != "issuer_quarter_v1":
        raise ValueError("Issuer-quarter source profile required")
    with gate.flow.writer(gate.flow.ROOT):
        entry = gate._verify_under_lock([record], gate.flow.ROOT)[0]
        identity = gate._analysis_manifest_entry(entry[1])
        if identity in old["analysis_manifest"]:
            return {"status": "already_published", "analysis_entry": identity}
        if any(
            manifests.analysis_identity(e) == manifests.analysis_identity(identity)
            for e in old["analysis_manifest"]
        ):
            raise ValueError("Existing issuer edition requires an explicit revision reconciliation")
        executive = executive_projection(json.loads((baseline / EXECUTIVE).read_bytes()), entry[2])
        analysis_raw, executive_raw = encoded(gate._analysis_payload(*entry)), encoded(executive)
        spec = {
            "schema_version": "issuer_release_v1",
            "baseline_commit": commit,
            "baseline_manifest_sha256": sha((baseline / manifests.MANIFEST_NAME).read_bytes()),
            "entity_key": entry[2]["entity_key"],
            "period_id": entry[2]["period_id"],
            "analysis_entry": identity,
            "analysis_sha256": sha(analysis_raw),
            "analysis_bytes": len(analysis_raw),
            "executive_sha256": sha(executive_raw),
            "executive_bytes": len(executive_raw),
            "producer_code_version": code_version(),
        }
        cohort = {
            "implementation_commit": manifests.current_commit(repo),
            "analysis_manifest": [identity],
            "files": [
                {
                    "path": "data/v1/" + manifests.analysis_relative_path(identity).as_posix(),
                    "sha256": sha(analysis_raw),
                    "bytes": len(analysis_raw),
                }
            ],
        }
        config = {
            "schema_version": "analysis_approval_cohorts_v1",
            "cohorts": [*_cohorts(_optional_config(repo, commit)), cohort],
        }
        writes = []
        for name, value in ((ANCHOR, spec), (CONFIG, config)):
            target = repo / name
            if any(p.is_symlink() for p in [target, *target.parents]):
                raise ValueError("Issuer public pin cannot be a symlink")
            exists = (
                subprocess.run(
                    ["git", "cat-file", "-e", f"HEAD:{name}"],
                    cwd=repo,
                    capture_output=True,
                ).returncode
                == 0
            )
            committed = transport._git(repo, "show", f"HEAD:{name}") if exists else None
            actual = target.read_bytes() if target.exists() else None
            if actual != committed and (actual is None or json.loads(actual) != value):
                raise ValueError("Issuer pin has an unrelated local edit; reconcile its owner first")
            writes.append((target, value))
        for target, value in writes:
            gate.flow.atomic_json(target, value)
    return {"status": "pins_prepared_not_published", "anchor": spec, "cohort": cohort}


def publish_issuer(record_paths: list[Path], out_dir: Path):
    from src.analysis_agent.entity_adapter import code_version

    from . import gate
    from .verify import _verify_site

    repo, baseline = PATHS.root, PATHS.root / "site"
    out_dir = Path(out_dir).resolve()
    if out_dir != baseline.resolve():
        raise ValueError("Issuer publication targets only this checkout's tracked site/")
    manifests.refuse_if_build_inputs_dirty()
    start_head = manifests.current_commit(repo)
    spec = anchor(repo)
    if code_version() != spec["producer_code_version"]:
        raise ValueError("Issuer implementation differs from independent review")
    if gate._trusted_site_commit(repo) != spec["baseline_commit"]:
        raise ValueError("Issuer baseline is not current origin/master")
    gate.require_trusted_site_baseline(baseline, trusted_commit=spec["baseline_commit"])
    verify_historical_baseline(repo, spec, baseline)
    first_witness = transport.witness_remote(repo, spec)
    old, _ = transport.baseline(repo, spec)
    records = gate.load_records(record_paths)
    # Raw drafts do not carry the approval event. Resolve the exact slot, then
    # verify its complete current approval identity under the ledger lock.
    new = [
        r
        for r in records
        if (
            manifests.analysis_identity(r["draft"]) == (spec["entity_key"], spec["period_id"])
            and r["version"] == spec["analysis_entry"]["version"]
        )
    ]
    if len(new) != 1 or new[0]["draft"].get("source_profile") != "issuer_quarter_v1":
        raise ValueError("Exactly one current issuer-quarter record is required")
    name = "data/v1/" + manifests.analysis_relative_path(spec["analysis_entry"]).as_posix()
    if (baseline / name).exists():
        raise ValueError("Issuer quarter already published: reconcile its existing version before a revision")
    original_executive = json.loads((baseline / EXECUTIVE).read_bytes())

    def verified():
        current = gate._verify_under_lock(new, gate.flow.ROOT)[0]
        if gate._analysis_manifest_entry(current[1]) != spec["analysis_entry"]:
            raise ValueError("Issuer approval changed or names another version")
        analysis = gate._analysis_payload(*current)
        analysis_raw = encoded(analysis)
        if sha(analysis_raw) != spec["analysis_sha256"] or len(analysis_raw) != spec["analysis_bytes"]:
            raise ValueError("Issuer thesis differs from reviewed output")
        executive = executive_projection(original_executive, current[2])
        require_scope(original_executive, executive, spec["entity_key"], spec["period_id"])
        executive_raw = encoded(executive)
        if sha(executive_raw) != spec["executive_sha256"] or len(executive_raw) != spec["executive_bytes"]:
            raise ValueError("Issuer chart projection differs from reviewed output")
        pending = {
            "entry": spec["analysis_entry"],
            "bytes": analysis_raw,
            "file": {"path": name, "sha256": sha(analysis_raw), "bytes": len(analysis_raw)},
        }
        cohorts = verify_approval_cohorts(
            record_paths,
            repo,
            spec["baseline_commit"],
            old,
            gate.flow.ROOT,
            pending=pending,
        )
        return current, cohorts, analysis_raw, executive_raw

    with gate.flow.writer(gate.flow.ROOT):
        first = verified()
    web = gate.WEB_DATA_V1
    if web.exists():
        shutil.rmtree(web)
    shutil.copytree(baseline / "data/v1", web)
    target = web / manifests.analysis_relative_path(spec["analysis_entry"])
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(first[2])
    (web / "executive.json").write_bytes(first[3])
    dist = gate.build_web()
    if transport.frontend_entries(dist) != transport.frontend_entries(baseline):
        raise ValueError(
            "Issuer-only update requires unchanged dashboard frontend; review UI changes separately"
        )
    # Other applications and historical assets remain exact. Only the two
    # validated payloads plus this release's proof may change in this mode.
    with tempfile.TemporaryDirectory(prefix="issuer-site-") as temporary:
        prepared = Path(temporary) / "site"
        shutil.copytree(baseline, prepared)
        (prepared / name).parent.mkdir(parents=True, exist_ok=True)
        (prepared / name).write_bytes(first[2])
        (prepared / EXECUTIVE).write_bytes(first[3])
        (prepared / manifests.MANIFEST_NAME).unlink()
        (prepared / PROOF).write_bytes(
            encoded(
                {
                    "schema_version": "issuer_publication_v1",
                    "anchor_sha256": sha((repo / ANCHOR).read_bytes()),
                    "remote_witness": first_witness,
                }
            )
        )
        entries = sorted([*old["analysis_manifest"], spec["analysis_entry"]], key=manifests.analysis_sort_key)

        def validate(candidate):
            preserved = preserved_files(candidate, repo, spec)
            problems = _verify_site(candidate, preserved_approval_files=preserved)
            if problems:
                raise ValueError(f"Issuer candidate rejected: {problems[:3]}")

        with gate.flow.writer(gate.flow.ROOT):
            gate.require_trusted_site_baseline(baseline, trusted_commit=spec["baseline_commit"])
            if verified() != first or anchor(repo) != spec or manifests.current_commit(repo) != start_head:
                raise ValueError("Issuer source, approval, release or build code changed")
            # The live baseline check follows source replay, immediately before
            # the atomic swap. No fallback accepts an uncertain remote state.
            transport.witness_remote(repo, spec)
            if code_version() != spec["producer_code_version"]:
                raise ValueError("Issuer implementation changed during publication")
            manifest = gate.assemble_site(
                prepared,
                entries,
                out_dir,
                contracts=old["contracts"],
                validate_candidate=validate,
            )
    receipt = gate.write_receipt(manifest, first[1]["authorized"], out_dir)
    return {"manifest": manifest, "receipt": receipt}


def main(argv=None):
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prepare-record", type=Path, help="prepare public pins only; no publication")
    parser.add_argument("--record", type=Path, action="append", default=[])
    parser.add_argument("--out", type=Path, default=PATHS.root / "site")
    args = parser.parse_args(argv)
    try:
        if args.prepare_record:
            if args.record:
                raise ValueError("Pin preparation and publication are separate invocations")
            print(json.dumps(prepare_issuer(args.prepare_record), ensure_ascii=False))
            return 0
        if not args.record:
            raise ValueError("Publication requires exact baseline and new record paths")
        value = publish_issuer(args.record, args.out)
    except (ValueError, OSError, subprocess.SubprocessError) as error:
        print(f"Issuer publication refused: {error}")
        return 1
    print(json.dumps({"manifest_sha256": value["receipt"]["manifest_sha256"], "site_built_verified": True}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
