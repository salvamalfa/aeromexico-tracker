from __future__ import annotations

import subprocess

from scripts import pages_ci_evidence as evidence

MERGE = "a" * 40
SOURCE = "b" * 40
BASE = "c" * 40


def mock_git(monkeypatch, *, same_tree: bool = True) -> None:
    values = {
        ("rev-parse", "HEAD"): MERGE,
        ("rev-list", "--parents", "-n", "1", MERGE): f"{MERGE} {BASE} {SOURCE}",
        ("rev-parse", f"{MERGE}^{{tree}}"): "tree-1",
        ("rev-parse", f"{SOURCE}^{{tree}}"): "tree-1" if same_tree else "tree-2",
    }
    monkeypatch.setattr(evidence, "git", lambda *args: values[args])


def mock_api(monkeypatch, *, test: str = "success", web: str = "success", latest: str = "success") -> None:
    calls = []

    def api(path: str) -> dict:
        calls.append(path)
        if "/pulls?" in path:
            return [
                {
                    "head": {"sha": SOURCE},
                    "base": {"ref": "master", "sha": BASE},
                    "merge_commit_sha": MERGE,
                    "merged_at": "2026-11-05T00:00:00Z",
                }
            ]
        if "/workflows/ci.yml/runs?" in path:
            return {
                "workflow_runs": [
                    {
                        "head_sha": SOURCE,
                        "event": "pull_request",
                        "path": ".github/workflows/ci.yml",
                        "created_at": "2026-11-05T00:00:00Z",
                        "run_attempt": 1,
                        "id": 42,
                        "status": "completed",
                        "conclusion": latest,
                    }
                ]
            }
        return {
            "jobs": [
                {"name": "test", "status": "completed", "conclusion": test},
                {"name": "web", "status": "completed", "conclusion": web},
            ]
        }

    monkeypatch.setattr(evidence, "gh_json", api)


def test_reuses_full_ci_only_for_identical_tree_and_green_required_jobs(monkeypatch) -> None:
    mock_git(monkeypatch)
    mock_api(monkeypatch)

    result = evidence.assess(MERGE, "salvamalfa/aeromexico-tracker")

    assert result == {
        "reuse": True,
        "reason": "same_tree_and_successful_pr_ci",
        "source_sha": SOURCE,
        "workflow_run_id": 42,
    }


def test_changed_integration_tree_uses_full_fallback(monkeypatch) -> None:
    mock_git(monkeypatch, same_tree=False)

    result = evidence.assess(MERGE, "salvamalfa/aeromexico-tracker")

    assert result == {"reuse": False, "reason": "integration_tree_differs_from_tested_commit"}


def test_failed_required_check_uses_full_fallback(monkeypatch) -> None:
    mock_git(monkeypatch)
    mock_api(monkeypatch, web="failure")

    result = evidence.assess(MERGE, "salvamalfa/aeromexico-tracker")

    assert result == {"reuse": False, "reason": "required_job_web_not_successful"}


def test_latest_failed_ci_run_supersedes_an_older_success(monkeypatch) -> None:
    mock_git(monkeypatch)
    mock_api(monkeypatch, latest="failure")

    result = evidence.assess(MERGE, "salvamalfa/aeromexico-tracker")

    assert result == {"reuse": False, "reason": "latest_pr_ci_not_successful"}


def test_non_merge_commit_uses_full_fallback(monkeypatch) -> None:
    monkeypatch.setattr(
        evidence, "git", lambda *args: MERGE if args == ("rev-parse", "HEAD") else f"{MERGE} {BASE}"
    )

    result = evidence.assess(MERGE, "salvamalfa/aeromexico-tracker")

    assert result == {"reuse": False, "reason": "not_two_parent_merge"}


def test_ci_from_unmerged_or_non_master_pr_is_not_reused(monkeypatch) -> None:
    mock_git(monkeypatch)
    mock_api(monkeypatch)
    original = evidence.gh_json

    def api(path: str) -> dict:
        if "/pulls?" in path:
            return [{"head": {"sha": SOURCE}, "base": {"ref": "feature", "sha": BASE}}]
        return original(path)

    monkeypatch.setattr(evidence, "gh_json", api)

    result = evidence.assess(MERGE, "salvamalfa/aeromexico-tracker")

    assert result == {"reuse": False, "reason": "no_merged_master_pr_for_exact_tree"}


def test_ambiguous_pr_association_uses_full_fallback(monkeypatch) -> None:
    mock_git(monkeypatch)
    mock_api(monkeypatch)
    original = evidence.gh_json

    def api(path: str) -> dict:
        if "/pulls?" in path:
            return original(path) + [
                {
                    "head": {"sha": SOURCE},
                    "base": {"ref": "feature", "sha": BASE},
                    "merge_commit_sha": None,
                    "merged_at": None,
                }
            ]
        return original(path)

    monkeypatch.setattr(evidence, "gh_json", api)

    result = evidence.assess(MERGE, "salvamalfa/aeromexico-tracker")

    assert result == {"reuse": False, "reason": "ambiguous_pull_request_association"}


def test_unavailable_github_evidence_uses_full_fallback(monkeypatch) -> None:
    mock_git(monkeypatch)

    def unavailable(_path: str) -> dict:
        raise subprocess.CalledProcessError(1, ["gh", "api"])

    monkeypatch.setattr(evidence, "gh_json", unavailable)

    result = evidence.assess(MERGE, "salvamalfa/aeromexico-tracker")

    assert result == {"reuse": False, "reason": "evidence_unavailable_or_invalid"}


def test_gate_accepts_only_successful_reuse_or_full_fallback() -> None:
    assert evidence.gate_result("true", "success", "skipped") == (
        True,
        "Pages reuses successful CI from an identical integration tree.",
    )
    assert evidence.gate_result("false", "success", "success") == (
        True,
        "Pages passed the full CI fallback.",
    )
    assert evidence.gate_result("false", "success", "failure")[0] is False
    assert evidence.gate_result("true", "failure", "success")[0] is False
