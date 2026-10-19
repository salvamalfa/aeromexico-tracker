"""Protect historical evidence and distinguish checked inventory from UI counts."""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

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
    subprocess.run(
        [sys.executable, "-m", "scripts.audit.gold_exposure", "--out", str(out)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
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
