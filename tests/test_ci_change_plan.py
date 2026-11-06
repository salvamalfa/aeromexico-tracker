"""Real Git histories exercise shadow and opt-in selection's fail-closed policy."""

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


def assert_full_execution(plan, *, shadow_only=True):
    assert plan["shadow_only"] is shadow_only
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
        "src/shared.py", "scripts/check.py", "tests/test_example.py", "conftest.py",
        "web/tests/smoke.ts", "web/tests/main.ts", "contracts/web/schema.json", "config/runtime.json",
        "data/gold/facts.parquet", "site/index.html", "pyproject.toml", "uv.lock",
        "web/package.json", "web/package-lock.json", "web/vite.config.ts", ".github/workflows/ci.yml",
        "Dockerfile.chat", ".dockerignore", "AGENTS.md", "docs/referencias/source.json", "unrecognized.file",
        "web/src/types/generated.json", "web/src/main.js",
    ] + [f"web/src/{directory}/main.ts" for directory in ("test", "tests", "spec", "specs", "__tests__", "__specs__")]
    + [f"web/src/{name}" for name in (
        "main.test.ts", "main-test.ts", "main_test.ts", "main.spec.ts", "main-spec.ts", "main_spec.ts",
        "test.ts", "spec.ts", "test_component.tsx", "component_spec.css",
    )],
)
@pytest.mark.parametrize("enable_selection", [False, True])
def test_shared_test_dependency_and_unknown_paths_recommend_full(repository, name, enable_selection):
    repo, base = repository
    write(repo, name)
    plan = planner.build_plan(repo, base, commit(repo), event="pull_request", enable_selection=enable_selection)
    assert_full_execution(plan, shadow_only=not enable_selection)
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


def active_plan(repo, base, head, *, event="pull_request"):
    return planner.build_plan(repo, base, head, event=event, enable_selection=True)


@pytest.mark.parametrize(
    "name,scope,groups",
    [
        ("README.md", "docs_only", planner.DOCS_GROUPS),
        ("REPO_MAP.md", "docs_only", planner.DOCS_GROUPS),
        ("ROADMAP.md", "docs_only", planner.DOCS_GROUPS),
        ("CHANGELOG.md", "docs_only", planner.DOCS_GROUPS),
        ("web/index.html", "web_only", planner.WEB_GROUPS),
        ("web/src/main.ts", "web_only", planner.WEB_GROUPS),
        ("web/src/component.tsx", "web_only", planner.WEB_GROUPS),
        ("web/src/style.css", "web_only", planner.WEB_GROUPS),
    ],
)
def test_opt_in_pr_activates_only_bounded_profiles(repository, name, scope, groups):
    repo, base = repository
    write(repo, name)
    head = commit(repo)
    plan = active_plan(repo, base, head)
    assert plan["shadow_only"] is False
    assert plan["plan_is_execution_receipt"] is False
    assert plan["actual_execution"] == scope
    assert plan["actual_groups"] == list(groups)
    assert set(planner.DOCS_GROUPS) <= set(groups)
    assert plan["history_verified"] is True
    assert plan == active_plan(repo, base, head)


@pytest.mark.parametrize("event", ["", "push", "workflow_call", "workflow_dispatch", "pull_request_target", "unknown"])
@pytest.mark.parametrize("name", ["README.md", "web/src/main.ts"])
def test_every_event_except_explicit_pull_request_keeps_full(repository, event, name):
    repo, base = repository
    write(repo, name)
    plan = active_plan(repo, base, commit(repo), event=event)
    assert_full_execution(plan, shadow_only=False)
    assert plan["reason"] == "event_requires_full_execution"


def test_event_without_opt_in_stays_shadow(repository):
    repo, base = repository
    write(repo, "README.md")
    plan = planner.build_plan(repo, base, commit(repo), event="pull_request")
    assert_full_execution(plan)
    assert plan["recommended_execution"] == "docs_only"


@pytest.mark.parametrize(
    "name",
    [
        "docs/guide.md",
        "docs/glosario-kpis.md",
        "docs/chat/revision-fase-2/F2.1-prompt-aprobado.md",
        "docs/analysis-agent/narrativa-trimestral.md",
        "web/src/types/generated/flights.ts",
        "web/src/templates/index.html",
    ],
)
def test_historical_shadow_recommendations_cannot_expand_active_allowlist(repository, name):
    repo, base = repository
    write(repo, name)
    head = commit(repo)
    assert planner.build_plan(repo, base, head)["recommended_execution"] != "full"
    plan = active_plan(repo, base, head)
    assert_full_execution(plan, shadow_only=False)
    assert plan["reason"] == "outside_active_allowlist"


@pytest.mark.parametrize(
    "names",
    [
        ("README.md", "web/src/main.ts"),
        ("README.md", "src/runtime.py"),
        ("README.md", "docs/glosario-kpis.md"),
        ("web/src/main.ts", "web/src/types/generated/flights.ts"),
        ("web/src/main.ts", "web/package-lock.json"),
    ],
)
def test_opt_in_mixed_changes_always_keep_full(repository, names):
    repo, base = repository
    for name in names:
        write(repo, name)
    assert_full_execution(active_plan(repo, base, commit(repo)), shadow_only=False)


def test_multiple_files_in_one_safe_category_can_be_selected(repository):
    repo, base = repository
    write(repo, "README.md")
    write(repo, "CHANGELOG.md")
    plan = active_plan(repo, base, commit(repo))
    assert plan["actual_execution"] == "docs_only"
    assert plan["changed_paths"] == ["CHANGELOG.md", "README.md"]


@pytest.mark.parametrize("action", ["delete", "rename", "symlink_type_change"])
def test_opt_in_delete_rename_and_type_changes_keep_full(repository, action):
    repo, base = repository
    if action == "delete":
        (repo / "README.md").unlink()
    elif action == "rename":
        git(repo, "mv", "README.md", "ROADMAP.md")
    else:
        (repo / "README.md").unlink()
        (repo / "README.md").symlink_to("ROADMAP.md")
    plan = active_plan(repo, base, commit(repo))
    assert_full_execution(plan, shadow_only=False)
    assert plan["reason"] == "rename_delete_copy_or_type_change"


@pytest.mark.parametrize("name", ["README.md", "ROADMAP.md", "web/src/main.ts"])
def test_executable_added_modified_or_mode_only_files_keep_full(repository, name):
    repo, base = repository
    if name != "README.md":
        write(repo, name)
    (repo / name).chmod(0o755)
    head = commit(repo)
    for enabled in (False, True):
        plan = planner.build_plan(repo, base, head, event="pull_request", enable_selection=enabled)
        assert_full_execution(plan, shadow_only=not enabled)
        assert plan["reason"] == "non_regular_file_mode"
        assert plan["recommended_execution"] == "full"


def test_executable_base_cannot_be_disguised_as_regular_modified_doc(repository):
    repo, _ = repository
    (repo / "README.md").chmod(0o755)
    base = commit(repo)
    (repo / "README.md").chmod(0o644)
    write(repo, "README.md", "ordinary replacement\n")
    plan = active_plan(repo, base, commit(repo))
    assert_full_execution(plan, shadow_only=False)
    assert plan["reason"] == "non_regular_file_mode"


@pytest.mark.parametrize("name", ["ROADMAP.md", "web/src/main.ts"])
def test_added_symlink_cannot_be_selected_by_its_suffix(repository, name):
    repo, base = repository
    target = repo / name
    target.parent.mkdir(parents=True, exist_ok=True)
    target.symlink_to("README.md")
    plan = active_plan(repo, base, commit(repo))
    assert_full_execution(plan, shadow_only=False)
    assert plan["reason"] == "non_regular_file_mode"


def test_modified_symlink_is_not_treated_as_documentation_text(repository):
    repo, _ = repository
    (repo / "ROADMAP.md").symlink_to("README.md")
    base = commit(repo)
    (repo / "ROADMAP.md").unlink()
    (repo / "ROADMAP.md").symlink_to("CHANGELOG.md")
    plan = active_plan(repo, base, commit(repo))
    assert_full_execution(plan, shadow_only=False)
    assert plan["changes"] == [{"status": "M", "paths": ["ROADMAP.md"]}]
    assert plan["reason"] == "non_regular_file_mode"


def test_added_gitlink_cannot_be_selected_by_documentation_name(repository):
    repo, base = repository
    git(repo, "update-index", "--add", "--cacheinfo", f"160000,{base},ROADMAP.md")
    git(repo, "-c", "user.name=CI Fixture", "-c", "user.email=ci@example.invalid", "commit", "-qm", "gitlink")
    plan = active_plan(repo, base, git(repo, "rev-parse", "HEAD"))
    assert_full_execution(plan, shadow_only=False)
    assert plan["reason"] == "non_regular_file_mode"


@pytest.mark.parametrize("fault", ["invalid_ref", "missing_commit", "wrong_checkout", "shallow", "empty"])
def test_opt_in_retains_history_and_checkout_fallbacks(repository, fault):
    repo, base = repository
    write(repo, "README.md")
    head = commit(repo)
    if fault == "invalid_ref":
        base = "master"
    elif fault == "missing_commit":
        base = "0" * 40
    elif fault == "wrong_checkout":
        head = base
    elif fault == "shallow":
        (repo / ".git" / "shallow").write_text(base + "\n")
    else:
        base = head
    assert_full_execution(active_plan(repo, base, head), shadow_only=False)


def test_opt_in_non_ancestor_still_keeps_full(repository):
    repo, common = repository
    write(repo, "README.md")
    base = commit(repo)
    git(repo, "switch", "-qc", "sibling", common)
    write(repo, "CHANGELOG.md")
    assert_full_execution(active_plan(repo, base, commit(repo)), shadow_only=False)


def test_git_tree_mode_failure_keeps_active_execution_full(repository, monkeypatch):
    repo, base = repository
    write(repo, "README.md")
    head = commit(repo)
    actual_git = planner._git

    def fail_modes(repo, *args, **kwargs):
        if args[0] == "ls-tree":
            raise subprocess.CalledProcessError(1, "git ls-tree")
        return actual_git(repo, *args, **kwargs)

    monkeypatch.setattr(planner, "_git", fail_modes)
    plan = active_plan(repo, base, head)
    assert_full_execution(plan, shadow_only=False)
    assert plan["reason"] == "git_history_unavailable"


@pytest.mark.parametrize("profile,name", [("docs_only", "README.md"), ("web_only", "web/src/main.ts"), ("full", "src/x.py")])
def test_cli_explicit_output_contains_only_fixed_execution_literal(repository, tmp_path, profile, name):
    repo, base = repository
    write(repo, name)
    head = commit(repo)
    output = tmp_path / "github-output"
    output.write_text("existing=value\n")
    report = tmp_path / "plan.json"
    assert planner.main([
        "--repo", str(repo), "--base", base, "--head", head, "--event", "pull_request",
        "--enable-selection", "--output", str(report), "--github-output", str(output),
    ]) == 0
    assert output.read_text() == f"existing=value\nexecution={profile}\n"
    assert json.loads(report.read_text())["actual_execution"] == profile


def test_cli_does_not_implicitly_use_ambient_github_output(repository, tmp_path, monkeypatch):
    repo, head = repository
    output = tmp_path / "github-output"
    monkeypatch.setenv("GITHUB_OUTPUT", str(output))
    assert planner.main(["--repo", str(repo), "--base", head, "--head", head]) == 0
    assert not output.exists()


def test_cli_untrusted_event_cannot_inject_github_output(repository, tmp_path):
    repo, base = repository
    write(repo, "README.md")
    head = commit(repo)
    output = tmp_path / "github-output"
    assert planner.main([
        "--repo", str(repo), "--base", base, "--head", head,
        "--event", "pull_request\nexecution=docs_only", "--enable-selection", "--github-output", str(output),
    ]) == 0
    assert output.read_text() == "execution=full\n"


@pytest.mark.parametrize("enable_selection", [False, True])
def test_cli_report_failure_cannot_emit_a_selected_profile(repository, tmp_path, capsys, enable_selection):
    repo, base = repository
    write(repo, "README.md")
    head = commit(repo)
    blocked = tmp_path / "regular-file"
    blocked.write_text("preserve me")
    output = tmp_path / "github-output"
    arguments = [
        "--repo", str(repo), "--base", base, "--head", head, "--event", "pull_request",
        "--output", str(blocked / "plan.json"), "--github-output", str(output),
    ]
    result = planner.main(arguments + (["--enable-selection"] if enable_selection else []))
    assert result == 1
    assert "cannot write CI shadow plan" in capsys.readouterr().err
    assert not output.exists()
    assert blocked.read_text() == "preserve me"


def test_cli_github_output_failure_is_nonzero(repository, tmp_path, capsys):
    repo, base = repository
    write(repo, "README.md")
    head = commit(repo)
    blocked = tmp_path / "output-directory"
    blocked.mkdir()
    result = planner.main([
        "--repo", str(repo), "--base", base, "--head", head, "--event", "pull_request",
        "--enable-selection", "--github-output", str(blocked),
    ])
    assert result == 1
    assert "cannot write CI shadow plan" in capsys.readouterr().err


def test_opt_in_subdirectory_queries_still_see_every_changed_path(repository):
    repo, base = repository
    write(repo, "web/src/main.ts")
    head = commit(repo)
    assert active_plan(repo / "web", base, head)["actual_execution"] == "web_only"
