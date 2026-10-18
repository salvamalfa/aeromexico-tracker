"""Require PR documentation dispositions and validate changed Markdown local links."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
from pathlib import Path
from urllib.parse import unquote, urlsplit

DISPOSITIONS = {"keep", "update", "archive", "delete_candidate", "pending"}
BLOCK = re.compile(r"<!--\s*document-lifecycle:v1\s*(\{.*?\})\s*-->", re.S)


def changed_documents(root: Path, base: str) -> list[str]:
    changed = (
        subprocess.check_output(["git", "diff", "--name-only", "-z", base, "HEAD", "--"], cwd=root)
        .decode()
        .split("\0")
    )
    return sorted(
        path
        for path in changed
        if path
        and (
            path.endswith(".md")
            or ".example." in Path(path).name
            or (path.startswith("docs/") and Path(path).suffix in {".json", ".csv", ".html", ".ipynb"})
        )
    )


def validate_dispositions(root: Path, paths: list[str], summary: str) -> list[str]:
    if not paths:
        return []
    block = BLOCK.search(summary)
    if block is None:
        return ["Documentation changed: add document-lifecycle:v1 dispositions to the PR summary"]
    try:
        entries = json.loads(block[1])["files"]
        records = {item["path"]: item for item in entries}
        if len(records) != len(entries):
            return ["Duplicate documentation lifecycle paths"]
    except (ValueError, KeyError, TypeError):
        return ["Invalid document-lifecycle:v1 JSON"]
    errors = []
    for path in paths:
        row = records.get(path, {})
        if row.get("disposition") not in DISPOSITIONS or not str(row.get("reason", "")).strip():
            errors.append(f"Missing disposition/reason: {path}")
        file = root / path
        if file.suffix != ".md" or not file.is_file():
            continue
        text = re.sub(r"```.*?```", "", file.read_text(encoding="utf-8"), flags=re.S)
        for target in re.findall(r"\]\(([^)]+)\)", text):
            value = urlsplit(target.strip().strip("<>"))
            if value.scheme or not value.path:
                continue
            resolved = (file.parent / unquote(value.path)).resolve()
            if not resolved.is_relative_to(root.resolve()) or not resolved.exists():
                errors.append(f"Broken/outside local reference in {path}: {target}")
    return errors


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", required=True)
    parser.add_argument("--summary-file", type=Path)
    parser.add_argument("--list", action="store_true")
    args = parser.parse_args(argv)
    root = Path(__file__).resolve().parents[1]
    paths = changed_documents(root, args.base)
    if args.list:
        print(json.dumps(paths, indent=2))
        return 0
    summary = args.summary_file.read_text() if args.summary_file else os.getenv("DOC_LIFECYCLE_SUMMARY", "")
    errors = validate_dispositions(root, paths, summary)
    print(json.dumps({"documents": len(paths), "errors": errors}, ensure_ascii=False, indent=2))
    return bool(errors)


if __name__ == "__main__":
    raise SystemExit(main())
