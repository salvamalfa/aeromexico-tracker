"""Content identity of the native AFAC producer, independent of HEAD and Gold."""

import hashlib
import json
import subprocess
from pathlib import Path

from src.source_updates.catalog import ROOT

ROOTS = ("src", "scripts", "contracts", "config", "sql", "data/reference", "pyproject.toml", "uv.lock")


def included(name):
    path = Path(name)
    return (
        (path.parts[0] in {"src", "scripts"} and path.suffix == ".py")
        or path.parts[0] == "contracts"
        and path.suffix in {".yaml", ".yml", ".json"}
        or path.parent.as_posix() == "config"
        and path.suffix in {".yaml", ".yml", ".json", ".csv"}
        or name.startswith("sql/")
        and path.suffix == ".sql"
        or name.startswith("data/reference/")
        and path.suffix in {".csv", ".json", ".yaml"}
        or name in {"pyproject.toml", "uv.lock"}
    )


def _fingerprint(files):
    return hashlib.sha256(
        (json.dumps(files, sort_keys=True, separators=(",", ":")) + "\n").encode()
    ).hexdigest()


def producer_version(repo=ROOT):
    paths = []
    for name in ROOTS:
        path = repo / name
        paths.extend(path.rglob("*") if path.is_dir() else [path])
    return _fingerprint(
        {
            path.relative_to(repo).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in paths
            if path.is_file() and included(path.relative_to(repo).as_posix())
        }
    )


def version_at_commit(commit, repo=ROOT):
    tree = subprocess.check_output(
        ["git", "ls-tree", "-rz", "--format=%(objectname) %(path)", commit], cwd=repo
    )
    selected = [entry.split(b" ", 1) for entry in tree.split(b"\0") if entry]
    selected = [(sha, name.decode()) for sha, name in selected if included(name.decode())]
    raw = subprocess.check_output(
        ["git", "cat-file", "--batch"], cwd=repo, input=b"\n".join(sha for sha, _ in selected) + b"\n"
    )
    offset, files = 0, {}
    for _, name in selected:
        end = raw.index(b"\n", offset)
        size = int(raw[offset:end].split()[2])
        body = raw[end + 1 : end + 1 + size]
        files[name] = hashlib.sha256(body).hexdigest()
        offset = end + size + 2
    return _fingerprint(files)


def verify_preparation(commit, version, repo=ROOT):
    subprocess.run(
        ["git", "merge-base", "--is-ancestor", commit, "HEAD"], cwd=repo, check=True, capture_output=True
    )
    if producer_version(repo) != version or version_at_commit(commit, repo) != version:
        raise ValueError("Native AFAC producer changed between preparation and data-only incorporation")
