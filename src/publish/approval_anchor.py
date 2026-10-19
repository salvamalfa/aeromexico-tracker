"""Select an original approval verifier without changing any approval record.

An anchor is provenance, never authorization: callers must still revalidate
every original record and require all protected payloads to remain exact.
"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
from pathlib import Path

from . import manifest as manifest_mod


def approval_implementation(repo: Path, trusted_commit: str, baseline: dict) -> str:
    """Bind the verifier to an ancestor's exact published thesis edition."""
    path = repo / "config/publish/preserved-analysis.json"
    if not path.exists():
        return trusted_commit
    if path.is_symlink():
        raise ValueError("Preserved-analysis anchor must not be a symlink")
    anchor = json.loads(path.read_bytes())
    if set(anchor) != {
        "schema_version",
        "published_site_commit",
        "published_manifest_sha256",
        "implementation_commit",
    }:
        raise ValueError("Invalid preserved-analysis anchor fields")
    if anchor["schema_version"] != "preserved_analysis_anchor_v1":
        raise ValueError("Unknown preserved-analysis anchor edition")
    for key, length in (
        ("published_site_commit", 40),
        ("implementation_commit", 40),
        ("published_manifest_sha256", 64),
    ):
        if not isinstance(anchor[key], str) or not re.fullmatch(rf"[a-f0-9]{{{length}}}", anchor[key]):
            raise ValueError("Invalid preserved-analysis anchor digest")
    original_commit = anchor["published_site_commit"]
    code = anchor["implementation_commit"]
    for ancestor, descendant in ((original_commit, trusted_commit), (code, original_commit)):
        if subprocess.run(
            ["git", "merge-base", "--is-ancestor", ancestor, descendant], cwd=repo, capture_output=True
        ).returncode:
            raise ValueError("Approval anchor is outside trusted publication history")
    raw = subprocess.check_output(
        ["git", "show", f"{original_commit}:site/publication_manifest.json"], cwd=repo
    )
    if hashlib.sha256(raw).hexdigest() != anchor["published_manifest_sha256"]:
        raise ValueError("Original approval manifest hash differs from anchor")
    original = json.loads(raw)
    if original["code_commit"] != code:
        raise ValueError("Approval implementation differs from original published manifest")
    if not baseline["analysis_manifest"] or original["analysis_manifest"] != baseline["analysis_manifest"]:
        raise ValueError("Approval anchor cannot authorize another thesis identity or version")

    def thesis_files(manifest):
        names = {
            "data/v1/" + manifest_mod.analysis_relative_path(item).as_posix()
            for item in manifest["analysis_manifest"]
        }
        rows = [row for row in manifest["files"] if row["path"] in names]
        if len(rows) != len(names) or len({row["path"] for row in rows}) != len(names):
            raise ValueError("Approval anchor is missing or duplicates a thesis payload")
        return {row["path"]: (row["sha256"], row["bytes"]) for row in rows}

    if thesis_files(original) != thesis_files(baseline):
        raise ValueError("Approval anchor cannot authorize changed thesis bytes")
    return code
