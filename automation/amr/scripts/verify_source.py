#!/usr/bin/env python3
"""Read-only integrity check for the audited AMR reference sources."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify(amr_root: Path, installed_root: Path | None = None) -> list[str]:
    repo_root = amr_root.parents[1]
    manifest = json.loads((amr_root / "source-manifest.json").read_text(encoding="utf-8"))
    errors: list[str] = []
    expected: set[Path] = set()
    for item in manifest:
        relative = Path(item["path"])
        target = (repo_root / relative).resolve()
        if not target.is_relative_to((amr_root / "skills").resolve()):
            errors.append(f"Manifest path outside skills: {relative.as_posix()}")
            continue
        if target in expected:
            errors.append(f"Duplicate manifest path: {relative.as_posix()}")
        expected.add(target)
        if not target.is_file() or sha256(target) != item["staged_sha256"]:
            errors.append(f"Source differs from reviewed copy: {relative.as_posix()}")
        if installed_root is not None:
            installed = installed_root / target.relative_to(amr_root / "skills")
            if not installed.is_file() or sha256(installed) != item["original_sha256"]:
                errors.append(f"Installed source differs from audit: {relative.as_posix()}")
    actual = {
        path.resolve()
        for path in (amr_root / "skills").rglob("*")
        if path.is_file() and "__pycache__" not in path.parts and path.suffix not in {".pyc", ".pyo"}
    }
    for extra in sorted(actual - expected):
        errors.append(f"Unreviewed source file: {extra.relative_to(repo_root).as_posix()}")
    if not expected:
        errors.append("Source manifest must not be empty")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--installed-root", type=Path, help="Optional read-only comparison with installed skills")
    args = parser.parse_args()
    amr_root = Path(__file__).resolve().parents[1]
    errors = verify(amr_root, args.installed_root)
    print(json.dumps({"verified": not errors, "errors": errors}, ensure_ascii=False, indent=2))
    return bool(errors)


if __name__ == "__main__":
    raise SystemExit(main())
