"""Publish one approved issuer product independently over a verified live baseline."""

from __future__ import annotations

import argparse
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
from .records import PublicationRefused


def _write_pins(writes):
    from . import gate

    repo = PATHS.root
    prepared = []
    for name, value in writes:
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
        prepared.append((target, value))
    for target, value in prepared:
        gate.flow.atomic_json(target, value)


def _stable_cohort(repo, spec, cohort):
    """Re-preparing committed pins must not move the already-selected producer."""
    from .approval_cohorts import _cohorts, _optional_config

    exists = (
        subprocess.run(
            ["git", "cat-file", "-e", f"HEAD:{ANCHOR}"],
            cwd=repo,
            capture_output=True,
        ).returncode
        == 0
    )
    if exists and json.loads(transport._git(repo, "show", f"HEAD:{ANCHOR}")) == spec:
        matches = [
            c
            for c in _cohorts(_optional_config(repo, "HEAD"))
            if c["analysis_manifest"] == cohort["analysis_manifest"] and c["files"] == cohort["files"]
        ]
        if len(matches) == 1:
            return matches[0]
    return cohort


def inspect_data(package_path: Path):
    """Read-only exact binding for independent source audit and data authority."""
    from src.analysis_agent.entity_adapter import code_version

    from . import gate
    from .issuer_authority import binding

    package = json.loads(Path(package_path).read_bytes())
    baseline = PATHS.root / "site"
    commit = gate._trusted_site_commit(PATHS.root)
    gate.require_trusted_site_baseline(baseline, trusted_commit=commit)
    raw = encoded(executive_projection(json.loads((baseline / EXECUTIVE).read_bytes()), package))
    spec = {
        "schema_version": "issuer_release_v1",
        "stage": "data_only",
        "baseline_commit": commit,
        "baseline_manifest_sha256": sha((baseline / manifests.MANIFEST_NAME).read_bytes()),
        **{
            k: package[k]
            for k in (
                "entity_key",
                "period_id",
                "package_id",
                "evidence_fingerprint",
                "source_binding",
            )
        },
        "analysis_entry": None,
        "analysis_sha256": None,
        "analysis_bytes": 0,
        "executive_sha256": sha(raw),
        "executive_bytes": len(raw),
        "producer_code_version": code_version(),
        "authorization_sha256": None,
        "previous_entry": None,
        "previous_file": None,
    }
    return {
        "anchor": spec,
        "binding": binding(package, spec),
        "status": "no_visual_change" if raw == (baseline / EXECUTIVE).read_bytes() else "data_change",
    }


def verify_no_visual_change(package_path: Path, expected_binding: dict, site: Path = PATHS.root / "site"):
    """Reproduce a no-op handoff; a worker's status text alone is insufficient."""
    if Path(site).resolve() != (PATHS.root / "site").resolve():
        raise ValueError("No-change verification requires the trusted local publication")
    package = json.loads(Path(package_path).read_bytes())
    if package["source_binding"] != expected_binding:
        raise ValueError("No-change receipt names another source version")
    observed = inspect_data(package_path)
    if observed["status"] != "no_visual_change":
        raise ValueError("Issuer source changes a visible financial payload")
    verify_historical_baseline(PATHS.root, observed["anchor"], site)
    return {
        "status": "no_visual_change",
        "entity_key": package["entity_key"],
        "period_id": package["period_id"],
        "source_binding": package["source_binding"],
        "manifest_sha256": sha((Path(site) / manifests.MANIFEST_NAME).read_bytes()),
        "executive_sha256": observed["anchor"]["executive_sha256"],
    }


def prepare_data(package_path: Path, authorization_path: Path):
    from . import gate
    from .issuer_authority import authority

    inspected = inspect_data(package_path)
    spec = inspected["anchor"]
    spec["authorization_sha256"] = sha(Path(authorization_path).read_bytes())
    expected = (
        PATHS.root
        / "analysis_runs/dashboard_updates/authorizations"
        / (spec["authorization_sha256"] + ".json")
    )
    if Path(authorization_path).resolve() != expected.resolve():
        raise ValueError("Retain the data authorization under its canonical private hash filename")
    package = json.loads(Path(package_path).read_bytes())
    with gate.flow.writer(gate.flow.ROOT):
        authority(package, spec)
        _write_pins([(ANCHOR, spec)])
    return {"status": "data_pins_prepared_not_published", "anchor": spec}


def prepare_issuer(record_path: Path, *, stage="combined", replace_version: str | None = None):
    """Prepare public pins from a currently approved thesis; never approve it."""
    from src.analysis_agent.entity_adapter import code_version

    from . import gate
    from .approval_cohorts import CONFIG, _cohorts, _optional_config, replacement_cohort

    if stage not in {"combined", "editorial_only"}:
        raise ValueError("Invalid editorial stage")
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
        previous = next(
            (
                e
                for e in old["analysis_manifest"]
                if manifests.analysis_identity(e) == manifests.analysis_identity(identity)
            ),
            None,
        )
        previous_file = next(
            (
                f
                for f in old["files"]
                if previous is not None
                and f["path"] == "data/v1/" + manifests.analysis_relative_path(previous).as_posix()
            ),
            None,
        )
        if previous is not None and replace_version != previous["version"]:
            raise ValueError("Select the exact prior version explicitly before preparing a revision")
        if previous is None and replace_version is not None:
            raise ValueError("No published prior version matches the requested replacement")
        executive = executive_projection(json.loads((baseline / EXECUTIVE).read_bytes()), entry[2])
        analysis_raw, executive_raw = encoded(gate._analysis_payload(*entry)), encoded(executive)
        if stage == "editorial_only" and executive_raw != (baseline / EXECUTIVE).read_bytes():
            raise ValueError("Editorial-only release requires the financial projection already published")
        spec = {
            "schema_version": "issuer_release_v1",
            "stage": stage,
            "baseline_commit": commit,
            "baseline_manifest_sha256": sha((baseline / manifests.MANIFEST_NAME).read_bytes()),
            **{
                k: entry[2][k]
                for k in (
                    "entity_key",
                    "period_id",
                    "package_id",
                    "evidence_fingerprint",
                    "source_binding",
                )
            },
            "analysis_entry": identity,
            "analysis_sha256": sha(analysis_raw),
            "analysis_bytes": len(analysis_raw),
            "executive_sha256": sha(executive_raw),
            "executive_bytes": len(executive_raw),
            "producer_code_version": code_version(),
            "authorization_sha256": None,
            "previous_entry": previous,
            "previous_file": previous_file,
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
        cohort = _stable_cohort(repo, spec, cohort)
        trusted = _cohorts(_optional_config(repo, commit))
        replaced = replacement_cohort(
            {
                "entry": identity,
                "file": cohort["files"][0],
                "replaces": {"entry": previous, "file": previous_file},
            }
            if previous
            else None,
            trusted,
            old,
        )
        config = {
            "schema_version": "analysis_approval_cohorts_v1",
            "cohorts": [*[c for c in trusted if c != replaced], cohort],
        }
        _write_pins([(ANCHOR, spec), (CONFIG, config)])
    return {"status": "pins_prepared_not_published", "anchor": spec, "cohort": cohort}


def publish_issuer(record_paths: list[Path], out_dir: Path, *, package_path: Path | None = None):
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
    new = (
        []
        if spec["stage"] == "data_only"
        else [
            r
            for r in records
            if (
                manifests.analysis_identity(r["draft"]) == (spec["entity_key"], spec["period_id"])
                and r["version"] == spec["analysis_entry"]["version"]
            )
        ]
    )
    if spec["stage"] != "data_only" and (
        len(new) != 1 or new[0]["draft"].get("source_profile") != "issuer_quarter_v1"
    ):
        raise ValueError("Exactly one current issuer-quarter record is required")
    name = (
        "data/v1/" + manifests.analysis_relative_path(spec["analysis_entry"]).as_posix()
        if spec["analysis_entry"] is not None
        else None
    )
    if name and (baseline / name).exists() and spec["previous_entry"] is None:
        raise ValueError("Issuer thesis already published: reconcile its existing version before a revision")
    original_executive = json.loads((baseline / EXECUTIVE).read_bytes())

    def verified():
        if spec["stage"] == "data_only":
            from .issuer_authority import verified_data

            if package_path is None:
                raise ValueError("Data-only publication requires its exact source-replayed package")
            package = json.loads(Path(package_path).read_bytes())
            data_raw, authorities = verified_data(package, spec, baseline)
            cohorts = verify_approval_cohorts(
                record_paths, repo, spec["baseline_commit"], old, gate.flow.ROOT
            )
            return authorities, cohorts, None, data_raw
        current = gate._verify_under_lock(new, gate.flow.ROOT)[0]
        if gate._analysis_manifest_entry(current[1]) != spec["analysis_entry"]:
            raise ValueError("Issuer approval changed or names another version")
        for key in ("entity_key", "period_id", "package_id", "evidence_fingerprint", "source_binding"):
            if current[2][key] != spec[key]:
                raise ValueError("Thesis handoff differs from its source version")
        analysis_raw = encoded(gate._analysis_payload(*current))
        if sha(analysis_raw) != spec["analysis_sha256"] or len(analysis_raw) != spec["analysis_bytes"]:
            raise ValueError("Issuer thesis differs from reviewed output")
        executive = executive_projection(original_executive, current[2])
        require_scope(original_executive, executive, spec["entity_key"], spec["period_id"])
        executive_raw = encoded(executive)
        if spec["stage"] == "editorial_only" and executive_raw != (baseline / EXECUTIVE).read_bytes():
            raise ValueError("Editorial-only release cannot change the financial projection")
        if sha(executive_raw) != spec["executive_sha256"] or len(executive_raw) != spec["executive_bytes"]:
            raise ValueError("Issuer chart projection differs from reviewed output")
        pending = {
            "entry": spec["analysis_entry"],
            "bytes": analysis_raw,
            "file": {"path": name, "sha256": sha(analysis_raw), "bytes": len(analysis_raw)},
        }
        if spec["previous_entry"] is not None:
            pending["replaces"] = {"entry": spec["previous_entry"], "file": spec["previous_file"]}
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
    if name:
        target = web / manifests.analysis_relative_path(spec["analysis_entry"])
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(first[2])
    (web / "executive.json").write_bytes(first[3])
    dist = gate.build_web()
    if transport.frontend_entries(dist) != transport.frontend_entries(baseline):
        raise ValueError(
            "Issuer-only update requires unchanged dashboard frontend; review UI changes separately"
        )
    with tempfile.TemporaryDirectory(prefix="issuer-site-") as temporary:
        prepared = Path(temporary) / "site"
        shutil.copytree(baseline, prepared)
        if name:
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
        additions = [spec["analysis_entry"]] if name else []
        retained_entries = [e for e in old["analysis_manifest"] if e != spec["previous_entry"]]
        entries = sorted([*retained_entries, *additions], key=manifests.analysis_sort_key)

        def validate(candidate):
            preserved = preserved_files(candidate, repo, spec)
            problems = _verify_site(candidate, preserved_approval_files=preserved)
            if problems:
                raise ValueError(f"Issuer candidate rejected: {problems[:3]}")

        with gate.flow.writer(gate.flow.ROOT):
            gate.require_trusted_site_baseline(baseline, trusted_commit=spec["baseline_commit"])
            if verified() != first or anchor(repo) != spec or manifests.current_commit(repo) != start_head:
                raise ValueError("Issuer source, approval, release or build code changed")
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
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prepare-record", type=Path)
    parser.add_argument("--editorial-only", action="store_true")
    parser.add_argument("--replace-version", help="exact currently published thesis version to supersede")
    parser.add_argument("--inspect-data", type=Path)
    parser.add_argument("--prepare-data", type=Path)
    parser.add_argument("--data-authorization", type=Path)
    parser.add_argument("--package", type=Path)
    parser.add_argument("--record", type=Path, action="append", default=[])
    parser.add_argument("--out", type=Path, default=PATHS.root / "site")
    args = parser.parse_args(argv)
    try:
        choices = sum(bool(x) for x in (args.prepare_record, args.inspect_data, args.prepare_data))
        if choices > 1 or (choices and args.record):
            raise ValueError("Preparation, inspection and publication are separate invocations")
        if args.inspect_data:
            print(json.dumps(inspect_data(args.inspect_data), ensure_ascii=False))
            return 0
        if args.prepare_data:
            if not args.data_authorization:
                raise ValueError("Data preparation requires exact private owner authority and source audit")
            print(json.dumps(prepare_data(args.prepare_data, args.data_authorization), ensure_ascii=False))
            return 0
        if args.prepare_record:
            stage = "editorial_only" if args.editorial_only else "combined"
            print(
                json.dumps(
                    prepare_issuer(args.prepare_record, stage=stage, replace_version=args.replace_version),
                    ensure_ascii=False,
                )
            )
            return 0
        if not args.record:
            raise ValueError("Publication requires exact baseline record paths")
        value = publish_issuer(args.record, args.out, package_path=args.package)
    except (ValueError, OSError, subprocess.SubprocessError, PublicationRefused) as error:
        print(f"Issuer publication refused: {error}")
        return 1
    print(json.dumps({"manifest_sha256": value["receipt"]["manifest_sha256"], "site_built_verified": True}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
