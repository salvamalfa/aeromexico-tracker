"""Plan conservative committed-tree CI selection, with an explicit PR opt-in.

The report is never an execution receipt. By default, recommendations retain
the full execution policy in shadow mode. Opt-in selection permits only a
bounded allowlist on pull requests. Missing or uncertain input retains full CI.
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
    "ci_controls",
    "pages_preflight",
    "docker_preflight",
    "public_tests",
    "chat_runtime",
    "web",
    "browser",
)
DOCS_GROUPS = ("lifecycle", "lint", "ci_controls", "pages_preflight")
WEB_GROUPS = (*DOCS_GROUPS, "web", "browser")
SHA = re.compile(r"[a-f0-9]{40}\Z")
ROOT_DOCS = {"README.md", "REPO_MAP.md", "ROADMAP.md", "CHANGELOG.md"}
WEB_SUFFIXES = {".ts", ".tsx", ".css", ".html"}
ACTIVE_WEB_SUFFIXES = {".ts", ".tsx", ".css"}
TEST_DIRECTORIES = {"test", "tests", "spec", "specs", "__tests__", "__specs__"}


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
        or TEST_DIRECTORIES.intersection(path.parts)
        or path.name == "conftest.py"
        or path.name.startswith("Dockerfile")
        or re.search(r"(?:^|[._-])(?:test|spec)(?:[._-]|$)", path.name)
        or name in {"pyproject.toml", "uv.lock", ".dockerignore", "AGENTS.md"}
    ):
        return "shared"
    if name in ROOT_DOCS or (name.startswith("docs/") and path.suffix == ".md"):
        return "docs"
    if name == "web/index.html" or (name.startswith("web/src/") and path.suffix in WEB_SUFFIXES):
        return "web"
    return "unknown"


def _active_path(name: str, category: str) -> bool:
    # Markdown under docs/ can be a machine-read prompt, evidence or Gold
    # input. The initial rollout allows only these canonical root documents.
    if category == "docs":
        return name in ROOT_DOCS
    if category == "web":
        return name == "web/index.html" or (
            name.startswith("web/src/")
            and not name.startswith("web/src/types/generated/")
            and Path(name).suffix in ACTIVE_WEB_SUFFIXES
        )
    return False


def _require_regular_files(repo: Path, commit: str, names: set[str]) -> None:
    """Verify committed modes without following checkout symlinks or pathspecs."""
    if not names:
        return
    wanted = {name.encode("utf-8") for name in names}
    # --full-tree avoids subdirectory-relative queries. Reading literal tree
    # entries also avoids interpreting a filename as a Git pathspec.
    raw = _git(repo, "ls-tree", "--full-tree", "-r", "-z", commit).stdout
    if not raw.endswith(b"\0"):
        raise PlanInputError("malformed_tree_modes")
    seen = set()
    for entry in raw.split(b"\0")[:-1]:
        metadata, separator, name = entry.partition(b"\t")
        if not separator:
            raise PlanInputError("malformed_tree_modes")
        if name in wanted:
            fields = metadata.split(b" ")
            if len(fields) != 3 or fields[:2] != [b"100644", b"blob"]:
                raise PlanInputError("non_regular_file_mode")
            seen.add(name)
    if seen != wanted:
        raise PlanInputError("changed_path_missing_from_tree")


def build_plan(
    repo: Path, base: str, head: str, *, event: str = "", enable_selection: bool = False
) -> dict:
    """Return a deterministic report; an input failure never narrows CI."""
    plan = {
        "schema_version": "ci_change_plan_v1",
        "shadow_only": not enable_selection,
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
            _require_regular_files(repo, head, set(plan["changed_paths"]))
            _require_regular_files(
                repo, base, {change["paths"][0] for change in changes if change["status"] == "M"}
            )
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
            if enable_selection:
                if event != "pull_request":
                    plan["reason"] = "event_requires_full_execution"
                elif categories in ({"docs"}, {"web"}):
                    category = next(iter(categories))
                    if all(_active_path(name, category) for name in plan["changed_paths"]):
                        groups = DOCS_GROUPS if category == "docs" else WEB_GROUPS
                        plan.update(
                            actual_execution=f"{category}_only",
                            actual_groups=list(groups),
                            reason=f"{category}_only_selection_enabled",
                        )
                    else:
                        plan["reason"] = "outside_active_allowlist"
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
    parser.add_argument("--event", default="")
    parser.add_argument("--enable-selection", action="store_true")
    parser.add_argument("--github-output", type=Path)
    arguments = parser.parse_args(argv)
    plan = build_plan(
        arguments.repo, arguments.base, arguments.head,
        event=arguments.event, enable_selection=arguments.enable_selection,
    )
    report = json.dumps(plan, indent=2, sort_keys=True)
    try:
        if arguments.output is not None:
            arguments.output.parent.mkdir(parents=True, exist_ok=True)
            arguments.output.write_text(report + "\n", encoding="utf-8")
        if arguments.github_output is not None:
            # Only these fixed literals may enter GitHub's output protocol.
            output = {
                "full": "execution=full\n",
                "docs_only": "execution=docs_only\n",
                "web_only": "execution=web_only\n",
            }[plan["actual_execution"]]
            with arguments.github_output.open("a", encoding="utf-8") as stream:
                stream.write(output)
        print(report)
    except OSError as exc:
        print(f"cannot write CI shadow plan or execution output: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
