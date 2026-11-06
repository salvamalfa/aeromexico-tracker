"""Historical Pages verification stays bound, isolated and fail-closed."""

import json
import subprocess
from contextlib import contextmanager

import pytest

from scripts import check_ci_pages as pages
from tests.test_ci_pages_preflight import commit_change
from tests.test_ci_pages_preflight import policy_repo as policy_repo
from tests.test_ci_pages_preflight import prepared as prepared


@pytest.fixture
def published_repo(policy_repo):
    root, _ = policy_repo
    producer = commit_change(
        root, "scripts/check_pages_publication.py", "print('historical strong verifier')\n",
    )
    (root / "site/nested").mkdir()
    (root / "site/nested/published.json").write_text('{"published":true}\n')
    release = commit_change(
        root, "site/publication_manifest.json", json.dumps({"code_commit": producer, "files": []}),
    )
    # BASE already contains a code-only merge after the publication producer.
    base = commit_change(root, "web/src/app.ts", "export const value=2;\n")
    subprocess.run(["git", "update-ref", "refs/remotes/origin/master", base], cwd=root, check=True)
    head = commit_change(root, "web/src/app.ts", "export const value=3;\n")
    return root, base, producer, release, head


def worktree_inventory(root):
    return pages.git(root, "worktree", "list", "--porcelain")


def historical_preflight(root, base, tmp_path, *, execute=True):
    return pages.preflight(
        root, execute=execute, cache_state="unknown", base=base, verify_published_base=True,
        environment={
            "UV_PROJECT_ENVIRONMENT": str(tmp_path / "isolated-pages"),
            "OPENAI_API_KEY": "private-provider-key",
            "PYTHONPATH": "/unrelated/site-packages", "PYTHONHOME": "/unrelated/python",
            "SSL_CERT_FILE": "/configured/ca.pem",
        },
    )


def test_published_plan_and_cli_dry_run_never_mutate_git_or_launch_uv(
    published_repo, monkeypatch, tmp_path, capsys,
):
    root, base, producer, _, _ = published_repo
    before = worktree_inventory(root)
    monkeypatch.setattr(pages, "ROOT", root)
    monkeypatch.setattr(pages.os, "environ", {"UV_PROJECT_ENVIRONMENT": str(tmp_path / "isolated")})
    monkeypatch.setattr(pages, "run_phase", lambda *_args: pytest.fail("Dry run launched uv"))
    monkeypatch.setattr(pages, "published_worktree", lambda *_args: pytest.fail("Dry run created a worktree"))
    assert pages.main(["--dry-run", "--base", base, "--verify-published-base"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["status"] == "planned" and report["phases"] == []
    assert report["historical_verification_plan"]["producer"] == producer
    assert report["historical_verification_plan"]["base"] == base
    assert report["historical_verification_plan"]["approval_scope"] == "historical_site_only"
    assert report["commands"] == [list(pages.INSTALL), list(pages.ENVIRONMENT_VERIFY), list(pages.VERIFY)]
    assert report["historical_site_strong_verified"] is False
    assert worktree_inventory(root) == before
    assert not (tmp_path / "isolated").exists()


@pytest.mark.parametrize("fail_inside", [False, True])
def test_published_worktree_is_detached_has_real_git_marker_and_cleans_up(published_repo, fail_inside):
    root, base, producer, _, head = published_repo
    policy = pages.verification_policy(root, base, head)
    plan = pages.published_base_plan(root, policy)
    before = worktree_inventory(root)
    branches = pages.git(root, "for-each-ref", "refs/heads")
    temporary = None
    try:
        with pages.published_worktree(root, policy, plan) as (temporary, expected, marker):
            assert pages.git_head(temporary) == producer
            assert (temporary / ".git").is_file() and not (temporary / ".git").is_symlink()
            assert marker.startswith(b"gitdir: ")
            assert pages.git(temporary, "rev-parse", "--abbrev-ref", "HEAD").strip() == b"HEAD"
            assert (temporary / "web/src/app.ts").read_text() == "export const value=1;\n"
            assert (temporary / "site/nested/published.json").read_bytes() == (
                root / "site/nested/published.json"
            ).read_bytes()
            assert pages.historical_snapshot(temporary, producer, expected, marker)
            if fail_inside:
                raise RuntimeError("Verifier failed after worktree creation")
    except RuntimeError:
        assert fail_inside
    assert temporary is not None and not temporary.exists()
    assert worktree_inventory(root) == before
    assert pages.git(root, "for-each-ref", "refs/heads") == branches


@pytest.mark.parametrize("failed_phase", [None, "install", "imports", "historical_verify"])
def test_historical_phases_use_exact_locked_profile_and_never_fallback(
    published_repo, monkeypatch, tmp_path, failed_phase,
):
    root, base, producer, _, _ = published_repo
    before = worktree_inventory(root)
    calls = []

    def phase(name, command, checkout, environment):
        calls.append((name, command, checkout, dict(environment)))
        if name == "historical_verify":
            assert pages.git_head(checkout) == producer
            assert checkout != root
            manifest = json.loads((checkout / "site/publication_manifest.json").read_text())
            assert manifest["code_commit"] == producer
        else:
            assert checkout == root
        return {"phase": name, "command": list(command), "exit_code": 19 if name == failed_phase else 0}

    monkeypatch.setattr(pages, "run_phase", phase)
    report = historical_preflight(root, base, tmp_path)
    names = ["install", "imports", "historical_verify"]
    if failed_phase:
        names = names[:names.index(failed_phase) + 1]
    assert [name for name, *_ in calls] == names
    expected_commands = [pages.INSTALL, pages.ENVIRONMENT_VERIFY, pages.VERIFY][:len(names)]
    assert [command for _, command, *_ in calls] == expected_commands
    assert report["status"] == ("failed" if failed_phase else "passed")
    assert report["failed_phase"] == failed_phase
    assert report["current_site_strong_verified"] is False
    assert report["current_runtime_approved"] is False
    assert report["historical_site_strong_verified"] is (failed_phase is None)
    if failed_phase is None:
        assert report["site_verification"] == "historical_site_strong_verified"
    environments = [environment for *_, environment in calls]
    assert all(environment == environments[0] for environment in environments)
    assert environments[0]["UV_PROJECT_ENVIRONMENT"] == str(tmp_path / "isolated-pages")
    assert environments[0]["SSL_CERT_FILE"] == "/configured/ca.pem"
    assert not {"OPENAI_API_KEY", "PYTHONPATH", "PYTHONHOME"}.intersection(environments[0])
    assert worktree_inventory(root) == before


@pytest.mark.parametrize("target", [
    "current_site", "current_authority", "current_head", "protected_base",
    "historical_code", "historical_site", "historical_head", "ignored_input", "python_cache",
])
def test_historical_verification_revalidates_both_checkouts_without_fallback(
    published_repo, monkeypatch, tmp_path, target,
):
    root, base, _, _, head = published_repo
    before = worktree_inventory(root)
    calls = []

    def phase(name, command, checkout, _environment):
        calls.append(name)
        if name == "historical_verify":
            if target == "current_site":
                (root / "site/nested/published.json").write_text("changed during verification")
            elif target == "current_authority":
                (root / "config/publish/authority.json").write_text("changed during verification")
            elif target == "current_head":
                pages.git(root, "update-ref", "HEAD", base)
            elif target == "protected_base":
                pages.git(root, "update-ref", "-d", "refs/remotes/origin/master")
            elif target == "historical_code":
                (checkout / "src/app.py").write_text("changed historical code")
            elif target == "historical_site":
                (checkout / "site/nested/published.json").write_text("changed historical site")
            elif target == "historical_head":
                pages.git(checkout, "update-ref", "HEAD", base)
            elif target == "python_cache":
                cache = checkout / "src/__pycache__/app.cpython-313.pyc"
                cache.parent.mkdir()
                cache.write_bytes(b"injected executable bytecode")
            else:
                (checkout / ".gitignore").write_text("src/injected.py\n")
                (checkout / "src/injected.py").write_text("untracked import input\n")
        return {"phase": name, "exit_code": 0}
    monkeypatch.setattr(pages, "run_phase", phase)
    report = historical_preflight(root, base, tmp_path)
    assert calls == ["install", "imports", "historical_verify"]
    assert report["status"] == "failed"
    assert report["failed_phase"] == (
        "policy_revalidation" if target.startswith("current_") or target == "protected_base"
        else "historical_revalidation"
    )
    assert not report["historical_site_strong_verified"] and not report["current_runtime_approved"]
    if target == "current_head":
        pages.git(root, "update-ref", "HEAD", head)
    assert worktree_inventory(root) == before


def test_historical_git_marker_change_is_rejected_and_worktree_removed(published_repo):
    root, base, producer, _, head = published_repo
    policy = pages.verification_policy(root, base, head)
    before = worktree_inventory(root)
    plan = pages.published_base_plan(root, policy)
    with pages.published_worktree(root, policy, plan) as (checkout, expected, marker):
        (checkout / ".git").write_bytes(marker + b"changed\n")
        try:
            with pytest.raises(ValueError, match="Git marker changed"):
                pages.historical_snapshot(checkout, producer, expected, marker)
        finally:
            (checkout / ".git").write_bytes(marker)
    assert worktree_inventory(root) == before


@pytest.mark.parametrize("name", [
    "uv.lock", "pyproject.toml", "config/publish/authority.json", "config/chat/approved-index.json",
    ".agents/skills/aeromexico-tracker-analysis/SKILL.md",
])
def test_producer_config_or_dependencies_cannot_borrow_current_environment(
    published_repo, monkeypatch, tmp_path, name,
):
    root, _, _, _, _ = published_repo
    base = commit_change(root, name, "changed after producer\n")
    subprocess.run(["git", "update-ref", "refs/remotes/origin/master", base], cwd=root, check=True)
    commit_change(root, "web/src/app.ts", "export const value=4;\n")
    monkeypatch.setattr(pages, "run_phase", lambda *_args: pytest.fail("Incompatible producer reached uv"))
    report = historical_preflight(root, base, tmp_path)
    assert report["verification_policy"]["mode"] == "environment_only"
    assert report["status"] == "failed" and report["failed_phase"] == "historical_setup"
    assert report["phases"] == [] and not report["historical_site_strong_verified"]


def test_worktree_setup_failure_cleans_up_without_verification(published_repo, monkeypatch, tmp_path):
    root, base, _, _, _ = published_repo
    before = worktree_inventory(root)
    calls = []

    def phase(name, *_args):
        calls.append(name)
        return {"phase": name, "exit_code": 0}

    def fail_copy(*_args, **_kwargs):
        raise OSError("Cannot materialize bound site")

    monkeypatch.setattr(pages, "run_phase", phase)
    monkeypatch.setattr(pages.shutil, "copytree", fail_copy)
    report = historical_preflight(root, base, tmp_path)
    assert report["status"] == "failed" and report["failed_phase"] == "historical_setup"
    assert calls == ["install", "imports"]
    assert worktree_inventory(root) == before


def test_opt_in_keeps_current_strong_verification_when_not_environment_only(prepared, monkeypatch):
    root, environment = prepared
    calls = []

    def phase(name, command, *_args):
        calls.append((name, command))
        return {"phase": name, "exit_code": 0}

    monkeypatch.setattr(pages, "run_phase", phase)
    monkeypatch.setattr(
        pages, "published_worktree", lambda *_args: pytest.fail("Unexpected historical worktree"),
    )
    report = pages.preflight(
        root, execute=True, cache_state="unknown", environment=environment, verify_published_base=True,
    )
    assert calls == [("install", pages.INSTALL), ("verify", pages.VERIFY)]
    assert report["status"] == "passed" and report["current_site_strong_verified"]
    assert not report["historical_site_strong_verified"]


@pytest.mark.parametrize("producer", [None, "HEAD", "f" * 40, "unrelated"])
def test_missing_unknown_or_nonancestor_producer_fails_closed(
    published_repo, monkeypatch, tmp_path, producer,
):
    root, _, _, _, _ = published_repo
    if producer == "unrelated":
        tree = pages.git(root, "rev-parse", "HEAD^{tree}").decode().strip()
        producer = pages.git(root, "commit-tree", tree, "-m", "unrelated").decode().strip()
    base = commit_change(root, "site/publication_manifest.json", json.dumps({"code_commit": producer}))
    pages.git(root, "update-ref", "refs/remotes/origin/master", base)
    commit_change(root, "web/src/app.ts", "export const value=4;\n")
    monkeypatch.setattr(pages, "run_phase", lambda *_args: pytest.fail("Untrusted producer reached uv"))
    report = historical_preflight(root, base, tmp_path)
    assert report["status"] == "failed" and report["failed_phase"] == "historical_setup"
    assert report["phases"] == []


def test_historical_selector_must_exist_in_producer(policy_repo):
    root, producer = policy_repo
    base = commit_change(root, "site/publication_manifest.json", json.dumps({"code_commit": producer}))
    pages.git(root, "update-ref", "refs/remotes/origin/master", base)
    head = commit_change(root)
    policy = pages.verification_policy(root, base, head)
    with pytest.raises(ValueError, match="strong publication selector"):
        pages.published_base_plan(root, policy)


def test_git_overrides_and_checkout_hooks_cannot_redirect_historical_worktree(published_repo, monkeypatch):
    root, base, _, _, head = published_repo
    marker = root.parent / "checkout-hook-executed"
    hook = root / ".git/hooks/post-checkout"
    hook.write_text(f"#!/bin/sh\ntouch '{marker}'\n")
    hook.chmod(0o755)
    monkeypatch.setenv("GIT_DIR", str(root.parent / "unrelated-git-dir"))
    monkeypatch.setenv("GIT_WORK_TREE", str(root.parent / "unrelated-checkout"))
    policy = pages.verification_policy(root, base, head)
    with pages.published_worktree(root, policy, pages.published_base_plan(root, policy)):
        assert not marker.exists()
    assert not marker.exists()


def test_worktree_cleanup_failure_is_a_retained_failure(published_repo, monkeypatch, tmp_path):
    root, base, _, _, _ = published_repo
    original_git = pages.git
    pending = []

    def git(checkout, *arguments):
        if arguments[:2] == ("worktree", "remove"):
            pending.append(arguments[-1])
            raise subprocess.CalledProcessError(1, ["git", *arguments])
        return original_git(checkout, *arguments)

    monkeypatch.setattr(pages, "git", git)
    monkeypatch.setattr(pages, "run_phase", lambda name, *_args: {"phase": name, "exit_code": 0})
    try:
        report = historical_preflight(root, base, tmp_path)
        assert report["status"] == "failed" and report["failed_phase"] == "historical_cleanup"
        assert not report["historical_site_strong_verified"]
        assert [phase["phase"] for phase in report["phases"]] == ["install", "imports", "historical_verify"]
    finally:
        for checkout in pending:
            original_git(root, "worktree", "remove", "--force", checkout)


def test_policy_change_during_historical_setup_stops_before_verifier(published_repo, monkeypatch, tmp_path):
    root, base, _, _, _ = published_repo
    before = worktree_inventory(root)
    original = pages.published_worktree
    calls = []

    @contextmanager
    def worktree(*arguments):
        with original(*arguments) as value:
            (root / "config/chat/approved-index.json").write_text("changed during setup")
            yield value

    def phase(name, *_args):
        calls.append(name)
        return {"phase": name, "exit_code": 0}

    monkeypatch.setattr(pages, "published_worktree", worktree)
    monkeypatch.setattr(pages, "run_phase", phase)
    report = historical_preflight(root, base, tmp_path)
    assert report["status"] == "failed" and report["failed_phase"] == "policy_revalidation"
    assert calls == ["install", "imports"]
    assert worktree_inventory(root) == before


def test_historical_child_git_cannot_use_ambient_redirects(published_repo, monkeypatch, tmp_path):
    root, base, _, _, _ = published_repo
    calls = []

    def phase(name, command, checkout, environment):
        calls.append(name)
        assert "GIT_DIR" not in environment and "GIT_WORK_TREE" not in environment
        assert environment["GIT_CONFIG_NOSYSTEM"] == "1"
        assert environment["GIT_NO_REPLACE_OBJECTS"] == "1"
        assert environment["PYTHONDONTWRITEBYTECODE"] == "1"
        return {"phase": name, "exit_code": 0}

    monkeypatch.setattr(pages, "run_phase", phase)
    report = pages.preflight(
        root, execute=True, cache_state="unknown", base=base, verify_published_base=True,
        environment={
            "UV_PROJECT_ENVIRONMENT": str(tmp_path / "isolated"),
            "GIT_DIR": "/unrelated/git-dir", "GIT_WORK_TREE": "/unrelated/worktree",
        },
    )
    assert report["status"] == "passed"
    assert calls == ["install", "imports", "historical_verify"]
