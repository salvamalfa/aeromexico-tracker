"""Protect historical evidence and distinguish checked inventory from UI counts."""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

import pytest

from scripts.audit.gold_exposure import SEARCH_ROOTS, dependency_references

ROOT = Path(__file__).resolve().parents[1]


def test_gold_audit_preserves_existing_cut(tmp_path):
    historical = tmp_path / "historical"
    historical.mkdir()
    evidence = historical / "summary.json"
    evidence.write_text('{"historical": true}\n')
    before = evidence.read_bytes()
    run = subprocess.run(
        [sys.executable, "-m", "scripts.audit.gold_exposure", "--out", str(historical)],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert run.returncode != 0
    assert "preserve the previous audit cut" in run.stderr
    assert evidence.read_bytes() == before
    assert list(historical.iterdir()) == [evidence]


def test_gold_audit_counts_actual_tables_and_leaves_private_unknown(tmp_path):
    out = tmp_path / "fresh"
    run = subprocess.run(
        [sys.executable, "-m", "scripts.audit.gold_exposure", "--out", str(out)],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert run.returncode == 0, (
        f"Gold audit exited {run.returncode}\nstdout:\n{run.stdout}\nstderr:\n{run.stderr}"
    )
    summary = json.loads((out / "summary.json").read_text())
    tracked = subprocess.check_output(["git", "ls-files", "data/gold"], cwd=ROOT, text=True)
    assert summary["public_tables"] == sum(p.endswith(".parquet") for p in tracked.splitlines())
    assert summary["private_flight_gold"]["count"] is None
    assert summary["private_flight_gold"]["status"] == "not_checked"
    # The airport JSON remains exported, but its removed view cannot add two UI tables.
    assert summary["market_direct"] == summary["baseline_direct"]
    assert summary["broad_use"] == summary["baseline_direct"] + summary["baseline_context_or_validation"]


def test_gold_audit_rejects_unverified_private_input(tmp_path):
    private = tmp_path / "private"
    private.mkdir()
    subprocess.run(["git", "init", "--quiet", str(private)], check=True)
    # No private content is copied: this checkout cannot supply committed Gold.
    out = tmp_path / "rejected"
    run = subprocess.run(
        [
            sys.executable,
            "-m",
            "scripts.audit.gold_exposure",
            "--out",
            str(out),
            "--private-root",
            str(private),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert run.returncode != 0
    assert not (out / "summary.json").exists()
    assert not (out / "tables.csv").exists()


def test_dependency_search_needs_only_git_and_keeps_working_tree_candidates(tmp_path, monkeypatch):
    subprocess.run(["git", "init", "--quiet", str(tmp_path)], check=True)
    for relative in SEARCH_ROOTS:
        (tmp_path / relative).mkdir(parents=True, exist_ok=True)
    tracked = tmp_path / "src/tracked.py"
    tracked.write_text("fact_fixture\n", encoding="utf-8")
    subprocess.run(["git", "add", "src/tracked.py"], cwd=tmp_path, check=True)
    tracked.write_text("fact_fixture\nfact_fixture\n", encoding="utf-8")
    (tmp_path / "src/candidate.py").write_text("fact_fixture\n", encoding="utf-8")
    (tmp_path / ".agents/skills/SKILL.md").write_text("fact_fixture\n", encoding="utf-8")
    (tmp_path / "src/other.py").write_text("fact_fixture_suffix\n", encoding="utf-8")
    (tmp_path / ".gitignore").write_text("src/ignored.py\n", encoding="utf-8")
    (tmp_path / "src/ignored.py").write_text("fact_fixture\n", encoding="utf-8")
    actual_run = subprocess.run

    def git_only(command, **kwargs):
        assert command[0] == "git", "No optional search executable may be required"
        return actual_run(command, **kwargs)

    monkeypatch.setattr("scripts.audit.gold_exposure.subprocess.run", git_only)
    references = dependency_references(tmp_path, "fact_fixture")
    assert set(references) == {
        "src/tracked.py:1:fact_fixture",
        "src/tracked.py:2:fact_fixture",
        "src/candidate.py:1:fact_fixture",
        ".agents/skills/SKILL.md:1:fact_fixture",
    }
    assert dependency_references(tmp_path, "fact_missing") == []


def test_dependency_search_does_not_hide_git_errors(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "scripts.audit.gold_exposure.subprocess.run",
        lambda *args, **kwargs: subprocess.CompletedProcess(args[0], 2, stdout="", stderr="search denied"),
    )
    with pytest.raises(RuntimeError, match="Dependency search failed: search denied"):
        dependency_references(tmp_path, "fact_fixture")
