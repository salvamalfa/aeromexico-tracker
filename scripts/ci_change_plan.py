"""Describe a conservative committed-tree CI selection without enabling it.

The report is diagnostic, never an execution receipt or a source of job
conditions. Every recommendation retains the full execution policy while the
selector is in shadow mode. Missing or uncertain Git input recommends full CI.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path

FULL_GROUPS = (
    "lifecycle",
    "lint",
    "pages_preflight",
    "docker_preflight",
    "public_tests",
    "chat_runtime",
    "web",
    "browser",
)
SHA = re.compile(r"[a-f0-9]{40}\Z")
ROOT_DOCS = {"README.md", "REPO_MAP.md", "ROADMAP.md", "CHANGELOG.md"}
WEB_SUFFIXES = {".ts", ".tsx", ".css", ".html"}


class PlanInputError(ValueError):
    """An uncertainty that must retain the complete execution policy."""


def _git(repo: Path, *arguments: str, check: bool = True) -> subprocess.CompletedProcess:
    # Ambient Git overrides must not redirect the explicit checkout or replace
    # the committed history. No command fetches objects or executes a shell.
    environment = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
    environment.update(
        GIT_CONFIG_GLOBAL=os.devnull,
        GIT_CONFIG_NOSYSTEM="1",
        GIT_TERMINAL_PROMPT="0",
        GIT_OPTIONAL_LOCKS="0",
        LC_ALL="C",
    )
    return subprocess.run(
        ["git", "--no-replace-objects", "-C", str(repo), *arguments],
        env=environment,
        capture_output=True,
        check=check,
        timeout=30,
    )


def _path(raw: bytes) -> str:
    try:
        value = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise PlanInputError("invalid_path_encoding") from exc
    if (
        not value
        or value.startswith("/")
        or "\\" in value
        or any(part in {"", ".", ".."} for part in value.split("/"))
        or any(ord(character) < 32 or ord(character) == 127 for character in value)
    ):
        raise PlanInputError("unsafe_or_ambiguous_path")
    return value


def parse_diff(raw: bytes) -> list[dict]:
    """Read NUL-delimited statuses and retain both sides of copies/renames."""
    if not raw:
        return []
    if not raw.endswith(b"\0"):
        raise PlanInputError("malformed_diff")
    fields = raw.split(b"\0")[:-1]
    changes = []
    position = 0
    while position < len(fields):
        try:
            status = fields[position].decode("ascii")
        except UnicodeDecodeError as exc:
            raise PlanInputError("malformed_diff_status") from exc
        position += 1
        if re.fullmatch(r"[RC](?:100|[1-9]?[0-9])", status):
            count = 2
        elif status in {"A", "M", "D", "T", "U", "X", "B"}:
            count = 1
        else:
            raise PlanInputError("malformed_diff_status")
        if position + count > len(fields):
            raise PlanInputError("malformed_diff")
        paths = [_path(value) for value in fields[position : position + count]]
        changes.append({"status": status, "paths": paths})
        position += count
    return sorted(changes, key=lambda item: (item["paths"], item["status"]))


def _category(name: str) -> str:
    path = Path(name)
    if (
        name.startswith(("tests/", "scripts/", "src/", "contracts/", "config/", "data/", "site/", ".github/"))
        or "tests" in path.parts
        or "__tests__" in path.parts
        or path.name == "conftest.py"
        or path.name.startswith(("test_", "spec_", "Dockerfile"))
        or re.search(r"\.(test|spec)\.[^/]+$", path.name)
        or name in {"pyproject.toml", "uv.lock", ".dockerignore", "AGENTS.md"}
    ):
        return "shared"
    if name in ROOT_DOCS or (name.startswith("docs/") and path.suffix == ".md"):
        return "docs"
    if name == "web/index.html" or (name.startswith("web/src/") and path.suffix in WEB_SUFFIXES):
        return "web"
    return "unknown"


def build_plan(repo: Path, base: str, head: str) -> dict:
    """Return a deterministic report; an input failure never narrows CI."""
    plan = {
        "schema_version": "ci_change_plan_v1",
        "shadow_only": True,
        "plan_is_execution_receipt": False,
        "base_sha": base if SHA.fullmatch(base) else None,
        "head_sha": head if SHA.fullmatch(head) else None,
        "checkout_sha": None,
        "history_verified": False,
        "diff_sha256": None,
        "changes": [],
        "changed_paths": [],
        "recommended_execution": "full",
        "recommended_groups": list(FULL_GROUPS),
        "actual_execution": "full",
        "actual_groups": list(FULL_GROUPS),
        "reason": "invalid_or_missing_commit_sha",
    }
    if plan["base_sha"] is None or plan["head_sha"] is None:
        return plan
    try:
        for commit in (base, head):
            if _git(repo, "cat-file", "-t", commit).stdout.strip() != b"commit":
                raise PlanInputError("commit_object_required")
        checkout = _git(repo, "rev-parse", "--verify", "HEAD").stdout.decode("ascii").strip()
        plan["checkout_sha"] = checkout
        if checkout != head:
            raise PlanInputError("head_differs_from_checkout")
        if _git(repo, "rev-parse", "--is-shallow-repository").stdout.strip() != b"false":
            raise PlanInputError("incomplete_git_history")
        if _git(repo, "merge-base", "--is-ancestor", base, head, check=False).returncode != 0:
            raise PlanInputError("base_not_verified_ancestor")
        raw = _git(
            repo,
            "diff",
            "--no-ext-diff",
            "--no-textconv",
            "--no-relative",
            "--ignore-submodules=none",
            "--find-renames",
            "--name-status",
            "-z",
            base,
            head,
            "--",
        ).stdout
        plan["diff_sha256"] = hashlib.sha256(raw).hexdigest()
        changes = parse_diff(raw)
        plan.update(
            history_verified=True,
            changes=changes,
            changed_paths=sorted({name for change in changes for name in change["paths"]}),
        )
        if not changes:
            plan["reason"] = "empty_diff_keeps_full_execution"
        elif any(change["status"] not in {"A", "M"} for change in changes):
            plan["reason"] = "rename_delete_copy_or_type_change"
        else:
            categories = {_category(name) for name in plan["changed_paths"]}
            if categories == {"docs"}:
                plan.update(
                    recommended_execution="docs_only",
                    recommended_groups=["lifecycle", "baseline_checks"],
                    reason="documentation_text_only_shadow_recommendation",
                )
            elif categories == {"web"}:
                plan.update(
                    recommended_execution="web_only",
                    recommended_groups=["web", "browser"],
                    reason="web_source_only_shadow_recommendation",
                )
            else:
                plan["reason"] = "shared_unknown_or_mixed_paths"
    except PlanInputError as exc:
        plan["reason"] = str(exc)
    except FileNotFoundError:
        plan["reason"] = "git_or_checkout_unavailable"
    except subprocess.TimeoutExpired:
        plan["reason"] = "git_query_timed_out"
    except (subprocess.CalledProcessError, OSError, UnicodeError):
        plan["reason"] = "git_history_unavailable"
    return plan


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    parser.add_argument("--base", default="")
    parser.add_argument("--head", default="")
    parser.add_argument("--output", type=Path)
    arguments = parser.parse_args(argv)
    report = json.dumps(build_plan(arguments.repo, arguments.base, arguments.head), indent=2, sort_keys=True)
    try:
        if arguments.output is not None:
            arguments.output.parent.mkdir(parents=True, exist_ok=True)
            arguments.output.write_text(report + "\n", encoding="utf-8")
        print(report)
    except OSError as exc:
        print(f"cannot write CI shadow plan: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
