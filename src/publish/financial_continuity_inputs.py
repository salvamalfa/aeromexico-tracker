"""Immutable inputs for explicitly local financial runtime continuity checks."""

from __future__ import annotations

import io
import json
import re
import subprocess
import tarfile
import tempfile
import sys
from pathlib import Path, PurePosixPath

from . import editorial as transport
from .financial_scope import encoded, sha

POLICY = "config/publish/financial-continuity-local.json"
SCOPE = "financial_runtime_exact_preservation_local_v1"
BINDING = {
    "published_commit",
    "production_commit",
    "runtime_sha256",
    "original_anchor_sha256",
    "original_authorization_sha256",
    "original_review_sha256",
    "site_closure_sha256",
    "source_closure_sha256",
}
ASSERTIONS = {
    "code_review_passed",
    "original_sources_replayed",
    "exact_site_preserved",
    "original_authority_preserved",
    "adversarial_tests_passed",
}


def document(raw: bytes) -> dict:
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("Duplicate continuity document field")
            result[key] = value
        return result

    value = json.loads(raw, object_pairs_hook=unique)
    if not isinstance(value, dict):
        raise ValueError("Continuity document must be an object")
    return value


def regular(path: Path, root: Path) -> bytes:
    """Reject symlink components before reading any private input."""
    path = path.absolute()
    root = root.absolute()
    if not path.is_relative_to(root):
        raise ValueError("Continuity input escapes its root")
    for part in (root, *path.relative_to(root).parents):
        candidate = part if part == root else root / part
        if candidate.is_symlink():
            raise ValueError("Continuity input contains a symlink")
    if path.is_symlink() or not path.is_file():
        raise ValueError("Continuity input is not a regular file")
    return path.read_bytes()


def committed(repo: Path, name: str) -> bytes:
    raw = regular(repo / name, repo)
    if raw != transport._git(repo, "show", f"HEAD:{name}"):
        raise ValueError("Local continuity policy must be committed")
    return raw


def ancestor(repo: Path, before: str, after: str) -> None:
    if not all(isinstance(v, str) and re.fullmatch("[a-f0-9]{40}", v) for v in (before, after)):
        raise ValueError("Invalid continuity commit")
    transport._git(repo, "merge-base", "--is-ancestor", before, after)


def tree_files(repo: Path, commit: str, prefix: str) -> dict:
    raw = transport._git(repo, "archive", commit, prefix)
    result = {}
    with tarfile.open(fileobj=io.BytesIO(raw)) as archive:
        for item in archive:
            if item.isdir():
                continue
            if not item.isfile() or not item.name.startswith(prefix + "/"):
                raise ValueError("Published continuity tree contains a non-regular file")
            content = archive.extractfile(item).read()
            result[item.name[len(prefix) + 1 :]] = {"sha256": sha(content), "bytes": len(content)}
    return result


def site_files(site: Path) -> dict:
    result = {}
    if site.is_symlink() or not site.is_dir():
        raise ValueError("Continuity site is not a regular directory")
    for path in sorted(site.rglob("*")):
        if path.is_symlink():
            raise ValueError("Continuity site contains a symlink")
        if path.is_dir():
            continue
        raw = regular(path, site)
        result[path.relative_to(site).as_posix()] = {"sha256": sha(raw), "bytes": len(raw)}
    return result


def runtime_at_commit(repo: Path, commit: str) -> str:
    archive = transport._git(
        repo, "archive", commit, "src", "contracts", "config", "web", "uv.lock", ".agents"
    )
    with tempfile.TemporaryDirectory(prefix="financial-continuity-runtime-") as folder:
        base = Path(folder)
        with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
            tar.extractall(base, filter="data")
        result = subprocess.run(
            [
                sys.executable,
                "-B",
                "-c",
                "from pathlib import Path; from src.analysis_agent.entity_adapter import code_version; "
                "from src.config import PATHS; assert PATHS.root.resolve()==Path.cwd().resolve(); print(code_version())",
            ],
            cwd=base,
            capture_output=True,
            text=True,
        )
        if result.returncode or not re.fullmatch("[a-f0-9]{64}\\n?", result.stdout):
            raise ValueError("Cannot reproduce reviewed continuity runtime")
        return result.stdout.strip()


def policy(repo: Path) -> tuple[dict, bytes, bytes]:
    raw = committed(repo, POLICY)
    value = document(raw)
    if (
        set(value) != {"schema_version", "scope", "binding", "review_sha256", "procedure_consent"}
        or value["schema_version"] != "financial_continuity_local_v1"
        or value["scope"] != SCOPE
        or not isinstance(value["binding"], dict)
        or set(value["binding"]) != BINDING
    ):
        raise ValueError("Invalid local continuity policy")
    binding = value["binding"]
    for key in BINDING - {"production_commit", "published_commit"}:
        if not isinstance(binding[key], str) or not re.fullmatch("[a-f0-9]{64}", binding[key]):
            raise ValueError("Invalid continuity digest")
    consent = value["procedure_consent"]
    if (
        not isinstance(consent, dict)
        or set(consent) != {"source_reference", "instruction", "at", "local_only"}
        or consent["local_only"] is not True
        or not all(
            isinstance(consent[k], str) and consent[k].strip()
            for k in ("source_reference", "instruction", "at")
        )
    ):
        raise ValueError("Missing explicit local procedure consent")
    key = value["review_sha256"]
    if not isinstance(key, str) or not re.fullmatch("[a-f0-9]{64}", key):
        raise ValueError("Invalid continuity review digest")
    review_raw = regular(repo / "analysis_runs/financial_continuity/reviews" / (key + ".json"), repo)
    if sha(review_raw) != key:
        raise ValueError("Continuity review changed")
    review = document(review_raw)
    if (
        set(review)
        != {
            "schema_version",
            "scope",
            "binding",
            "status",
            "unresolved_findings",
            "reviewer_reference",
            "assertions",
        }
        or review["schema_version"] != "financial_continuity_review_v1"
        or review["scope"] != SCOPE
        or review["binding"] != binding
        or review["status"] != "passed"
        or review["unresolved_findings"] != []
        or not isinstance(review["reviewer_reference"], str)
        or not review["reviewer_reference"].strip()
        or not isinstance(review["assertions"], dict)
        or set(review["assertions"]) != ASSERTIONS
        or any(v is not True for v in review["assertions"].values())
    ):
        raise ValueError("Independent review does not cover this continuity binding")
    return value, raw, review_raw


def sources(repo: Path, record: Path, spec: dict, ledger: Path) -> dict:
    from .financial_sources import source_snapshot

    for folder in (repo / "analysis_runs", repo / "data/bronze"):
        if folder.is_symlink():
            raise ValueError("Continuity source root contains a symlink")
    for path in (repo / "analysis_runs").rglob("*"):
        if path.is_symlink():
            raise ValueError("Continuity evidence contains a symlink")
    package = repo / "analysis_runs/evidence" / (spec["package_id"] + ".json")
    doc = json.loads(regular(package, repo))
    for entry in doc["sources"]:
        name = entry["source_file"]
        path = PurePosixPath(name)
        if path.is_absolute() or ".." in path.parts or "\\" in name:
            raise ValueError("Continuity source path escapes Bronze")
        source = repo / "data/bronze" / name
        regular(source, repo)
        sidecar = Path(str(source) + ".meta.json")
        if sidecar.exists() or sidecar.is_symlink():
            regular(sidecar, repo)
    snapshot = source_snapshot([record], spec, ledger, repo)
    result = {}
    for name, digest in snapshot.items():
        path = Path(name)
        regular(path, repo)
        result[path.relative_to(repo.resolve()).as_posix()] = digest
    return result


def fingerprint(value: dict) -> str:
    return sha(encoded(dict(sorted(value.items()))))
