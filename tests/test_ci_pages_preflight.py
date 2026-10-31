"""The early Pages check cannot borrow a developer profile or loosen failure."""

import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest
import yaml

from scripts import check_ci_pages as pages

ROOT = Path(__file__).resolve().parents[1]
HEAD = "a" * 40


@pytest.fixture
def prepared(monkeypatch, tmp_path):
    root = tmp_path / "checkout"
    root.mkdir()
    environment = {
        "UV_PROJECT_ENVIRONMENT": str(tmp_path / "pages-environment"),
        "HTTP_PROXY": "http://proxy.invalid:8080",
        "SSL_CERT_FILE": "/configured/ca.pem",
        "OPENAI_API_KEY": "test-provider-credential-must-not-reach-child",
        "PYTHONPATH": "/unrelated/all-extras/site-packages",
        "PYTHONHOME": "/unrelated/python-home",
        "CHAT_BUSINESS_METRICS_APPROVAL_RECEIPT_SHA256": "test-approval-pin",
    }
    monkeypatch.setattr(pages, "git_head", lambda _root: HEAD)
    return root, environment


def test_commands_are_exactly_the_actual_pages_profile():
    workflow = yaml.safe_load((ROOT / ".github/workflows/pages.yml").read_text())
    steps = workflow["jobs"]["verify"]["steps"]
    install = next(step["run"] for step in steps if step.get("name") == "Install locked dependencies")
    verify = next(step["run"] for step in steps if "check_pages_publication.py" in step.get("run", ""))
    assert install.split() == list(pages.INSTALL)
    assert verify.split() == list(pages.VERIFY)
    assert "--all-extras" not in pages.INSTALL
    assert "--all-groups" not in pages.INSTALL
    assert "--locked" in pages.INSTALL and "--locked" in pages.VERIFY


def test_default_plan_never_installs_verifies_or_creates_environment(prepared, monkeypatch):
    root, environment = prepared

    def unexpected(*_args, **_kwargs):
        raise AssertionError("A dry run must not run uv")

    monkeypatch.setattr(pages, "run_phase", unexpected)
    report = pages.preflight(root, execute=False, cache_state="unknown", environment=environment)
    assert report["status"] == "planned"
    assert not report["executed"] and report["phases"] == []
    assert report["head"] == HEAD
    assert not Path(environment["UV_PROJECT_ENVIRONMENT"]).exists()
    assert report["environment_existed_before"] is False
    assert report["cache_state_declared"] == "unknown"
    assert report["cache_state_observed"] == "not_inferred"


@pytest.mark.parametrize("value", [None, "", ".venv", "inside/environment"])
def test_missing_or_shared_environment_fails_before_install(prepared, monkeypatch, value):
    root, environment = prepared
    if value is None:
        environment.pop("UV_PROJECT_ENVIRONMENT")
    else:
        environment["UV_PROJECT_ENVIRONMENT"] = value
    monkeypatch.setattr(pages, "run_phase", lambda *_args: pytest.fail("Unsafe environment reached uv"))
    report = pages.preflight(root, execute=True, cache_state="unknown", environment=environment)
    assert report["status"] == "failed" and report["error_type"] == "ValueError"
    assert report["phases"] == []
    assert report["execution_requested"] and not report["executed"]
    assert report["failed_phase"] == "configuration"


def test_symlink_to_checkout_environment_is_rejected(prepared, monkeypatch, tmp_path):
    root, environment = prepared
    target = root / ".venv"
    target.mkdir()
    link = tmp_path / "outside-symlink"
    try:
        link.symlink_to(target, target_is_directory=True)
    except OSError:
        pytest.skip("Creating symlinks is unavailable on this host")
    environment["UV_PROJECT_ENVIRONMENT"] = str(link)
    report = pages.preflight(root, execute=True, cache_state="warm", environment=environment)
    assert report["status"] == "failed" and report["phases"] == []


def test_missing_dependency_install_stops_before_any_verifier(prepared, monkeypatch):
    root, environment = prepared
    calls = []

    def run(command, **kwargs):
        calls.append((command, kwargs))
        return subprocess.CompletedProcess(command, 3, b"", b"dependency cannot be installed")

    monkeypatch.setattr(pages.subprocess, "run", run)
    report = pages.preflight(root, execute=True, cache_state="cold", environment=environment)
    assert report["status"] == "failed" and len(report["phases"]) == 1
    assert len(calls) == 1 and calls[0][0] == pages.INSTALL
    assert report["phases"][0]["exit_code"] == 3
    assert report["failed_phase"] == "install"
    assert report["phases"][0]["stderr"] == pages.log_identity(b"dependency cannot be installed")
    assert report["elapsed_seconds"] >= 0


@pytest.mark.parametrize("verify_exit", [0, 1, 79])
def test_verifier_exit_is_preserved_without_fallback(prepared, monkeypatch, verify_exit):
    root, environment = prepared
    calls = []

    def run(command, **kwargs):
        calls.append((command, kwargs))
        return subprocess.CompletedProcess(command, 0 if command == pages.INSTALL else verify_exit, b"ok", b"")

    monkeypatch.setattr(pages.subprocess, "run", run)
    report = pages.preflight(root, execute=True, cache_state="warm", environment=environment)
    assert [call[0] for call in calls] == [pages.INSTALL, pages.VERIFY]
    assert report["status"] == ("passed" if verify_exit == 0 else "failed")
    assert report["phases"][-1]["exit_code"] == verify_exit
    assert report["failed_phase"] == (None if verify_exit == 0 else "verify")
    for _, kwargs in calls:
        assert kwargs["cwd"] == root
        assert kwargs["capture_output"] and not kwargs["check"]
        child = kwargs["env"]
        assert "OPENAI_API_KEY" not in child
        assert "PYTHONPATH" not in child and "PYTHONHOME" not in child
        for key in ("HTTP_PROXY", "SSL_CERT_FILE", "CHAT_BUSINESS_METRICS_APPROVAL_RECEIPT_SHA256"):
            assert child[key] == environment[key]
        assert child["UV_PROJECT_ENVIRONMENT"] == environment["UV_PROJECT_ENVIRONMENT"]


def test_real_pages_selection_rejects_missing_source_data_receipt_without_fallback(prepared, monkeypatch):
    root, environment = prepared
    shutil.copytree(ROOT / "tests/fixtures/site/valid", root / "site")
    manifest_path = root / "site/publication_manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["files"].append({"path": "source-data-publication.json", "bytes": 2, "sha256": "a" * 64})
    manifest_path.write_text(json.dumps(manifest))
    calls = []
    actual_run = subprocess.run

    def run(command, **kwargs):
        calls.append(command)
        if command == pages.INSTALL:
            return subprocess.CompletedProcess(command, 0, b"", b"")
        child = {**kwargs["env"], "PYTHONPATH": str(ROOT)}
        return actual_run(
            [sys.executable, str(ROOT / "scripts/check_pages_publication.py"), "site/"],
            cwd=kwargs["cwd"], env=child, capture_output=True, check=False,
        )

    monkeypatch.setattr(pages.subprocess, "run", run)
    report = pages.preflight(root, execute=True, cache_state="unknown", environment=environment)
    assert report["status"] == "failed"
    assert report["phases"][-1]["exit_code"] != 0
    assert report["phases"][-1]["stderr"]["bytes"] > 0
    assert calls == [pages.INSTALL, pages.VERIFY]


def test_logs_and_environment_values_cannot_enter_the_report(prepared, monkeypatch):
    root, environment = prepared
    private_text = b"fake-sensitive-process-output"
    monkeypatch.setattr(
        pages.subprocess, "run",
        lambda command, **_kwargs: subprocess.CompletedProcess(command, 1, private_text, private_text),
    )
    report = pages.preflight(root, execute=True, cache_state="unknown", environment=environment)
    encoded = json.dumps(report)
    assert private_text.decode() not in encoded
    assert environment["OPENAI_API_KEY"] not in encoded
    assert environment["CHAT_BUSINESS_METRICS_APPROVAL_RECEIPT_SHA256"] not in encoded
    assert hashlib.sha256(private_text).hexdigest() in encoded


def test_missing_executable_is_a_retained_failure(prepared, monkeypatch):
    root, environment = prepared

    def missing(*_args, **_kwargs):
        raise FileNotFoundError("uv is unavailable")

    monkeypatch.setattr(pages.subprocess, "run", missing)
    report = pages.preflight(root, execute=True, cache_state="unknown", environment=environment)
    assert report["status"] == "failed"
    assert report["phases"][0]["exit_code"] == 127
    assert report["phases"][0]["error_type"] == "FileNotFoundError"


@pytest.mark.parametrize("cache_state,existed", [("cold", False), ("warm", True), ("unknown", True)])
def test_cache_label_does_not_infer_actual_cache_or_savings(prepared, cache_state, existed):
    root, environment = prepared
    if existed:
        Path(environment["UV_PROJECT_ENVIRONMENT"]).mkdir()
    report = pages.preflight(root, execute=False, cache_state=cache_state, environment=environment)
    assert report["cache_state_declared"] == cache_state
    assert report["environment_existed_before"] is existed
    assert report["cache_state_observed"] == "not_inferred"
    assert not report["phases"]
    assert "no claim" in report["measurement_scope"]


def test_cli_default_only_writes_an_explicit_report(prepared, monkeypatch, capsys, tmp_path):
    root, environment = prepared
    monkeypatch.setattr(pages, "ROOT", root)
    monkeypatch.setattr(pages.os, "environ", environment)
    destination = tmp_path / "results/pages.json"
    assert pages.main(["--report", str(destination)]) == 0
    report = json.loads(destination.read_text())
    assert report == json.loads(capsys.readouterr().out)
    assert report["status"] == "planned" and report["phases"] == []
    assert not Path(environment["UV_PROJECT_ENVIRONMENT"]).exists()


def test_cli_failure_keeps_report_and_nonzero_exit(prepared, monkeypatch, capsys, tmp_path):
    root, environment = prepared
    monkeypatch.setattr(pages, "ROOT", root)
    monkeypatch.setattr(pages.os, "environ", environment)
    monkeypatch.setattr(
        pages.subprocess, "run",
        lambda command, **_kwargs: subprocess.CompletedProcess(command, 17, b"", b"dependency missing"),
    )
    destination = tmp_path / "results/pages.json"
    assert pages.main(["--execute", "--report", str(destination)]) == 1
    assert json.loads(destination.read_text()) == json.loads(capsys.readouterr().out)
    assert json.loads(destination.read_text())["status"] == "failed"


def test_invalid_git_identity_never_reaches_uv(monkeypatch, tmp_path):
    monkeypatch.setattr(
        pages.subprocess, "run",
        lambda *_args, **_kwargs: subprocess.CompletedProcess(["git"], 0, b"not-a-sha", b""),
    )
    report = pages.preflight(
        tmp_path, execute=True, cache_state="unknown",
        environment={"UV_PROJECT_ENVIRONMENT": str(tmp_path.parent / "pages-env")},
    )
    assert report["status"] == "failed" and report["phases"] == []


def test_report_io_failure_is_not_hidden(tmp_path):
    destination = tmp_path / "not-a-directory"
    destination.write_text("keep me")
    with pytest.raises(OSError):
        pages.write_report(destination / "report.json", {"status": "failed"})
    assert destination.read_text() == "keep me"


def test_report_serialization_failure_preserves_previous_receipt_and_cleans_temp(tmp_path):
    destination = tmp_path / "report.json"
    original = b'{"status":"planned"}\n'
    destination.write_bytes(original)
    with pytest.raises(TypeError):
        pages.write_report(destination, {"invalid": {object()}})
    assert destination.read_bytes() == original
    assert list(tmp_path.iterdir()) == [destination]


@pytest.fixture
def policy_repo(tmp_path):
    root = tmp_path / "policy-repo"
    root.mkdir()
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    for key, value in (("user.name", "CI Fixture"), ("user.email", "ci@example.invalid")):
        subprocess.run(["git", "config", key, value], cwd=root, check=True)
    for name, raw in {
        "site/publication_manifest.json": '{"files":[]}',
        "src/app.py": "VALUE=1\n",
        "contracts/web/current.schema.json": "{}\n",
        "web/src/app.ts": "export const value=1;\n",
        "uv.lock": "locked fixture\n",
        "pyproject.toml": "[project]\nname='fixture'\n",
        "config/publish/authority.json": "{}\n",
        "config/chat/approved-index.json": "{}\n",
        "src/publish/authority.py": "VALUE=1\n",
        ".agents/skills/aeromexico-tracker-analysis/SKILL.md": "Reviewed fixture skill\n",
    }.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(raw)
    subprocess.run(["git", "add", "."], cwd=root, check=True)
    subprocess.run(["git", "commit", "-qm", "published baseline"], cwd=root, check=True)
    base = pages.git_head(root)
    subprocess.run(["git", "update-ref", "refs/remotes/origin/master", base], cwd=root, check=True)
    return root, base


def commit_change(root, name="src/app.py", raw="VALUE=2\n"):
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(raw)
    subprocess.run(["git", "add", "."], cwd=root, check=True)
    subprocess.run(["git", "commit", "-qm", "candidate change"], cwd=root, check=True)
    return pages.git_head(root)


@pytest.mark.parametrize("name", [
    "src/app.py", "src/future_package/lazy.py", "web/src/app.ts", "web/src/style.css",
    "web/index.html", "web/package.json", "web/package-lock.json", "web/vite.config.ts",
    "web/tsconfig.build.json", "contracts/web/current.schema.json",
    "contracts/web/versions/new/extra.schema.json",
])
def test_code_or_web_contract_only_change_uses_explicit_environment_policy(policy_repo, name):
    root, base = policy_repo
    head = commit_change(root, name)
    policy = pages.verification_policy(root, base, head)
    assert policy["mode"] == "environment_only"
    assert policy["bound_inputs_sha256"]
    assert policy["base"] == base and policy["head"] == head


@pytest.mark.parametrize("name", [
    "scripts/check_ci_pages.py", "docs/guide.md", "web/README.md", "web/src/app.test.ts",
    "web/src/__tests__/nested/app.ts", "web/src/app.spec.css",
])
def test_non_runtime_changes_keep_current_strong_verification(policy_repo, name):
    root, base = policy_repo
    head = commit_change(root, name)
    assert pages.verification_policy(root, base, head)["mode"] == "current_site_strong"


@pytest.mark.parametrize("name", [
    "site/publication_manifest.json", "site/new.json", "config/publish/authority.json",
    "config/chat/approved-index.json", "src/publish/authority.py",
    ".agents/skills/aeromexico-tracker-analysis/SKILL.md", "uv.lock", "pyproject.toml",
])
def test_publication_authority_or_lock_changes_never_use_environment_only(policy_repo, name):
    root, base = policy_repo
    (root / "src/app.py").write_text("runtime also changed\n")
    head = commit_change(root, name)
    policy = pages.verification_policy(root, base, head)
    assert policy["mode"] == "current_site_strong"
    assert policy["reason"] == "publication_authority_or_dependencies_changed"


@pytest.mark.parametrize("name", sorted(pages.LOCAL_ONLY))
def test_existing_local_only_exclusions_match_historical_eligibility(policy_repo, name):
    root, base = policy_repo
    (root / "src/app.py").write_text("runtime also changed\n")
    head = commit_change(root, name)
    assert pages.verification_policy(root, base, head)["mode"] == "environment_only"


@pytest.mark.parametrize("base", [None, "", "HEAD", "--help", "a" * 39, "f" * 40])
def test_missing_invalid_or_unknown_base_can_only_choose_current_strong(policy_repo, base):
    root, _ = policy_repo
    head = commit_change(root)
    assert pages.verification_policy(root, base, head)["mode"] == "current_site_strong"


def test_base_must_be_ancestor_of_both_head_and_protected_branch(policy_repo):
    root, base = policy_repo
    first = commit_change(root)
    second = commit_change(root, "src/app.py", "VALUE=3\n")
    assert pages.verification_policy(root, first, second)["mode"] == "current_site_strong"
    assert pages.verification_policy(root, second, base)["mode"] == "current_site_strong"
    subprocess.run(["git", "update-ref", "-d", "refs/remotes/origin/master"], cwd=root, check=True)
    assert pages.verification_policy(root, base, second)["mode"] == "current_site_strong"


@pytest.mark.parametrize("mutation", ["changed", "deleted", "untracked", "ignored", "symlink"])
def test_dirty_site_bytes_or_inventory_cannot_select_environment_only(policy_repo, mutation):
    root, base = policy_repo
    head = commit_change(root)
    manifest = root / "site/publication_manifest.json"
    if mutation == "changed":
        manifest.write_text("different\n")
    elif mutation == "deleted":
        manifest.unlink()
    elif mutation == "untracked":
        (root / "site/extra.json").write_text("{}")
    elif mutation == "ignored":
        (root / ".gitignore").write_text("site/extra.json\n")
        (root / "site/extra.json").write_text("{}")
    else:
        manifest.unlink()
        try:
            manifest.symlink_to(root / "src/app.py")
        except OSError:
            pytest.skip("Creating symlinks is unavailable on this host")
    assert pages.verification_policy(root, base, head)["mode"] == "current_site_strong"


def test_dirty_authority_is_rejected_but_ignored_python_cache_is_not_an_authority(policy_repo):
    root, base = policy_repo
    head = commit_change(root)
    cache = root / "src/publish/__pycache__/authority.cpython-313.pyc"
    cache.parent.mkdir()
    cache.write_bytes(b"temporary cache")
    assert pages.verification_policy(root, base, head)["mode"] == "environment_only"
    (root / "config/publish/untracked.json").write_text("unapproved authority\n")
    assert pages.verification_policy(root, base, head)["mode"] == "current_site_strong"


def test_new_tracked_authority_cache_is_not_silently_ignored(policy_repo):
    root, base = policy_repo
    (root / "src/app.py").write_text("VALUE=2\n")
    head = commit_change(root, "src/publish/__pycache__/tracked.pyc", "tracked bytecode\n")
    assert pages.verification_policy(root, base, head)["mode"] == "current_site_strong"


def test_regular_mode_change_does_not_add_an_authority_restriction(policy_repo):
    root, base = policy_repo
    (root / "src/app.py").write_text("VALUE=2\n")
    subprocess.run(["git", "add", "src/app.py"], cwd=root, check=True)
    subprocess.run(["git", "update-index", "--chmod=+x", "src/publish/authority.py"], cwd=root, check=True)
    subprocess.run(["git", "commit", "-qm", "source code and authority mode only"], cwd=root, check=True)
    assert pages.verification_policy(root, base, pages.git_head(root))["mode"] == "environment_only"


def test_runtime_chmod_alone_does_not_skip_current_strong_verification(policy_repo):
    root, base = policy_repo
    subprocess.run(["git", "update-index", "--chmod=+x", "src/app.py"], cwd=root, check=True)
    subprocess.run(["git", "commit", "-qm", "mode only"], cwd=root, check=True)
    assert pages.verification_policy(root, base, pages.git_head(root))["mode"] == "current_site_strong"


@pytest.mark.parametrize("failed_phase", [None, "install", "imports"])
def test_environment_only_results_never_claim_strong_site_or_runtime_approval(
    policy_repo, monkeypatch, tmp_path, failed_phase,
):
    root, base = policy_repo
    commit_change(root)
    calls = []

    def phase(name, command, *_args):
        calls.append((name, command))
        return {"phase": name, "command": list(command), "exit_code": 3 if name == failed_phase else 0}

    monkeypatch.setattr(pages, "run_phase", phase)
    report = pages.preflight(
        root, execute=True, cache_state="unknown", base=base,
        environment={"UV_PROJECT_ENVIRONMENT": str(tmp_path / "isolated-pages")},
    )
    assert report["verification_policy"]["mode"] == "environment_only"
    assert report["status"] == ("passed" if failed_phase is None else "failed")
    assert report["current_site_strong_verified"] is False
    assert report["current_runtime_approved"] is False
    assert pages.VERIFY not in [command for _, command in calls]
    if failed_phase == "install":
        assert [name for name, _ in calls] == ["install"]
    else:
        assert calls[-1] == ("imports", pages.ENVIRONMENT_VERIFY)
    if failed_phase is None:
        assert report["site_verification"] == "historical_site_not_reapproved"


def test_conservation_race_is_failure_not_an_import_or_strong_fallback(policy_repo, monkeypatch, tmp_path):
    root, base = policy_repo
    commit_change(root)
    calls = []

    def phase(name, command, *_args):
        calls.append(command)
        (root / "config/publish/authority.json").write_text("changed during install")
        return {"phase": name, "exit_code": 0}

    monkeypatch.setattr(pages, "run_phase", phase)
    report = pages.preflight(
        root, execute=True, cache_state="unknown", base=base,
        environment={"UV_PROJECT_ENVIRONMENT": str(tmp_path / "isolated-pages")},
    )
    assert report["status"] == "failed" and report["failed_phase"] == "policy_revalidation"
    assert calls == [pages.INSTALL]
    assert not report["current_site_strong_verified"]


def test_environment_probe_really_imports_selected_module_and_missing_dependency_fails(
    policy_repo, monkeypatch, tmp_path,
):
    root, first = policy_repo
    (root / "scripts").mkdir()
    shutil.copyfile(ROOT / "scripts/check_pages_publication.py", root / "scripts/check_pages_publication.py")
    (root / "src/__init__.py").write_text("")
    (root / "src/publish/__init__.py").write_text("")
    (root / "src/publish/source_data_scope.py").write_text("import unavailable_ci_pages_dependency_fixture\n")
    proof = root / "site/source-data-publication.json"
    proof.write_text(json.dumps({"remote_witness": {"baseline_commit": first}}))
    manifest = root / "site/publication_manifest.json"
    manifest.write_text(json.dumps({"files": [{
        "path": proof.name, "sha256": hashlib.sha256(proof.read_bytes()).hexdigest(),
        "bytes": proof.stat().st_size,
    }]}))
    base = commit_change(root, "src/app.py", "VALUE=2\n")
    subprocess.run(["git", "update-ref", "refs/remotes/origin/master", base], cwd=root, check=True)
    commit_change(root, "src/app.py", "VALUE=3\n")
    calls = []
    original_phase = pages.run_phase

    def phase(name, command, repo, environment):
        calls.append(command)
        if command == pages.INSTALL:
            return {"phase": name, "exit_code": 0}
        return original_phase(name, (sys.executable, "-c", pages.ENVIRONMENT_PROBE), repo, environment)

    monkeypatch.setattr(pages, "run_phase", phase)
    report = pages.preflight(
        root, execute=True, cache_state="unknown", base=base,
        environment={**os.environ, "UV_PROJECT_ENVIRONMENT": str(tmp_path / "isolated-pages")},
    )
    assert report["verification_policy"]["mode"] == "environment_only"
    assert report["status"] == "failed" and report["failed_phase"] == "imports"
    assert report["phases"][-1]["stderr"]["bytes"] > 0
    assert calls == [pages.INSTALL, pages.ENVIRONMENT_VERIFY]
    assert not report["current_site_strong_verified"]
