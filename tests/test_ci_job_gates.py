"""Missing, skipped and failed jobs must never make required checks green."""

import copy
import json
import os
import subprocess
from pathlib import Path

import pytest
import yaml

from scripts.check_ci_jobs import GATES, WAIVED, check, main


ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("gate", ["test", "web"])
def test_gate_requires_every_component(gate):
    good = {name: {"result": "success"} for name in GATES[gate]}
    assert check(gate, good) == []
    for name in good:
        for conclusion in ("failure", "cancelled", "skipped", "neutral", None):
            bad = copy.deepcopy(good)
            bad[name]["result"] = conclusion
            assert check(gate, bad), (name, conclusion)
        assert check(gate, {key: value for key, value in good.items() if key != name})
    assert check(gate, {**good, "unexpected": {"result": "success"}})
    assert check(gate, {})
    assert check(gate, [])


@pytest.mark.parametrize("value", ["null", "{}", "[]", "not json"])
def test_cli_rejects_invalid_or_empty_results(monkeypatch, value):
    monkeypatch.setenv("CI_REQUIRED_RESULTS", value)
    with pytest.raises(SystemExit) as failure:
        main(["test"])
    assert failure.value.code == 1


def test_cli_success_uses_json_data_instead_of_shell(monkeypatch):
    results = {name: {"result": "success"} for name in GATES["test"]}
    results["change-plan"]["outputs"] = {"execution": "full"}
    monkeypatch.setenv("CI_REQUIRED_RESULTS", json.dumps(results))
    assert main(["test"]) == 0


@pytest.mark.parametrize("outputs", [None, [], "full", 1, {}, {"execution": "web_only"}])
def test_cli_reports_invalid_selector_outputs_as_closed_gate(monkeypatch, outputs):
    results = {name: {"result": "success"} for name in GATES["test"]}
    results["change-plan"]["outputs"] = outputs
    monkeypatch.setenv("CI_REQUIRED_RESULTS", json.dumps(results))
    with pytest.raises(SystemExit) as failure:
        main(["test"])
    assert failure.value.code == 1


@pytest.mark.parametrize("execution", ["docs_only", "web_only"])
@pytest.mark.parametrize("gate", ["test", "web"])
def test_only_proven_omissions_are_allowed_and_other_results_fail(gate, execution):
    good = {
        name: {"result": "skipped" if name in WAIVED[execution] else "success"}
        for name in GATES[gate]
    }
    assert check(gate, good, execution=execution) == []
    for name in good:
        for result in ("failure", "cancelled", "neutral", None):
            bad = copy.deepcopy(good)
            bad[name]["result"] = result
            assert check(gate, bad, execution=execution), (name, result)
        bad = copy.deepcopy(good)
        bad[name]["result"] = "success" if good[name]["result"] == "skipped" else "skipped"
        assert check(gate, bad, execution=execution)
        assert check(gate, {key: value for key, value in good.items() if key != name}, execution=execution)
    assert check(gate, good, execution="invented")


@pytest.mark.parametrize("force_full", ["false", "true"])
@pytest.mark.parametrize("event", ["pull_request", "push", "workflow_call", ""])
@pytest.mark.parametrize("gate", ["test", "web"])
def test_cli_recomputes_checkout_profile_and_rejects_disagreement(tmp_path, monkeypatch, event, gate, force_full):
    from tests.test_ci_change_plan import commit, git, write

    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init", "-q")
    write(repo, "README.md", "base\n")
    base = commit(repo)
    write(repo, "web/src/main.ts", "export const answer = 42;\n")
    head = commit(repo)
    monkeypatch.chdir(repo)
    monkeypatch.setenv("CI_PLAN_BASE", base)
    monkeypatch.setenv("CI_PLAN_HEAD", head)
    monkeypatch.setenv("CI_PLAN_EVENT", event)
    monkeypatch.setenv("CI_PLAN_FORCE_FULL", force_full)
    expected = "web_only" if event == "pull_request" and force_full == "false" else "full"
    results = {
        name: {"result": "skipped" if name in WAIVED[expected] else "success"}
        for name in GATES[gate]
    }
    results["change-plan"]["outputs"] = {"execution": expected}
    monkeypatch.setenv("CI_REQUIRED_RESULTS", json.dumps(results))
    assert main([gate]) == 0
    for reported in ("docs_only", "invented", "", None):
        results["change-plan"]["outputs"]["execution"] = reported
        monkeypatch.setenv("CI_REQUIRED_RESULTS", json.dumps(results))
        with pytest.raises(SystemExit) as failure:
            main([gate])
        assert failure.value.code == 1
    # A stale SHA must fail rather than authorize skips from the selector.
    results["change-plan"]["outputs"]["execution"] = "web_only"
    monkeypatch.setenv("CI_REQUIRED_RESULTS", json.dumps(results))
    monkeypatch.setenv("CI_PLAN_HEAD", base)
    with pytest.raises(SystemExit):
        main([gate])


def test_actual_dag_preserves_required_gates_and_profile_prerequisites():
    workflow = yaml.safe_load((ROOT / ".github/workflows/ci.yml").read_text())
    jobs = workflow["jobs"]
    for gate in ("test", "web"):
        assert set(jobs[gate]["needs"]) == GATES[gate]
        assert "always()" in jobs[gate]["if"]
        assert any(f"scripts/check_ci_jobs.py {gate}" in step.get("run", "") for step in jobs[gate]["steps"])
        checkout = next(step for step in jobs[gate]["steps"] if "checkout@" in step.get("uses", ""))
        assert checkout["with"]["fetch-depth"] == 0
        environment = next(step["env"] for step in jobs[gate]["steps"] if "CI_REQUIRED_RESULTS" in step.get("env", {}))
        assert environment["CI_PLAN_HEAD"] == "${{ github.sha }}"
        assert environment["CI_PLAN_EVENT"] == "${{ github.event_name }}"
    assert set(jobs["public-tests"]["needs"]) == {"change-plan", "static"}
    assert jobs["public-tests"]["if"] == "${{ needs.change-plan.outputs.execution == 'full' }}"
    assert set(jobs["web-checks"]["needs"]) == {"change-plan", "static"}
    assert jobs["web-checks"]["if"] == "${{ needs.change-plan.outputs.execution != 'docs_only' }}"
    for name in ("docker-preflight", "chat-runtime"):
        assert jobs[name]["needs"] == ["change-plan"]
        assert jobs[name]["if"] == "${{ needs.change-plan.outputs.execution == 'full' }}"
    assert "--fixture-only" not in str(jobs)
    assert workflow["permissions"] == {"contents": "read"}
    assert all("permissions" not in job for job in jobs.values())


def test_opt_in_plan_retains_full_public_selection_and_lightweight_controls():
    jobs = yaml.safe_load((ROOT / ".github/workflows/ci.yml").read_text())["jobs"]
    assert jobs["change-plan"]["outputs"] == {"execution": "${{ steps.plan.outputs.execution }}"}
    plan = next(step for step in jobs["change-plan"]["steps"] if step.get("id") == "plan")
    assert "--enable-selection" in plan["run"] and '--event "$PLAN_EVENT"' in plan["run"]
    assert plan["env"]["PLAN_HEAD"] == "${{ github.sha }}"
    assert plan["env"]["PLAN_FORCE_FULL"] == "${{ inputs.force_full || false }}"
    for name, job in jobs.items():
        assert "recommended" not in job.get("if", "")
        if name != "change-plan":
            assert "change-plan.json" not in str(job)
    script = "\n".join(step.get("run", "") for step in jobs["public-tests"]["steps"])
    assert '-m "not local_data and not browser"' in script
    assert "-n 2 --dist=loadfile --max-worker-restart=0" in script
    controls = "\n".join(step.get("run", "") for step in jobs["static"]["steps"])
    for name in ("test_ci_change_plan.py", "test_ci_job_gates.py", "test_pages_ci_evidence.py", "test_repo_budgets.py"):
        assert name in controls
    assert "if" not in jobs["static"]


def test_pages_profile_matches_deployment_and_is_isolated_per_step():
    from scripts.check_ci_pages import INSTALL, VERIFY

    ci = yaml.safe_load((ROOT / ".github/workflows/ci.yml").read_text())
    pages = yaml.safe_load((ROOT / ".github/workflows/pages.yml").read_text())
    install = next(s["run"] for s in pages["jobs"]["verify"]["steps"] if s.get("name") == "Install locked dependencies")
    verify = next(s["run"] for s in pages["jobs"]["verify"]["steps"] if "check_pages_publication.py" in s.get("run", ""))
    assert install.strip() == " ".join(INSTALL)
    assert verify.strip() == " ".join(VERIFY)
    step = next(s for s in ci["jobs"]["pages-preflight"]["steps"] if "check_ci_pages.py" in s.get("run", ""))
    assert "runner.temp" in step["env"]["UV_PROJECT_ENVIRONMENT"]
    assert '--base "$PUBLICATION_BASE_COMMIT"' in step["run"]
    assert "--verify-published-base" in step["run"]
    assert ci["jobs"]["pages-preflight"]["needs"] == ["change-plan"]
    assert ci["env"] == pages["env"]


def test_artifacts_are_attempt_scoped_and_required_preflight_reports_cannot_disappear():
    jobs = yaml.safe_load((ROOT / ".github/workflows/ci.yml").read_text())["jobs"]
    for name, job in jobs.items():
        for step in job.get("steps", []):
            if step.get("uses") == "actions/upload-artifact@v4":
                assert "github.run_attempt" in step["with"]["name"]
                if name in {"change-plan", "pages-preflight", "docker-preflight"}:
                    assert step["with"]["if-no-files-found"] == "error"


@pytest.mark.parametrize(
    "probes,download_code,deps_code,expected_calls,succeeds",
    [
        ([0], 0, 0, ["download", "probe"], True),
        ([1, 0], 0, 0, ["download", "probe", "dependencies", "probe"], True),
        ([1, 1], 0, 0, ["download", "probe", "dependencies", "probe"], False),
        ([0], 1, 0, ["download"], False),
        ([1, 0], 0, 1, ["download", "probe", "dependencies"], False),
    ],
)
def test_browser_preparation_only_installs_system_packages_after_failed_probe(
    tmp_path, probes, download_code, deps_code, expected_calls, succeeds,
):
    workflow = yaml.safe_load((ROOT / ".github/workflows/ci.yml").read_text())
    step = next(s for s in workflow["jobs"]["web-checks"]["steps"] if "probe pinned" in s.get("name", ""))
    fake_uv = tmp_path / "uv"
    fake_uv.write_text('''#!/usr/bin/env python3
import json, os, sys
from pathlib import Path
log = Path(os.environ["BROWSER_CALLS"])
calls = json.loads(log.read_text()) if log.exists() else []
args = sys.argv[1:]
if args == ["run", "--no-sync", "playwright", "install", "--only-shell", "chromium"]:
    kind, code = "download", int(os.environ["DOWNLOAD_CODE"])
elif args == ["run", "--no-sync", "playwright", "install-deps", "chromium"]:
    kind, code = "dependencies", int(os.environ["DEPS_CODE"])
elif args == ["run", "--no-sync", "python", "-"]:
    kind = "probe"
    assert "chromium.launch(headless=True" in sys.stdin.read()
    code = json.loads(os.environ["PROBE_CODES"])[calls.count("probe")]
else:
    raise AssertionError(args)
log.write_text(json.dumps(calls + [kind]))
raise SystemExit(code)
''')
    fake_uv.chmod(0o755)
    calls_path = tmp_path / "calls.json"
    result = subprocess.run(
        ["bash", "-e", "-o", "pipefail", "-c", step["run"]], capture_output=True, text=True,
        env={
            **os.environ, "PATH": str(tmp_path) + os.pathsep + os.environ["PATH"],
            "BROWSER_CALLS": str(calls_path), "PROBE_CODES": json.dumps(probes),
            "DOWNLOAD_CODE": str(download_code), "DEPS_CODE": str(deps_code),
        },
    )
    assert json.loads(calls_path.read_text()) == expected_calls, result.stderr
    assert (result.returncode == 0) == succeeds, result.stderr


def test_narrow_push_dedup_only_applies_where_pages_runs_full_ci():
    ci = yaml.safe_load((ROOT / ".github/workflows/ci.yml").read_text())
    pages = yaml.safe_load((ROOT / ".github/workflows/pages.yml").read_text())
    ci_events = ci.get("on", ci.get(True))
    page_events = pages.get("on", pages.get(True))
    assert set(ci_events["push"]["paths-ignore"]) == set(page_events["push"]["paths"])
    assert ci_events["push"]["branches"] == page_events["push"]["branches"] == ["master"]
    assert "paths" not in ci_events["pull_request"]
    assert "edited" in ci_events["pull_request"]["types"]
    assert "workflow_call" in ci_events
    assert ci_events["workflow_call"]["inputs"]["force_full"] == {"type": "boolean", "default": True}
    pages_ci = pages["jobs"]["ci"]
    assert pages_ci["uses"] == "./.github/workflows/ci.yml"
    assert pages_ci["needs"] == ["ci-evidence"]
    assert pages_ci["if"] == "${{ always() && needs.ci-evidence.outputs.reuse != 'true' }}"
    assert "ci-gate" in pages["jobs"]["deploy"]["needs"]
    assert "if" not in pages["jobs"]["deploy"]  # No always()/skipped bypass.
