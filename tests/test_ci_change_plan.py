"""Real Git histories exercise the informational selector's fail-closed policy."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

from scripts import ci_change_plan as planner


def git(repo, *arguments):
    return subprocess.check_output(["git", "-C", str(repo), *arguments], text=True).strip()


def commit(repo, message="change"):
    git(repo, "add", "-A")
    git(repo, "-c", "user.name=CI Fixture", "-c", "user.email=ci@example.invalid", "commit", "-qm", message)
    return git(repo, "rev-parse", "HEAD")


def write(repo, name, content="new contents\n"):
    path = repo / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


@pytest.fixture
def repository(tmp_path):
    repo = tmp_path / "repository"
    repo.mkdir()
    git(repo, "init", "-q")
    write(repo, "README.md", "original documentation\n")
    return repo, commit(repo, "initial")


def assert_full_execution(plan):
    assert plan["shadow_only"] is True
    assert plan["plan_is_execution_receipt"] is False
    assert plan["actual_execution"] == "full"
    assert plan["actual_groups"] == list(planner.FULL_GROUPS)


@pytest.mark.parametrize(
    "name,scope,groups",
    [
        ("README.md", "docs_only", ["lifecycle", "baseline_checks"]),
        ("docs/guide.md", "docs_only", ["lifecycle", "baseline_checks"]),
        ("web/src/main.ts", "web_only", ["web", "browser"]),
        ("web/index.html", "web_only", ["web", "browser"]),
    ],
)
def test_narrow_recommendation_never_changes_actual_execution(repository, name, scope, groups):
    repo, base = repository
    write(repo, name)
    head = commit(repo)
    plan = planner.build_plan(repo, base, head)
    assert_full_execution(plan)
    assert plan["recommended_execution"] == scope
    assert plan["recommended_groups"] == groups
    assert plan["base_sha"] == base and plan["head_sha"] == plan["checkout_sha"] == head
    assert plan["history_verified"] is True
    assert plan["changed_paths"] == [name]
    assert len(plan["diff_sha256"]) == 64
    assert plan == planner.build_plan(repo, base, head)


@pytest.mark.parametrize(
    "name",
    [
        "src/shared.py",
        "scripts/check.py",
        "tests/test_example.py",
        "conftest.py",
        "web/src/main.test.ts",
        "web/src/__tests__/main.ts",
        "web/tests/smoke.ts",
        "contracts/web/schema.json",
        "config/runtime.json",
        "data/gold/facts.parquet",
        "site/index.html",
        "pyproject.toml",
        "uv.lock",
        "web/package-lock.json",
        ".github/workflows/ci.yml",
        "Dockerfile.chat",
        ".dockerignore",
        "AGENTS.md",
        "docs/referencias/source.json",
        "unrecognized.file",
    ],
)
def test_shared_test_dependency_and_unknown_paths_recommend_full(repository, name):
    repo, base = repository
    write(repo, name)
    plan = planner.build_plan(repo, base, commit(repo))
    assert_full_execution(plan)
    assert plan["recommended_execution"] == "full"
    assert plan["recommended_groups"] == list(planner.FULL_GROUPS)
    assert plan["reason"] == "shared_unknown_or_mixed_paths"


def test_mixed_docs_and_web_recommend_full(repository):
    repo, base = repository
    write(repo, "docs/guide.md")
    write(repo, "web/src/main.ts")
    plan = planner.build_plan(repo, base, commit(repo))
    assert_full_execution(plan)
    assert plan["recommended_execution"] == "full"


def test_cross_boundary_rename_retains_old_and_new_paths(repository):
    repo, _ = repository
    write(repo, "scripts/producer.py", "print('retained source')\n" * 30)
    base = commit(repo)
    (repo / "docs").mkdir()
    git(repo, "mv", "scripts/producer.py", "docs/producer.md")
    plan = planner.build_plan(repo, base, commit(repo))
    assert_full_execution(plan)
    assert plan["recommended_execution"] == "full"
    assert plan["changed_paths"] == ["docs/producer.md", "scripts/producer.py"]
    assert plan["changes"] == [{"status": "R100", "paths": ["scripts/producer.py", "docs/producer.md"]}]


def test_documentation_delete_still_recommends_full(repository):
    repo, base = repository
    (repo / "README.md").unlink()
    plan = planner.build_plan(repo, base, commit(repo))
    assert_full_execution(plan)
    assert plan["recommended_execution"] == "full"
    assert plan["changes"] == [{"status": "D", "paths": ["README.md"]}]


def test_empty_diff_is_not_a_skip_receipt(repository):
    repo, head = repository
    plan = planner.build_plan(repo, head, head)
    assert_full_execution(plan)
    assert plan["recommended_execution"] == "full"
    assert plan["reason"] == "empty_diff_keeps_full_execution"


@pytest.mark.parametrize(
    "base,head", [("", ""), ("master", "HEAD"), ("f" * 40, "invalid"), ("-evil", "a" * 40)]
)
def test_empty_symbolic_or_malformed_refs_keep_full(repository, base, head):
    repo, _ = repository
    plan = planner.build_plan(repo, base, head)
    assert_full_execution(plan)
    assert plan["recommended_execution"] == "full"
    assert plan["reason"] == "invalid_or_missing_commit_sha"


def test_missing_commit_object_keeps_full(repository):
    repo, head = repository
    plan = planner.build_plan(repo, "0" * 40, head)
    assert_full_execution(plan)
    assert plan["recommended_execution"] == "full"
    assert plan["reason"] == "git_history_unavailable"


def test_non_ancestor_base_keeps_full(repository):
    repo, common = repository
    write(repo, "docs/first.md")
    first = commit(repo)
    git(repo, "switch", "-qc", "sibling", common)
    write(repo, "docs/sibling.md")
    head = commit(repo)
    plan = planner.build_plan(repo, first, head)
    assert_full_execution(plan)
    assert plan["reason"] == "base_not_verified_ancestor"


def test_head_must_be_the_tested_checkout(repository):
    repo, base = repository
    write(repo, "docs/new.md")
    commit(repo)
    plan = planner.build_plan(repo, base, base)
    assert_full_execution(plan)
    assert plan["reason"] == "head_differs_from_checkout"


def test_shallow_history_keeps_full(repository, tmp_path):
    repo, base = repository
    write(repo, "docs/new.md")
    head = commit(repo)
    clone = tmp_path / "shallow"
    subprocess.run(["git", "clone", "-q", "--depth=1", repo.as_uri(), str(clone)], check=True)
    # Both refs can be supplied and available, but incomplete history remains uncertain.
    plan = planner.build_plan(clone, head, head)
    assert_full_execution(plan)
    assert plan["reason"] == "incomplete_git_history"


def test_missing_git_keeps_full(repository, monkeypatch):
    repo, head = repository
    monkeypatch.setenv("PATH", "")
    plan = planner.build_plan(repo, head, head)
    assert_full_execution(plan)
    assert plan["reason"] == "git_or_checkout_unavailable"


def test_ambient_git_override_cannot_change_the_requested_repo(repository, tmp_path, monkeypatch):
    repo, base = repository
    write(repo, "docs/new.md")
    head = commit(repo)
    monkeypatch.setenv("GIT_DIR", str(tmp_path / "not-a-repository"))
    monkeypatch.setenv("GIT_WORK_TREE", str(tmp_path))
    plan = planner.build_plan(repo, base, head)
    assert_full_execution(plan)
    assert plan["recommended_execution"] == "docs_only"


def test_subdirectory_and_relative_diff_configuration_cannot_hide_shared_changes(repository):
    repo, base = repository
    write(repo, "web/src/main.ts")
    write(repo, "src/shared.py")
    head = commit(repo)
    git(repo, "config", "diff.relative", "true")
    plan = planner.build_plan(repo / "web", base, head)
    assert_full_execution(plan)
    assert plan["recommended_execution"] == "full"
    assert plan["changed_paths"] == ["src/shared.py", "web/src/main.ts"]


def test_planning_does_not_modify_checkout_or_untracked_state(repository):
    repo, base = repository
    write(repo, "docs/guide.md")
    head = commit(repo)
    write(repo, "local-only.txt", "untracked state must survive\n")
    before = git(repo, "status", "--porcelain=v1", "-z")
    planner.build_plan(repo, base, head)
    assert git(repo, "rev-parse", "HEAD") == head
    assert git(repo, "status", "--porcelain=v1", "-z") == before
    assert (repo / "local-only.txt").read_text() == "untracked state must survive\n"


def test_diff_parse_failure_returns_full_report(repository, monkeypatch):
    repo, base = repository
    write(repo, "docs/guide.md")
    head = commit(repo)

    def invalid(_raw):
        raise planner.PlanInputError("malformed_diff")

    monkeypatch.setattr(planner, "parse_diff", invalid)
    plan = planner.build_plan(repo, base, head)
    assert_full_execution(plan)
    assert plan["recommended_execution"] == "full"
    assert plan["reason"] == "malformed_diff"


def test_git_timeout_returns_full_report(repository, monkeypatch):
    repo, head = repository

    def timeout(*_args, **_kwargs):
        raise subprocess.TimeoutExpired("git", 30)

    monkeypatch.setattr(planner, "_git", timeout)
    plan = planner.build_plan(repo, head, head)
    assert_full_execution(plan)
    assert plan["recommended_execution"] == "full"
    assert plan["reason"] == "git_query_timed_out"


def test_copy_parser_retains_both_paths_for_conservative_classification():
    assert planner.parse_diff(b"C100\0src/shared.py\0docs/source.md\0") == [
        {"status": "C100", "paths": ["src/shared.py", "docs/source.md"]}
    ]


@pytest.mark.parametrize(
    "raw",
    [b"M\0docs/a.md", b"R100\0docs/a.md\0", b"M\0../docs/a.md\0", b"M\0docs/a\nb.md\0", b"M\0docs/\xff.md\0"],
)
def test_malformed_or_unsafe_diff_cannot_create_a_narrow_recommendation(raw):
    with pytest.raises(planner.PlanInputError):
        planner.parse_diff(raw)


def test_cli_writes_json_even_with_missing_refs(repository, tmp_path):
    repo, _ = repository
    output = tmp_path / "results" / "plan.json"
    script = Path(planner.__file__)
    completed = subprocess.run(
        [sys.executable, str(script), "--repo", str(repo), "--output", str(output)],
        capture_output=True,
        text=True,
        check=True,
    )
    plan = json.loads(completed.stdout)
    assert json.loads(output.read_text()) == plan
    assert_full_execution(plan)


def test_cli_output_failure_is_not_silently_successful(repository, tmp_path, capsys):
    repo, head = repository
    blocked = tmp_path / "regular-file"
    blocked.write_text("preserve me")
    result = planner.main(
        ["--repo", str(repo), "--base", head, "--head", head, "--output", str(blocked / "plan.json")]
    )
    assert result == 1
    assert "cannot write CI shadow plan" in capsys.readouterr().err
    assert blocked.read_text() == "preserve me"
