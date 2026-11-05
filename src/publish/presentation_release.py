"""Strict interface-only publication over the current quarterly and AFAC chain.

This profile keeps the historical ``--ui-only`` gate unchanged. It replays the
current quarterly approval cohorts and the exact private AFAC source release,
then permits only compiled frontend files to differ from the served baseline.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from src.analysis_agent import lifecycle as flow

from . import manifest as manifests
from .records import PublicationRefused, load_records

PROFILE_PATH = "config/publish/presentation-release.json"
PROFILE_SCHEMA = "presentation_release_v1"
AFAC_PRODUCER_COMMIT = "00a4353afe560ea81cd0a07190bb46c7cda2a3fa"
PRESENTATION_FILES = ("index.html",)
PRESENTATION_PREFIXES = ("assets/",)


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def load_profile(repo: Path) -> dict[str, Any]:
    path = Path(repo) / PROFILE_PATH
    if path.is_symlink() or not path.is_file():
        raise ValueError("Presentation release profile is missing or symlinked")
    raw = path.read_bytes()
    committed = subprocess.check_output(["git", "show", f"HEAD:{PROFILE_PATH}"], cwd=repo)
    if raw != committed:
        raise ValueError("Presentation release profile differs from committed HEAD")
    value = json.loads(raw)
    if (
        set(value) != {"schema_version", "afac_producer_commit", "afac_request"}
        or value["schema_version"] != PROFILE_SCHEMA
    ):
        raise ValueError("Unknown presentation release profile")
    if value["afac_producer_commit"] != AFAC_PRODUCER_COMMIT:
        raise ValueError("Presentation profile must use the exact published AFAC producer")
    request = value["afac_request"]
    if (
        not isinstance(request, dict)
        or set(request) != {"path", "sha256"}
        or request["path"] != "tmp/source-updates/afac-history-correction-20261104/request.json"
        or request["sha256"] != "35401e58d25c690d4375aa0782b234c92cbf67206a3c8646fdb5b5cb53fe549c"
    ):
        raise ValueError("Presentation profile must name the exact inspected AFAC request")
    return value


_AFAC_REPLAY_PROGRAM = r"""
import hashlib, json, sys
from pathlib import Path
from src.analysis_agent import lifecycle as flow
from src.publish import afac_history_update as update
repo=Path.cwd()
request=repo / sys.argv[1]
result=update.evaluate(repo, request, existing=True)
authority=update.authority(repo, result["request"], result["scope"])
value={
    "scope":result["scope"],
    "members":result["members"],
    "contracts":result["contracts"],
    "state":result["state"],
    "authorized":result["authorized"],
    "outputs":[
        {"path":name,"sha256":hashlib.sha256(raw).hexdigest(),"bytes":len(raw)}
        for name,raw in sorted(result["outputs"].items())
    ],
    "authority":list(authority),
}
print(json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(",",":")))
"""


def replay_afac_sources(repo: Path, profile: dict[str, Any], anchor: dict[str, Any]) -> dict[str, Any]:
    """Run the exact published source producer against current private inputs."""
    from . import afac_history_scope, afac_history_update

    repo = Path(repo).resolve()
    commit = profile["afac_producer_commit"]
    afac_history_update.transport._git(repo, "merge-base", "--is-ancestor", commit, "HEAD")
    released_version = anchor["scope"]["producer_code_version"]
    if afac_history_scope.producer_version_at_commit(commit, repo) != released_version:
        raise ValueError("Pinned AFAC producer commit differs from the released source fingerprint")

    request_ref = profile["afac_request"]
    request_path = repo / request_ref["path"]
    if request_path.is_symlink() or not request_path.is_file():
        raise ValueError("Exact private AFAC request is missing or symlinked")
    if _sha(request_path.read_bytes()) != request_ref["sha256"]:
        raise ValueError("Private AFAC request differs from its exact inspected hash")

    from .afac_history_update import request_inputs

    _, request = request_inputs(repo, request_path)
    temp_root = Path(tempfile.mkdtemp(prefix="presentation-afac-replay-")).resolve()
    checkout = temp_root / "producer"
    try:
        subprocess.run(
            ["git", "worktree", "add", "--detach", str(checkout), commit],
            cwd=repo,
            check=True,
            capture_output=True,
            text=True,
        )
        for name in ("analysis_runs", "data/bronze", "tmp/source-updates"):
            source = repo / name
            if not source.exists():
                raise ValueError(f"Required restored AFAC source directory is missing: {name}")
            if any(path.is_symlink() for path in [source, *source.rglob("*")]):
                raise ValueError(f"Private AFAC source directory contains a symlink: {name}")
            shutil.copytree(source, checkout / name, dirs_exist_ok=True, copy_function=shutil.copy2)

        result = subprocess.run(
            [sys.executable, "-B", "-c", _AFAC_REPLAY_PROGRAM, request_ref["path"]],
            cwd=checkout,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=3600,
            env={**__import__("os").environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"},
        )
        if result.returncode:
            raise ValueError("Pinned AFAC producer replay failed: " + result.stderr[-2400:])
        lines = [line for line in result.stdout.splitlines() if line.strip()]
        try:
            replay = json.loads(lines[-1])
        except (IndexError, json.JSONDecodeError) as error:
            raise ValueError(
                "Pinned AFAC producer replay returned no machine-readable result: " + result.stdout[-1200:]
            ) from error
    finally:
        if checkout.exists():
            subprocess.run(
                ["git", "worktree", "remove", "--force", str(checkout)],
                cwd=repo,
                check=True,
                capture_output=True,
            )
        shutil.rmtree(temp_root, ignore_errors=True)

    require_afac_replay_matches_anchor(replay, anchor)
    return replay


def require_afac_replay_matches_anchor(replay: dict[str, Any], anchor: dict[str, Any]) -> None:
    """Fail closed unless replay and both exact authority files match the release anchor."""
    if (
        replay["scope"] != anchor["scope"]
        or replay["members"] != anchor["members"]
        or replay["contracts"] != anchor["contracts"]
        or replay["authority"] != [anchor["authorization_sha256"], anchor["source_audit_sha256"]]
    ):
        raise ValueError("Pinned AFAC replay, owner authority or independent audit differs from release")


def _public_file_map(site: Path) -> dict[str, tuple[str, int]]:
    return {row["path"]: (row["sha256"], row["bytes"]) for row in manifests.file_entries(site)}


def _preserved_map(files: dict[str, tuple[str, int]]) -> dict[str, tuple[str, int]]:
    return {
        name: identity
        for name, identity in files.items()
        if name not in PRESENTATION_FILES
        and not any(name.startswith(prefix) for prefix in PRESENTATION_PREFIXES)
    }


def verify_presentation_only_site(site: Path, repo: Path) -> None:
    """Use both the generic verifier and the unique strong AFAC verifier."""
    from scripts.check_pages_publication import verifier_for, verify_site

    from .verify import verify_site as verify_generic

    problems = verify_generic(site)
    if problems:
        raise ValueError(f"presentation candidate failed normal site verification: {problems[:5]}")
    selected = verifier_for(site, repo)
    if selected != "src.publish.afac_history_scope":
        raise ValueError(f"presentation release requires the pinned AFAC verifier, got {selected!r}")
    problems = verify_site(site, repo)
    if problems:
        raise ValueError(f"presentation candidate failed strong AFAC verification: {problems[:5]}")


def _replay_release(record_paths, repo, trusted_commit, current_manifest, ledger_root):
    """Replay current approval, source and revocation chains while caller locks."""
    from . import afac_history_scope

    profile = load_profile(repo)
    request_path = Path(repo) / profile["afac_request"]["path"]
    if request_path.is_symlink() or not request_path.is_file():
        raise ValueError("Exact private AFAC request is missing or symlinked")
    if _sha(request_path.read_bytes()) != profile["afac_request"]["sha256"]:
        raise ValueError("Private AFAC request differs from its exact inspected hash")

    anchor = afac_history_scope.anchor(repo)
    replay = replay_afac_sources(repo, profile, anchor)

    selected_records = load_records(record_paths)
    selected = {
        (*manifests.analysis_identity(record["draft"]), record["version"]): record
        for record in selected_records
    }
    expected = {
        (*manifests.analysis_identity(entry), entry["version"]): entry
        for entry in current_manifest["analysis_manifest"]
    }
    if set(selected) != set(expected):
        raise ValueError("Selected records differ from the exact trusted publication identities")
    for identity, record in selected.items():
        entry = expected[identity]
        if (
            record["content_hash"] != entry["content_hash"]
            or record["draft"]["evidence_fingerprint"] != entry["evidence_fingerprint"]
        ):
            raise ValueError("Selected record bytes differ from the exact trusted approval identities")
    replayed = sorted(replay["authorized"], key=manifests.analysis_sort_key)
    manifest_entries = sorted(current_manifest["analysis_manifest"], key=manifests.analysis_sort_key)
    if manifest_entries != replayed:
        raise ValueError("Served analysis manifest differs from the current quarterly approval chain")

    return {"afac": replay}


def publish_presentation_only(
    record_paths,
    out_dir: Path,
    *,
    repo: Path,
    ledger_root: Path,
    web_dir: Path,
    web_data_v1: Path,
    build_web,
    require_trusted_baseline,
    trusted_site_commit,
    assemble_site,
    write_receipt,
):
    """Rebuild only frontend presentation and atomically preserve all evidence."""
    repo, out_dir = Path(repo).resolve(), Path(out_dir).resolve()
    try:
        manifests.refuse_if_build_inputs_dirty(root=repo)
    except RuntimeError as error:
        raise PublicationRefused(f"uncommitted presentation build inputs: {error}") from error

    records = load_records(record_paths)
    if not records:
        raise PublicationRefused("no --record given; refuse to publish an empty approval manifest")
    trusted_commit = trusted_site_commit(repo)
    require_trusted_baseline(out_dir, root=repo, trusted_commit=trusted_commit)
    verify_presentation_only_site(out_dir, repo)

    current_manifest = manifests.load_manifest(out_dir)
    baseline_files = _public_file_map(out_dir)
    if not any(path.startswith("data/v1/") for path in baseline_files):
        raise PublicationRefused("trusted site has no public data payload to preserve")
    try:
        with flow.writer(ledger_root):
            first = _replay_release(record_paths, repo, trusted_commit, current_manifest, ledger_root)
    except ValueError as error:
        message = f"current presentation approval/source chain failed replay: {error}"
        raise PublicationRefused(message) from error

    source_data = {path: identity for path, identity in baseline_files.items() if path.startswith("data/v1/")}
    if Path(web_data_v1).exists():
        shutil.rmtree(web_data_v1)
    Path(web_data_v1).parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(out_dir / "data/v1", web_data_v1)
    dist_dir = build_web(web_dir)
    built_files = _public_file_map(dist_dir)
    if {path: value for path, value in built_files.items() if path.startswith("data/v1/")} != source_data:
        raise PublicationRefused("frontend build changed or omitted a public data file")
    unexpected_build_files = {
        name
        for name in built_files
        if not name.startswith(("assets/", "data/v1/"))
        and name not in {"index.html", "access.html", "review.html"}
    }
    if unexpected_build_files or "index.html" not in built_files:
        raise PublicationRefused("frontend build emitted unexpected or missing public files")

    expected_preserved = _preserved_map(baseline_files)

    def validate_candidate(candidate: Path) -> None:
        if _preserved_map(_public_file_map(candidate)) != expected_preserved:
            raise ValueError("presentation candidate changed protected data, contracts, sources or evidence")
        candidate_manifest = manifests.load_manifest(candidate)
        if candidate_manifest["contracts"] != current_manifest["contracts"]:
            raise ValueError("presentation candidate changed public contract pins")
        if candidate_manifest["analysis_manifest"] != current_manifest["analysis_manifest"]:
            raise ValueError("presentation candidate changed approved analysis identities")
        if not candidate_manifest["files"]:
            raise ValueError("presentation candidate has no manifested files")
        verify_presentation_only_site(candidate, repo)

    with tempfile.TemporaryDirectory(prefix="presentation-site-") as temporary:
        staged_dist = Path(temporary) / "dist"
        shutil.copytree(out_dir, staged_dist)
        if any(path.is_symlink() for path in dist_dir.rglob("*")):
            raise PublicationRefused("frontend build contains a symlink")
        shutil.copyfile(dist_dir / "index.html", staged_dist / "index.html")
        for asset in sorted((dist_dir / "assets").rglob("*")):
            if not asset.is_file():
                continue
            name = asset.relative_to(dist_dir).as_posix()
            target = staged_dist / name
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.exists() and target.read_bytes() != asset.read_bytes():
                raise PublicationRefused(f"frontend build reused an asset path with different bytes: {name}")
            if not target.exists():
                shutil.copyfile(asset, target)
        for name, expected in expected_preserved.items():
            target = staged_dist / name
            if target.exists() or target.is_symlink():
                if target.is_symlink() or not target.is_file():
                    raise PublicationRefused(f"frontend build changed protected file type: {name}")
                if (manifests.sha256_file(target), target.stat().st_size) != expected:
                    raise PublicationRefused(f"frontend build changed protected file: {name}")
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(out_dir / name, target)
        if _preserved_map(_public_file_map(staged_dist)) != expected_preserved:
            raise PublicationRefused("frontend build added, changed or omitted a protected site file")

        try:
            with flow.writer(ledger_root):
                require_trusted_baseline(out_dir, root=repo, trusted_commit=trusted_commit)
                verify_presentation_only_site(out_dir, repo)
                current = _replay_release(record_paths, repo, trusted_commit, current_manifest, ledger_root)
                if current != first:
                    raise ValueError("approval, source or revocation state changed during the frontend build")
                manifest = assemble_site(
                    staged_dist,
                    current_manifest["analysis_manifest"],
                    out_dir,
                    contracts=current_manifest["contracts"],
                    validate_candidate=validate_candidate,
                )
        except ValueError as error:
            raise PublicationRefused(
                f"presentation release failed its locked pre-swap checks (nothing swapped in): {error}"
            ) from error

    receipt = write_receipt(manifest, first["afac"]["authorized"], out_dir, root=ledger_root)
    return {"manifest": manifest, "receipt": receipt}
