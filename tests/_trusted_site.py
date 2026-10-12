from __future__ import annotations

import io
import subprocess
import tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def copy_origin_master_site(destination: Path) -> Path:
    """Copy the immutable published baseline without touching the worktree site."""
    commit = subprocess.run(
        ["git", "rev-parse", "origin/master"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    archive = subprocess.run(
        ["git", "archive", commit, "site"],
        cwd=ROOT,
        check=True,
        capture_output=True,
    ).stdout
    destination.mkdir(parents=True, exist_ok=True)
    with tarfile.open(fileobj=io.BytesIO(archive), mode="r:") as bundle:
        bundle.extractall(destination, filter="data")
    return destination / "site"
