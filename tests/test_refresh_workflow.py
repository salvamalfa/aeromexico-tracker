"""Exercise the real refresh DAG and guards without dispatching or writing Gold."""

from __future__ import annotations

import ast
import copy
import hashlib
import itertools
import os
import re
import shlex
import shutil
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
STATES = ("success", "failure", "cancelled", "skipped", "")
PROTECTED = ("data/gold", "docs/diccionario-datos.md")


def workflow():
    return yaml.safe_load((ROOT / ".github/workflows/refresh.yml").read_text(encoding="utf-8"))


def condition(expression, values, *, success=True, cancelled=False):
    """Evaluate the limited Actions boolean grammar actually used by this DAG.

    This is a local model, not an Actions runner. Reject unfamiliar syntax so a
    workflow change cannot silently pass with an unevaluated condition.
    """
    source = expression.removeprefix("${{").removesuffix("}}").strip()
    explicit_status = re.search(r"\b(?:always|success|cancelled|failure)\s*\(", source)
    if not explicit_status and not success:
        return False
    source = re.sub(r"!(?!=)", " not ", source.replace("&&", " and ").replace("||", " or ")).strip()

    def evaluate(node):
        if isinstance(node, ast.Constant):
            return node.value
        if isinstance(node, ast.Attribute):
            parts = []
            while isinstance(node, ast.Attribute):
                parts.append(node.attr)
                node = node.value
            assert isinstance(node, ast.Name)
            return values.get(".".join([node.id, *reversed(parts)]), "")
        if isinstance(node, ast.Call):
            assert isinstance(node.func, ast.Name) and not node.args and not node.keywords
            return {"always": True, "success": success, "cancelled": cancelled, "failure": not success}[node.func.id]
        if isinstance(node, ast.BoolOp):
            operands = [bool(evaluate(item)) for item in node.values]
            assert isinstance(node.op, (ast.And, ast.Or))
            return all(operands) if isinstance(node.op, ast.And) else any(operands)
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
            return not evaluate(node.operand)
        if isinstance(node, ast.Compare):
            assert len(node.ops) == len(node.comparators) == 1
            left, right = evaluate(node.left), evaluate(node.comparators[0])
            assert isinstance(node.ops[0], (ast.Eq, ast.NotEq))
            return left == right if isinstance(node.ops[0], ast.Eq) else left != right
        raise AssertionError(ast.dump(node))

    return bool(evaluate(ast.parse(source, mode="eval").body))


def simulate(document, ci="success", stage8="success", *, overrides=None, stale=False, cancelled=False):
    """Follow actual YAML order, default success(), outcomes and continue-on-error.

    Only statuses are synthetic. No action, freshness command, commit or push is
    executed. The snapshot shell itself is exercised separately with real Git.
    """
    job = document["jobs"]["validate"]
    values = {"needs.ci.result": ci, "steps.manual_source.outputs.is_stale": str(stale).lower()}
    if not condition(job.get("if", "success()"), values, success=ci == "success", cancelled=cancelled):
        return [], {}
    trace, outcomes = [], {}
    successful = True
    overrides = overrides or {}
    for index, step in enumerate(job["steps"]):
        key = step.get("id", step.get("name", f"action-{index}"))
        if condition(step.get("if", "success()"), values, success=successful, cancelled=cancelled):
            trace.append(key)
            default = stage8 if key == "validate_stage8" else "failure" if key == "stop_on_failure" else "success"
            outcome = overrides.get(key, default)
            conclusion = "success" if outcome == "failure" and step.get("continue-on-error") else outcome
            successful = successful and conclusion != "failure"
        else:
            outcome = "skipped"
        outcomes[key] = outcome
        values[f"steps.{key}.outcome"] = outcome
    return trace, outcomes


def test_refresh_keeps_schedule_permissions_and_full_reusable_ci():
    document = workflow()
    events = document.get("on", document.get(True))
    assert events == {"workflow_dispatch": None, "schedule": [{"cron": "0 12 5 2,5,8,11 *"}]}
    assert document["concurrency"] == {"group": "dashboard-refresh", "cancel-in-progress": False}
    assert document["permissions"] == {"contents": "write", "issues": "write"}
    assert set(document["jobs"]) == {"ci", "validate"}
    assert document["jobs"]["ci"] == {
        "uses": "./.github/workflows/ci.yml",
        "with": {"force_full": True},
        "permissions": {"contents": "read"},
    }
    job = document["jobs"]["validate"]
    assert job["needs"] == ["ci"]
    checkout = next(step for step in job["steps"] if step.get("id") == "checkout")
    assert checkout["with"] == {"ref": "${{ github.sha }}", "fetch-depth": 0}
    steps = {step["id"]: step for step in job["steps"] if "id" in step}
    assert steps["manual_source"]["run"] == (
        "uv run python -m src.dashboard.check_manual_freshness --source afac --max-age-days 62"
    )
    assert steps["validate_stage8"]["run"] == "uv run python -m src.dashboard.validate_stage8"
    assert steps["validate_stage8"]["continue-on-error"] is True
    assert steps["snapshot_before"]["env"] == steps["snapshot_after"]["env"] == {"REFRESH_SHA": "${{ github.sha }}"}
    ids = list(steps)
    assert ids.index("snapshot_before") < ids.index("validate_stage8") < ids.index("snapshot_after")
    assert ids.index("snapshot_after") < ids.index("failure_issue") < ids.index("stop_on_failure") < ids.index("commit")
    commands = "\n".join(step.get("run", "") for step in job["steps"])
    assert "pytest" not in commands and "src.publish" not in commands and "src.ingest" not in commands
    assert [line.strip() for line in commands.splitlines() if line.strip().startswith("git add ")] == [
        "git add data/gold docs/diccionario-datos.md"
    ]
    # Calling CI must not invent a historical publication base or inherit secrets.
    ci = yaml.safe_load((ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8"))
    assert ci["permissions"] == {"contents": "read"}
    for called_job in ci["jobs"].values():
        for step in called_job.get("steps", []):
            if "actions/checkout@" in step.get("uses", ""):
                assert step.get("with", {}).get("ref", "${{ github.sha }}") == "${{ github.sha }}"


@pytest.mark.parametrize("ci,stage8", itertools.product(STATES, repeat=2))
def test_every_non_success_result_blocks_commit_and_preserves_diagnosis(ci, stage8):
    trace, outcomes = simulate(workflow(), ci, stage8)
    good = ci == stage8 == "success"
    assert ("commit" in trace) == good
    assert ("failure_issue" in trace) == (not good)
    assert ("stop_on_failure" in trace) == (not good)
    if not good:
        assert outcomes["stop_on_failure"] == "failure"
    assert "manual_source" in trace
    assert "validate_stage8" in trace


@pytest.mark.parametrize("step", ["snapshot_before", "manual_source", "snapshot_after"])
@pytest.mark.parametrize("outcome", STATES[1:])
def test_setup_identity_or_freshness_without_success_cannot_commit(step, outcome):
    trace, _ = simulate(workflow(), overrides={step: outcome})
    assert "commit" not in trace
    assert "failure_issue" in trace and "stop_on_failure" in trace


@pytest.mark.parametrize("step", ["checkout", "dependencies"])
def test_setup_failure_still_reaches_diagnosis_and_never_commits(step):
    trace, _ = simulate(workflow(), overrides={step: "failure"})
    assert "failure_issue" in trace and "stop_on_failure" in trace
    assert "commit" not in trace


def test_failed_snapshot_never_runs_stage8_on_unvalidated_gold():
    trace, _ = simulate(workflow(), overrides={"snapshot_before": "failure"})
    assert "validate_stage8" not in trace


def test_issue_api_failure_still_reaches_nonzero_stop():
    trace, outcomes = simulate(workflow(), ci="failure", overrides={"failure_issue": "failure"})
    assert outcomes["failure_issue"] == outcomes["stop_on_failure"] == "failure"
    assert "commit" not in trace


def test_workflow_cancellation_does_not_start_validation_or_commit():
    assert simulate(workflow(), cancelled=True) == ([], {})


@pytest.mark.parametrize("ci", STATES)
def test_stale_afac_remains_an_advisory_reminder_even_after_ci_failure(ci):
    trace, _ = simulate(workflow(), ci=ci, stale=True)
    assert "Open AFAC manual-refresh reminder" in trace
    assert ("commit" in trace) == (ci == "success")


def test_model_detects_permissive_commit_and_missing_failure_finalizer():
    document = copy.deepcopy(workflow())
    commit = next(step for step in document["jobs"]["validate"]["steps"] if step.get("id") == "commit")
    commit["if"] = "always()"
    assert "commit" in simulate(document, ci="failure")[0]
    document["jobs"]["validate"].pop("if")
    assert simulate(document, ci="failure") == ([], {})
    with pytest.raises((AssertionError, KeyError, SyntaxError)):
        condition("unsupported()", {})


def git(repo, *arguments):
    return subprocess.check_output(["git", "-C", str(repo), *arguments], text=True).strip()


@pytest.fixture
def snapshot_repo(tmp_path):
    repo = tmp_path / "repo"
    (repo / "data/gold").mkdir(parents=True)
    (repo / "docs").mkdir()
    (repo / "data/gold/table.parquet").write_bytes(b"versioned Gold fixture")
    (repo / "docs/diccionario-datos.md").write_text("dictionary\n", encoding="utf-8")
    (repo / ".gitignore").write_text("data/gold/ignored*\n", encoding="utf-8")
    git(repo, "init", "-q")
    git(repo, "add", ".")
    git(repo, "-c", "user.name=Test", "-c", "user.email=test@example.invalid", "commit", "-qm", "snapshot")
    return repo, git(repo, "rev-parse", "HEAD")


def run_guard(repo, sha, identifier):
    step = next(step for step in workflow()["jobs"]["validate"]["steps"] if step.get("id") == identifier)
    return subprocess.run(
        ["bash", "--noprofile", "--norc", "-e", "-o", "pipefail", "-c", step["run"]],
        cwd=repo, env={**os.environ, "REFRESH_SHA": sha}, capture_output=True, text=True,
    )


@pytest.mark.parametrize("identifier", ["snapshot_before", "snapshot_after"])
@pytest.mark.parametrize("mutation", ["none", "sha", "edit", "staged", "add", "ignored", "delete", "symlink", "dictionary"])
def test_actual_snapshot_shell_rejects_different_sha_inventory_and_bytes(snapshot_repo, identifier, mutation):
    repo, sha = snapshot_repo
    table = repo / "data/gold/table.parquet"
    if mutation == "sha":
        sha = "0" * 40
    elif mutation in {"edit", "staged"}:
        table.write_bytes(b"changed")
        if mutation == "staged":
            git(repo, "add", "data/gold/table.parquet")
    elif mutation in {"add", "ignored"}:
        (table.parent / f"{mutation}.parquet").write_bytes(b"unvalidated")
    elif mutation == "delete":
        table.unlink()
    elif mutation == "symlink":
        table.unlink()
        table.symlink_to(repo / "docs/diccionario-datos.md")
    elif mutation == "dictionary":
        (repo / "docs/diccionario-datos.md").write_text("changed\n", encoding="utf-8")
    result = run_guard(repo, sha, identifier)
    assert (result.returncode == 0) == (mutation == "none"), result.stdout + result.stderr


def test_inventory_command_failure_is_not_mistaken_for_empty_inventory(snapshot_repo, tmp_path, monkeypatch):
    repo, sha = snapshot_repo
    real_git = shutil.which("git")
    assert real_git
    binary = tmp_path / "bin"
    binary.mkdir()
    wrapper = binary / "git"
    wrapper.write_text(
        '#!/bin/sh\nif [ "$1" = "ls-files" ]; then exit 1; fi\n'
        + f'exec {shlex.quote(real_git)} "$@"\n', encoding="utf-8",
    )
    wrapper.chmod(0o755)
    monkeypatch.setenv("PATH", str(binary) + os.pathsep + os.environ["PATH"])
    assert run_guard(repo, sha, "snapshot_before").returncode != 0


def test_gold_changed_during_stage8_is_not_covered_by_earlier_ci(snapshot_repo):
    repo, sha = snapshot_repo
    assert run_guard(repo, sha, "snapshot_before").returncode == 0
    (repo / "data/gold/table.parquet").write_bytes(b"changed after CI")
    assert run_guard(repo, sha, "snapshot_after").returncode != 0
    trace, _ = simulate(workflow(), overrides={"snapshot_after": "failure"})
    assert "failure_issue" in trace and "stop_on_failure" in trace and "commit" not in trace


def gold_fingerprint(directory):
    result = {}
    for path in directory.rglob("*"):
        if path.is_file():
            with path.open("rb") as stream:
                result[path.relative_to(directory).as_posix()] = hashlib.file_digest(stream, "sha256").hexdigest()
    return result


def test_real_stage8_reports_are_temporary_and_gold_is_unchanged(tmp_path, monkeypatch):
    from src.config import PATHS
    from src.dashboard import validate_stage8 as stage8

    before = gold_fingerprint(PATHS.gold)
    monkeypatch.setattr(stage8, "PATHS", SimpleNamespace(root=ROOT, gold=PATHS.gold, quality=tmp_path))
    summary = stage8.validate_stage8()
    assert summary["all_passed"] and summary["passed"] == summary["total"] == 8
    assert {path.name for path in tmp_path.iterdir()} == {
        "stage8_acceptance.json", "stage8_acceptance_checks.parquet",
    }
    assert gold_fingerprint(PATHS.gold) == before
