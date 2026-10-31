"""Missing, skipped and failed jobs must never make required checks green."""

import copy
import json
from pathlib import Path

import pytest
import yaml

from scripts.check_ci_jobs import GATES, check, main


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
    monkeypatch.setenv("CI_REQUIRED_RESULTS", json.dumps({name: {"result": "success"} for name in GATES["test"]}))
    assert main(["test"]) == 0


def test_actual_dag_runs_preflights_before_both_expensive_suites():
    workflow = yaml.safe_load((ROOT / ".github/workflows/ci.yml").read_text())
    jobs = workflow["jobs"]
    for gate in ("test", "web"):
        assert set(jobs[gate]["needs"]) == GATES[gate]
        assert "always()" in jobs[gate]["if"]
        assert any(f"scripts/check_ci_jobs.py {gate}" in step.get("run", "") for step in jobs[gate]["steps"])
    for name in ("public-tests", "web-checks"):
        assert set(jobs[name]["needs"]) == GATES["test"] - {"public-tests"}
        assert "if" not in jobs[name]  # Normal success-only needs semantics.
    assert "--fixture-only" not in str(jobs)
    assert workflow["permissions"] == {"contents": "read"}
    assert all("permissions" not in job for job in jobs.values())


def test_shadow_plan_never_drives_a_job_condition_or_pytest_selection():
    jobs = yaml.safe_load((ROOT / ".github/workflows/ci.yml").read_text())["jobs"]
    assert "outputs" not in jobs["change-plan"]
    for name, job in jobs.items():
        assert "recommended" not in job.get("if", "")
        if name != "change-plan":
            assert "change-plan.json" not in str(job)
    script = "\n".join(step.get("run", "") for step in jobs["public-tests"]["steps"])
    assert '-m "not local_data and not browser"' in script
    assert "-n 2 --dist=loadfile --max-worker-restart=0" in script


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
    assert ci["env"] == pages["env"]


def test_artifacts_are_attempt_scoped_and_required_preflight_reports_cannot_disappear():
    jobs = yaml.safe_load((ROOT / ".github/workflows/ci.yml").read_text())["jobs"]
    for name, job in jobs.items():
        for step in job.get("steps", []):
            if step.get("uses") == "actions/upload-artifact@v4":
                assert "github.run_attempt" in step["with"]["name"]
                if name in {"change-plan", "pages-preflight", "docker-preflight"}:
                    assert step["with"]["if-no-files-found"] == "error"


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
    assert pages["jobs"]["ci"] == {"uses": "./.github/workflows/ci.yml"}
    assert "ci" in pages["jobs"]["deploy"]["needs"]
    assert "if" not in pages["jobs"]["deploy"]  # No always()/skipped bypass.
