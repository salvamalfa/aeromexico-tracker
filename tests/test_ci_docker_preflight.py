"""Fail-closed orchestration and real packaged-reader checks, without a daemon.

The orchestration doubles below are not evidence of a successful Docker build.
The CI job runs the real CLI, which builds and starts the image by its exact ID.
"""

from __future__ import annotations

import copy
import json
import subprocess
import sys

import pytest

from scripts import check_ci_docker as docker
from test_chat_docker_context import _materialize_runtime_copy

HEAD = "a" * 40
IMAGE = "sha256:" + "b" * 64
MANIFEST = "c" * 64


@pytest.fixture
def identity(monkeypatch):
    value = {
        "head": HEAD,
        "tracked_tree": "d" * 40,
        "tracked_worktree_dirty": False,
        "tracked_worktree_diff_sha256": docker.sha256(b""),
        "input_sha256": {"site/publication_manifest.json": MANIFEST},
    }
    monkeypatch.setattr(docker, "source_identity", lambda _root: copy.deepcopy(value))
    return value


def install_phases(monkeypatch, *, fail=None, inspect=None, observation=None):
    called = []
    observed = {
        "status": "docker_runtime_verified",
        "manifest_sha256": MANIFEST,
        "snapshot_version": "e" * 64,
        "provider": "mock",
        "worker_started_and_stopped": True,
        "retained_contracts_verified": 7,
    }
    if observation:
        observed.update(observation)

    def run(name, command, root, environment, timeout):
        called.append((name, command))
        assert "OPENAI_API_KEY" not in environment
        if name == "inspect":
            output = (inspect if inspect is not None else f"{IMAGE} {HEAD}\n").encode()
        elif name == "runtime":
            output = json.dumps(observed).encode()
        else:
            output = b""
        return {"name": name, "exit_code": 1 if name == fail else 0, "elapsed_seconds": 0.1}, output

    monkeypatch.setattr(docker, "run_phase", run)
    return called


def check(**kwargs):
    return docker.preflight(docker.ROOT, execute=True, cache_state="unknown", no_cache=False, **kwargs)


def test_dry_run_never_launches_docker_and_declares_cache_uncertainty(identity, monkeypatch):
    monkeypatch.setattr(docker, "run_phase", lambda *_: pytest.fail("dry run launched Docker"))
    report = docker.preflight(docker.ROOT, execute=False, cache_state="cold", no_cache=True)
    assert report["status"] == "planned" and report["phases"] == []
    assert report["cache"] == {
        "declared_state": "cold",
        "docker_stage_cache_disabled": True,
        "effective_cache_measured": False,
    }
    assert "--no-cache" in report["plan"]["build"]
    assert f"{docker.IMAGE_LABEL}={HEAD}" in report["plan"]["build"]


@pytest.mark.parametrize("phase", ["build", "inspect", "runtime"])
def test_failed_phase_stops_without_running_later_phases(identity, monkeypatch, phase):
    called = install_phases(monkeypatch, fail=phase)
    report = check()
    assert report["status"] == "failed" and report["failed_phase"] == phase
    names = [name for name, _command in called]
    assert names == ["build", "inspect", "runtime"][: names.index(phase) + 1]
    assert "runtime" not in report


@pytest.mark.parametrize("value", [f"{IMAGE} {'f' * 40}", f"runtime-tag {HEAD}", "", f"{IMAGE} {HEAD} extra"])
def test_stale_tag_or_wrong_image_revision_never_runs(identity, monkeypatch, value):
    called = install_phases(monkeypatch, inspect=value)
    report = check()
    assert report["status"] == "failed" and report["error"] == "image_identity_mismatch"
    assert [name for name, _ in called] == ["build", "inspect"]


@pytest.mark.parametrize(
    "observation",
    [
        {"manifest_sha256": "f" * 64},
        {"snapshot_version": "unavailable"},
        {"provider": "openai"},
        {"worker_started_and_stopped": False},
        {"status": "fixture_only"},
        {"retained_contracts_verified": 0},
        {"retained_contracts_verified": True},
    ],
)
def test_runtime_must_verify_current_manifest_real_snapshot_and_worker(identity, monkeypatch, observation):
    install_phases(monkeypatch, observation=observation)
    report = check()
    assert report["status"] == "failed" and report["error"] == "invalid_runtime_observation"


def test_runtime_uses_exact_image_id_and_no_host_code_mounts(identity, monkeypatch):
    called = install_phases(monkeypatch)
    report = check()
    assert report["status"] == "passed" and report["image_id"] == IMAGE
    command = called[-1][1]
    assert IMAGE in command and f"airlines-ci-preflight:{HEAD}" not in command
    assert command[:2] == docker.DOCKER
    assert "--network=none" in command and "--read-only" in command and "--pull=never" in command
    assert "--workdir=/app" in command
    assert not any(part in {"-v", "--volume", "--mount"} for part in command)
    assert [part for part in command if part in docker.PINS] == list(docker.PINS)
    assert "OPENAI_API_KEY" not in " ".join(command)


def test_source_change_during_build_cannot_be_accepted(identity, monkeypatch):
    install_phases(monkeypatch)
    states = iter([identity, identity | {"tracked_worktree_dirty": True}])
    monkeypatch.setattr(docker, "source_identity", lambda _: next(states))
    report = check()
    assert report["status"] == "failed" and report["error"] == "checkout_changed_during_preflight"


def test_only_public_approval_pins_are_inherited_as_chat_configuration(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-secret-not-for-docker")
    monkeypatch.setenv("CHAT_PROVIDER", "openai")
    monkeypatch.setenv("CHAT_PASSWORDS_JSON", "test-secret-password")
    monkeypatch.setenv("DOCKER_HOST", "tcp://wrong-daemon.invalid")
    monkeypatch.setenv("DOCKER_CONTEXT", "wrong-context")
    monkeypatch.setenv("DOCKER_CONFIG", "/existing/registry/config")
    for name in docker.PINS:
        monkeypatch.setenv(name, "pin-preserved")
    environment = docker.docker_environment()
    assert not set(environment) & {
        "OPENAI_API_KEY",
        "CHAT_PROVIDER",
        "CHAT_PASSWORDS_JSON",
        "DOCKER_HOST",
        "DOCKER_CONTEXT",
    }
    assert environment["DOCKER_CONFIG"] == "/existing/registry/config"
    assert all(environment[name] == "pin-preserved" for name in docker.PINS)


@pytest.mark.parametrize("kind", ["nonzero", "timeout", "missing_executable"])
def test_phase_reports_hashes_not_potentially_sensitive_log_contents(monkeypatch, kind):
    secret_log = b"proxy-password-must-not-appear-in-report"

    def run(*args, **kwargs):
        if kind == "timeout":
            raise subprocess.TimeoutExpired(args[0], kwargs["timeout"], output=secret_log, stderr=secret_log)
        if kind == "missing_executable":
            raise FileNotFoundError("potentially-sensitive-exception-text")
        return subprocess.CompletedProcess(args[0], 2, secret_log, secret_log)

    monkeypatch.setattr(docker.subprocess, "run", run)
    report, output = docker.run_phase("build", ["docker", "build"], docker.ROOT, {}, 1)
    encoded = json.dumps(report)
    assert "proxy-password" not in encoded and "potentially-sensitive" not in encoded
    assert report["exit_code"] != 0
    if kind != "missing_executable":
        assert report["stdout_sha256"] == docker.sha256(secret_log)
        assert report["stderr_bytes"] == len(secret_log) and output == secret_log


def test_cli_persists_failure_report_and_fails_the_job(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(
        docker, "preflight", lambda *_args, **_kwargs: {"status": "failed", "failed_phase": "runtime"}
    )
    report = tmp_path / "results/docker.json"
    assert docker.main(["--execute", "--report", str(report)]) == 1
    assert json.loads(report.read_text()) == json.loads(capsys.readouterr().out)


def run_packaged_probe(root):
    environment = docker.docker_environment() | {"PYTHONPATH": str(root), "PYTHONDONTWRITEBYTECODE": "1"}
    return subprocess.run(
        [sys.executable, "-c", docker.RUNTIME_PROBE],
        cwd=root,
        env=environment,
        capture_output=True,
        text=True,
        timeout=120,
    )


@pytest.fixture(scope="module")
def runtime_copy(tmp_path_factory):
    # Existing package admission model, not a complete Docker build. Its positive
    # reader/worker baseline makes the negative contract/dependency cases causal.
    root = tmp_path_factory.mktemp("docker-admitted-runtime")
    _materialize_runtime_copy(root)
    baseline = run_packaged_probe(root)
    assert baseline.returncode == 0, baseline.stdout + baseline.stderr
    assert json.loads(baseline.stdout)["worker_started_and_stopped"] is True
    return root


def test_actual_probe_refuses_missing_archived_contract_without_fixture_fallback(runtime_copy):
    manifest = json.loads((runtime_copy / "site/publication_manifest.json").read_text())
    name = "analysis.schema.json"
    archive = runtime_copy / "contracts/web/versions" / manifest["contracts"][name] / name
    assert archive.is_file()
    original = archive.read_bytes()
    archive.unlink()
    try:
        result = run_packaged_probe(runtime_copy)
    finally:
        archive.write_bytes(original)
    assert result.returncode != 0 and "docker_runtime_verified" not in result.stdout
    assert "SnapshotError" in result.stderr or "contract" in result.stderr.lower()


def test_actual_probe_refuses_missing_packaged_api_dependency(runtime_copy):
    dependency = runtime_copy / "src/conversational_analytics/api.py"
    original = dependency.read_bytes()
    dependency.unlink()
    # A compiled source fallback would invalidate this admission test.
    assert not (runtime_copy / "src/conversational_analytics/__pycache__").exists()
    try:
        result = run_packaged_probe(runtime_copy)
    finally:
        dependency.write_bytes(original)
    assert result.returncode != 0 and "docker_runtime_verified" not in result.stdout
    assert "ModuleNotFoundError" in result.stderr
