"""Reuse PR CI on Pages only when the integration commit has the exact tree.

Any missing, stale, or ambiguous evidence selects the existing full CI fallback.
The script emits only a boolean and a short reason to GitHub Actions outputs.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path

SHA = re.compile(r"[0-9a-f]{40}\Z")
REPOSITORY = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+\Z")
REQUIRED_JOBS = ("test", "web")


def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], text=True, stderr=subprocess.DEVNULL).strip()


def gh_json(path: str) -> dict:
    result = subprocess.run(
        ["gh", "api", path],
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(result.stdout)


def _latest_run(runs: list[dict], source_sha: str) -> dict | None:
    candidates = [
        run
        for run in runs
        if run.get("head_sha") == source_sha
        and run.get("event") == "pull_request"
        and run.get("path") == ".github/workflows/ci.yml"
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda run: (run.get("created_at", ""), run.get("run_attempt", 0)))


def assess(merge_sha: str, repository: str) -> dict:
    """Return a fail-closed reuse decision using Git tree identity and CI jobs."""
    if not SHA.fullmatch(merge_sha) or not REPOSITORY.fullmatch(repository):
        return {"reuse": False, "reason": "invalid_event_identity"}
    try:
        if git("rev-parse", "HEAD") != merge_sha:
            return {"reuse": False, "reason": "checkout_sha_mismatch"}
        parents = git("rev-list", "--parents", "-n", "1", merge_sha).split()
        if len(parents) != 3 or parents[0] != merge_sha:
            return {"reuse": False, "reason": "not_two_parent_merge"}
        base_sha = parents[1]
        source_sha = parents[2]
        if not SHA.fullmatch(source_sha):
            return {"reuse": False, "reason": "invalid_source_sha"}
        if git("rev-parse", f"{merge_sha}^{{tree}}") != git("rev-parse", f"{source_sha}^{{tree}}"):
            return {"reuse": False, "reason": "integration_tree_differs_from_tested_commit"}

        pull_requests = gh_json(f"repos/{repository}/commits/{source_sha}/pulls?per_page=100")
        if not isinstance(pull_requests, list):
            return {"reuse": False, "reason": "invalid_pull_request_response"}
        # The workflow-run API does not reliably include its originating PR
        # number. Reuse is safe only when GitHub reports a single association
        # for this source SHA, so a run from another target branch cannot win.
        if len(pull_requests) != 1 or not isinstance(pull_requests[0], dict):
            return {"reuse": False, "reason": "ambiguous_pull_request_association"}
        pr = pull_requests[0]
        matching_pr = (
            pr.get("head", {}).get("sha") == source_sha
            and pr.get("base", {}).get("ref") == "master"
            and pr.get("base", {}).get("sha") == base_sha
            and pr.get("merge_commit_sha") == merge_sha
            and pr.get("merged_at")
        )
        if not matching_pr:
            return {"reuse": False, "reason": "no_merged_master_pr_for_exact_tree"}

        workflow_runs = gh_json(
            f"repos/{repository}/actions/workflows/ci.yml/runs?head_sha={source_sha}&event=pull_request&per_page=100"
        ).get("workflow_runs", [])
        if not isinstance(workflow_runs, list):
            return {"reuse": False, "reason": "invalid_workflow_run_response"}
        run = _latest_run(workflow_runs, source_sha)
        if run is None:
            return {"reuse": False, "reason": "no_pr_ci_for_exact_source_commit"}
        if run.get("status") != "completed" or run.get("conclusion") != "success":
            return {"reuse": False, "reason": "latest_pr_ci_not_successful"}
        run_id = run.get("id")
        if type(run_id) is not int:
            return {"reuse": False, "reason": "invalid_workflow_run_id"}
        jobs = gh_json(f"repos/{repository}/actions/runs/{run_id}/jobs?filter=latest&per_page=100").get(
            "jobs", []
        )
        if not isinstance(jobs, list):
            return {"reuse": False, "reason": "invalid_workflow_jobs_response"}
        for name in REQUIRED_JOBS:
            matches = [job for job in jobs if job.get("name") == name]
            if (
                len(matches) != 1
                or matches[0].get("status") != "completed"
                or matches[0].get("conclusion") != "success"
            ):
                return {"reuse": False, "reason": f"required_job_{name}_not_successful"}
        return {
            "reuse": True,
            "reason": "same_tree_and_successful_pr_ci",
            "source_sha": source_sha,
            "workflow_run_id": run_id,
        }
    except (
        OSError,
        subprocess.SubprocessError,
        ValueError,
        TypeError,
        KeyError,
        AttributeError,
        json.JSONDecodeError,
    ):
        return {"reuse": False, "reason": "evidence_unavailable_or_invalid"}


def write_outputs(result: dict, output_path: str | None) -> None:
    if not output_path:
        return
    with Path(output_path).open("a", encoding="utf-8") as stream:
        stream.write(f"reuse={'true' if result.get('reuse') else 'false'}\n")
        stream.write(f"reason={result.get('reason', 'unknown')}\n")
        if result.get("source_sha"):
            stream.write(f"source_sha={result['source_sha']}\n")
        if result.get("workflow_run_id"):
            stream.write(f"workflow_run_id={result['workflow_run_id']}\n")


def gate_result(reuse: str, evidence_result: str, fallback_result: str) -> tuple[bool, str]:
    if reuse == "true" and evidence_result == "success":
        return True, "Pages reuses successful CI from an identical integration tree."
    if reuse != "true" and fallback_result == "success":
        return True, "Pages passed the full CI fallback."
    return (
        False,
        f"CI gate closed: reuse={reuse == 'true'}, evidence={evidence_result}, fallback={fallback_result}",
    )


def main() -> int:
    if os.environ.get("PAGES_CI_MODE") == "gate":
        passed, message = gate_result(
            os.environ.get("REUSE", ""),
            os.environ.get("EVIDENCE_RESULT", ""),
            os.environ.get("FALLBACK_RESULT", ""),
        )
        print(message)
        return 0 if passed else 1
    result = assess(os.environ.get("GITHUB_SHA", ""), os.environ.get("GITHUB_REPOSITORY", ""))
    print(json.dumps(result, sort_keys=True))
    write_outputs(result, os.environ.get("GITHUB_OUTPUT"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
