"""Require PR documentation dispositions and validate changed Markdown local links."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import unicodedata
from pathlib import Path
from urllib.parse import unquote, urlsplit

DISPOSITIONS = {"keep", "update", "archive", "delete_candidate", "pending"}
BLOCK = re.compile(r"<!--\s*document-lifecycle:v1\s*(\{.*?\})\s*-->", re.S)


def changed_documents(root: Path, base: str, head: str = "HEAD") -> list[str]:
    changed = (
        subprocess.check_output(
            ["git", "diff", "--no-renames", "--name-only", "-z", f"{base}...{head}", "--"], cwd=root
        )
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


def markdown_targets(text: str) -> list[str]:
    return re.findall(r"\]\(([^)]+)\)", text) + re.findall(r"(?m)^\s{0,3}\[[^\]]+\]:\s*(.+)", text)


def markdown_url(target: str):
    target = target.strip()
    if target.startswith("<") and ">" in target:
        target = target[1 : target.index(">")]
    else:
        target = target.split(maxsplit=1)[0] if target else ""
    return urlsplit(target)


def mutable_repo_document(value, root: Path) -> Path | None:
    repository = os.getenv("GITHUB_REPOSITORY", "salvamalfa/aeromexico-tracker")
    prefix = "/" + re.escape(repository)
    branch = r"/(?:refs/heads/)?(?:master|main|HEAD)/(.+)"
    if value.hostname == "github.com":
        match = re.fullmatch(prefix + r"/(?:blob|tree|raw)" + branch, value.path)
    elif value.hostname in {"raw.githubusercontent.com", "raw.github.com"}:
        match = re.fullmatch(prefix + branch, value.path)
    else:
        match = None
    if match:
        return (root / unquote(match[1])).resolve()
    return None


def prose_targets(target: str) -> tuple[str, ...]:
    """Keep literal filenames and also recognize punctuation at sentence endings."""
    trimmed = target
    while trimmed and trimmed[-1] not in "/\\_-" and unicodedata.category(trimmed[-1]).startswith("P"):
        trimmed = trimmed[:-1]
    return (target, trimmed) if trimmed and trimmed != target else (target,)


def inbound_references(root: Path, paths: list[str]) -> list[str]:
    """Inspect unchanged tracked consumers when a document was deleted or moved."""
    removed = {(root / path).resolve(): path for path in paths if not (root / path).exists()}
    if not removed:
        return []
    tracked = subprocess.check_output(["git", "ls-files", "-z"], cwd=root).decode().split("\0")
    errors = []
    for name in tracked:
        file = root / name
        if not name or file.is_symlink() or not file.is_file():
            continue
        with file.open("rb") as stream:
            prefix = stream.read(8192)
            if b"\0" in prefix:
                continue
            try:
                text = (prefix + stream.read()).decode("utf-8")
            except UnicodeDecodeError:
                continue
        referenced = set()
        for target in markdown_targets(text):
            value = markdown_url(target)
            if value.scheme:
                destination = mutable_repo_document(value, root)
                if destination in removed:
                    referenced.add(removed[destination])
                continue
            if not value.path:
                continue
            path = unquote(value.path)
            destination = root / path.lstrip("/") if path.startswith("/") else file.parent / path
            if destination.resolve() in removed:
                referenced.add(removed[destination.resolve()])
        for url in re.findall(r"https?://[^\s<>\"'`)]+", text):
            for target in prose_targets(url):
                destination = mutable_repo_document(urlsplit(target), root)
                if destination in removed:
                    referenced.add(removed[destination])
        # Immutable Git archive links are valid after retirement. Strip whole
        # links, including labels, before checking code/config/path literals.
        plain = re.sub(r"!?\[[^\]]*\]\([^)]+\)|!?\[[^\]]*\]\[[^\]]*\]", "", text)
        plain = re.sub(r"(?m)^\s{0,3}\[[^\]]+\]:.*$", "", plain)
        plain = re.sub(r"https?://[^\s<>\"'`]+", "", plain)
        normalized = plain.replace("\\", "/")
        normalized = re.sub(r"/{2,}", "/", normalized)
        for path in removed.values():
            if re.search(r"(?<![\w./-])" + re.escape(path) + r"(?![\w./-])", normalized):
                referenced.add(path)
        literals = re.findall(r"[\"'`]([^\"'`\n]+?\.[A-Za-z0-9]+(?:#[^\"'`\n]*)?)[\"'`]", plain)
        # YAML values and shell arguments need not be quoted. Resolve their
        # relative tokens from both the repository and the consumer directory.
        literals += re.findall(r"[^\s\"'`<>:=;,|()\[\]{}]+", plain)
        for target in {value for literal in literals for value in prose_targets(literal)}:
            value = urlsplit(target)
            if value.scheme or not value.path:
                continue
            path = unquote(value.path.replace("\\", "/"))
            for base in (root, file.parent):
                destination = (base / path).resolve()
                if destination in removed:
                    referenced.add(removed[destination])
        errors.extend(
            f"Inbound reference to retired document {path} in {name}" for path in sorted(referenced)
        )
    return errors


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
        for target in markdown_targets(text):
            value = markdown_url(target)
            if value.scheme or not value.path:
                continue
            resolved = (file.parent / unquote(value.path)).resolve()
            if not resolved.is_relative_to(root.resolve()) or not resolved.exists():
                errors.append(f"Broken/outside local reference in {path}: {target}")
    return errors + inbound_references(root, paths)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", required=True)
    parser.add_argument("--head", default="HEAD", help="PR head, not GitHub's synthetic merge commit")
    parser.add_argument("--summary-file", type=Path)
    parser.add_argument("--list", action="store_true")
    args = parser.parse_args(argv)
    root = Path(__file__).resolve().parents[1]
    paths = changed_documents(root, args.base, args.head)
    if args.list:
        print(json.dumps(paths, indent=2))
        return 0
    summary = args.summary_file.read_text() if args.summary_file else os.getenv("DOC_LIFECYCLE_SUMMARY", "")
    errors = validate_dispositions(root, paths, summary)
    print(json.dumps({"documents": len(paths), "errors": errors}, ensure_ascii=False, indent=2))
    return bool(errors)


if __name__ == "__main__":
    raise SystemExit(main())
