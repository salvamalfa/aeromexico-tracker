"""Inventory task files, require dispositions and check documentation references."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import unicodedata
from pathlib import Path
from urllib.parse import unquote, urlsplit

DISPOSITIONS = {"keep", "update", "consolidate", "archive", "retire", "delete_candidate", "pending"}
BLOCK = re.compile(r"<!--\s*document-lifecycle:v1\s*(\{.*?\})\s*-->", re.S)
# Directory groups are for repetitive generated/data evidence, never source code
# or canonical Markdown. Each group is expanded against this task's Git diff.
GROUP_ROOTS = ("site/", "data/gold/", "docs/referencias/", "prototypes/", "review/", "derived/", "snapshot/")
ARTIFACT_SUFFIXES = {
    ".json",
    ".jsonl",
    ".csv",
    ".tsv",
    ".html",
    ".parquet",
    ".duckdb",
    ".sqlite",
    ".pkl",
    ".png",
    ".gif",
    ".jpg",
    ".jpeg",
    ".webp",
    ".svg",
    ".pdf",
    ".zip",
    ".gz",
    ".xml",
    ".txt",
    ".log",
    ".xlsx",
    ".xls",
}


def groupable_artifact(path: str) -> bool:
    suffix = Path(path).suffix.lower()
    return suffix in ARTIFACT_SUFFIXES or (path.startswith("site/assets/") and suffix in {".js", ".css"})


def changed_files(root: Path, base: str, head: str = "HEAD", worktree: bool = False) -> list[str]:
    if worktree and head != "HEAD":
        raise ValueError("--worktree requires --head HEAD")
    comparison = (
        subprocess.check_output(["git", "merge-base", base, head], cwd=root).decode().strip()
        if worktree
        else f"{base}...{head}"
    )
    changed = (
        subprocess.check_output(
            ["git", "diff", "--no-renames", "--name-only", "-z", comparison, "--"], cwd=root
        )
        .decode()
        .split("\0")
    )
    if worktree:
        changed += (
            subprocess.check_output(["git", "ls-files", "--others", "--exclude-standard", "-z"], cwd=root)
            .decode()
            .split("\0")
        )
    return sorted(set(changed) - {""})


def changed_documents(root: Path, base: str, head: str = "HEAD") -> list[str]:
    # Compatibility helper for callers interested only in the old document scope.
    changed = changed_files(root, base, head)
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
    targets = []
    for match in re.finditer(r"\]\(", text):
        depth, angle, escaped = 1, False, False
        for index in range(match.end(), len(text)):
            char = text[index]
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == "<":
                angle = True
            elif char == ">":
                angle = False
            elif not angle:
                if char == "(":
                    depth += 1
                elif char == ")":
                    depth -= 1
                    if depth == 0:
                        targets.append(text[match.end() : index])
                        break
    return targets + re.findall(r"(?m)^\s{0,3}\[[^\]]+\]:\s*(.+)", text)


def markdown_url(target: str):
    target = target.strip()
    if target.startswith("<") and ">" in target:
        target = target[1 : target.index(">")]
    else:
        target = target.split(maxsplit=1)[0] if target else ""
    return urlsplit(re.sub(r"\\([()<>])", r"\1", target))


def repository_name(root: Path) -> str:
    remote = subprocess.run(
        ["git", "config", "--get", "remote.origin.url"], cwd=root, capture_output=True, text=True
    ).stdout.strip()
    if remote.startswith("git@github.com:"):
        path = remote.removeprefix("git@github.com:")
    else:
        try:
            value = urlsplit(remote)
            path = value.path.lstrip("/") if value.hostname in {"github.com", "ssh.github.com"} else ""
        except ValueError:
            path = ""
    match = re.fullmatch(r"([^/]+/[^/]+?)(?:\.git)?/?", path)
    return match[1] if match else os.getenv("GITHUB_REPOSITORY", "salvamalfa/aeromexico-tracker")


def mutable_repo_document(value, root: Path, repository: str | None = None) -> Path | None:
    repository = repository or repository_name(root)
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
    while trimmed and trimmed[-1] not in "/\\" and unicodedata.category(trimmed[-1]).startswith("P"):
        trimmed = trimmed[:-1]
    return (target, trimmed) if trimmed and trimmed != target else (target,)


def inbound_references(root: Path, paths: list[str]) -> list[str]:
    """Inspect literal consumers of retired files without resolving unrelated data."""
    removed = {(root / path).resolve(): path for path in paths if not (root / path).exists()}
    if not removed:
        return []
    basenames = {Path(path).name for path in removed.values()}

    def candidate(text: str) -> bool:
        # Every supported literal reference retains the destination's filename,
        # including percent-encoded Markdown/URLs. Dynamic paths need manual review.
        decoded = unquote(re.sub(r"\\([()<>])", r"\1", text))
        return any(name in decoded for name in basenames)

    tracked = set(subprocess.check_output(["git", "ls-files", "-z"], cwd=root).decode().split("\0"))
    # --worktree inventories new consumers before git add as well.
    tracked.update(paths)
    repository = repository_name(root)
    errors = []
    for name in sorted(tracked):
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
        if not candidate(text):
            continue
        referenced = set()
        for target in markdown_targets(text):
            try:
                value = markdown_url(target)
            except ValueError:
                if file.suffix == ".md":
                    errors.append(f"Malformed Markdown target in {name}: {target}")
                continue
            if value.scheme or value.netloc:
                destination = mutable_repo_document(value, root, repository)
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
                try:
                    destination = mutable_repo_document(urlsplit(target), root, repository)
                except ValueError:
                    # Python f-strings (e.g. server_address[1]) are not URLs
                    # until runtime. Continue checking literal paths below.
                    continue
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
        for target in {
            value for literal in literals if candidate(literal) for value in prose_targets(literal)
        }:
            try:
                value = urlsplit(target)
            except ValueError:
                continue  # Dynamic source-code tokens are not concrete URLs.
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


def disposition_records(paths: list[str], summary: str) -> tuple[dict, list[str]]:
    blocks = BLOCK.findall(summary)
    if len(blocks) != 1:
        return {}, ["Task files changed: include exactly one document-lifecycle:v1 block in the summary"]
    try:
        entries = json.loads(blocks[0])["files"]
        if not isinstance(entries, list) or any(not isinstance(row, dict) for row in entries):
            raise ValueError
        records, errors = {}, []
        for row in entries:
            if ("path" in row) == ("prefix" in row):
                raise ValueError
            if "path" in row:
                targets = [row["path"]]
                if not isinstance(targets[0], str):
                    raise ValueError
            else:
                prefix = row["prefix"]
                if (
                    not isinstance(prefix, str)
                    or not prefix.endswith("/")
                    or not prefix.startswith(GROUP_ROOTS)
                    or any(part in {"", ".", ".."} for part in prefix[:-1].split("/"))
                ):
                    raise ValueError
                targets = [path for path in paths if path.startswith(prefix)]
                if type(row.get("count")) is not int or row["count"] != len(targets) or not targets:
                    errors.append(f"Group count mismatch/empty: {prefix}")
                if any(not groupable_artifact(path) for path in targets):
                    errors.append(f"Group requires individual source/Markdown entries: {prefix}")
            for path in targets:
                if path in records:
                    errors.append(f"Duplicate/overlapping lifecycle path: {path}")
                records[path] = row
        return records, errors
    except (ValueError, KeyError, TypeError):
        return {}, ["Invalid document-lifecycle:v1 JSON or file/group entry"]


def validate_dispositions(root: Path, paths: list[str], summary: str) -> list[str]:
    if not paths:
        return []
    records, errors = disposition_records(paths, summary)
    if errors:
        return errors
    repository = repository_name(root)
    for path in paths:
        row = records.get(path, {})
        reason = row.get("reason")
        disposition = row.get("disposition")
        if (
            not isinstance(disposition, str)
            or disposition not in DISPOSITIONS
            or not isinstance(reason, str)
            or not reason.strip()
        ):
            errors.append(f"Missing disposition/reason: {path}")
        file = root / path
        if not file.exists() and disposition not in ("archive", "retire"):
            errors.append(f"Removed file requires archive/retire disposition: {path}")
        if file.exists() and disposition in ("archive", "retire"):
            errors.append(f"Archive/retire disposition requires an absent original path: {path}")
        if file.suffix != ".md" or not file.is_file():
            continue
        text = re.sub(r"```.*?```", "", file.read_text(encoding="utf-8"), flags=re.S)
        for target in markdown_targets(text):
            try:
                value = markdown_url(target)
            except ValueError:
                errors.append(f"Malformed Markdown target in {path}: {target}")
                continue
            if value.scheme or value.netloc:
                resolved = mutable_repo_document(value, root, repository)
                if resolved is None:
                    continue
            elif value.path:
                local_path = unquote(value.path)
                resolved = (
                    root / local_path.lstrip("/") if local_path.startswith("/") else file.parent / local_path
                ).resolve()
            else:
                continue
            if not resolved.is_relative_to(root.resolve()) or not resolved.exists():
                errors.append(f"Broken/outside local reference in {path}: {target}")
    return errors + inbound_references(root, paths)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", required=True)
    parser.add_argument("--head", default="HEAD", help="PR head, not GitHub's synthetic merge commit")
    parser.add_argument("--summary-file", type=Path)
    parser.add_argument("--list", action="store_true")
    parser.add_argument("--root", type=Path, help="Checkout to audit, including the private repository")
    parser.add_argument(
        "--worktree", action="store_true", help="Include staged, unstaged and untracked files"
    )
    args = parser.parse_args(argv)
    root = (args.root or Path(__file__).resolve().parents[1]).resolve()
    if args.worktree and args.head != "HEAD":
        parser.error("--worktree requires --head HEAD")
    paths = changed_files(root, args.base, args.head, args.worktree)
    if args.list:
        print(json.dumps(paths, indent=2))
        return 0
    summary = args.summary_file.read_text() if args.summary_file else os.getenv("DOC_LIFECYCLE_SUMMARY", "")
    errors = validate_dispositions(root, paths, summary)
    records, _ = disposition_records(paths, summary) if paths else ({}, [])
    pending = [
        path for path in paths if records.get(path, {}).get("disposition") in ("pending", "delete_candidate")
    ]
    lfs_markdown = [
        path
        for path in paths
        if Path(path).suffix == ".md"
        and (root / path).is_file()
        and (root / path).read_bytes().startswith(b"version https://git-lfs.github.com/spec/v1\n")
    ]
    print(
        json.dumps(
            {
                "files": len(paths),
                "pending": pending,
                "unverified_lfs_markdown": lfs_markdown,
                "errors": errors,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return bool(errors)


if __name__ == "__main__":
    raise SystemExit(main())
