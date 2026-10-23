"""Strict offline retention of the exact two reviewed carrier dossiers."""

from __future__ import annotations

import json
import re

from src.source_updates.calendar import local_time
from src.source_updates.collection import safe_workspace
from src.source_updates.primary_review import original
from src.source_updates.retained import digest, spec
from src.source_updates.retained import originals as retained_originals
from src.source_updates.retained import retain as retained_retain


def guard(workspace):
    if any(p.is_symlink() for p in [workspace, *workspace.parents]) or any(
        p.is_symlink() for p in workspace.rglob("*")
    ):
        raise ValueError("Carrier candidates cannot contain symlinks")


def inspect(root, product, selected):
    definition = spec(product)
    if not isinstance(selected, dict) or set(selected) != set(definition["roles"]):
        raise ValueError("Explicit complete carrier input roles required")
    if len(set(selected.values())) != len(selected):
        raise ValueError("Carrier roles must identify distinct originals")
    rows = [json.loads(s) for s in (root / "_manifest.jsonl").read_text(encoding="utf-8").splitlines()]
    for role, name in selected.items():
        found = [r for r in rows if r.get("source_file") == name]
        if len(found) != 1 or found[0].get("source_system") not in definition["roles"][role]:
            raise ValueError("Ambiguous/missing carrier original or source alias")
        row = found[0]
        if type(row.get("http_status")) is not int or row["http_status"] != 200:
            raise ValueError("Carrier certification requires an explicit successful HTTP capture")
        original(root, row)


def retain(workspace, source_root, product, selected, *, execute=False):
    guard(workspace)
    workspace = safe_workspace(workspace)
    inspect(source_root, product, selected)
    return retained_retain(workspace, source_root, product, selected, execute=execute)


def inputs(workspace, product, run_id, cutoff):
    guard(workspace)
    if not re.fullmatch(r"[a-f0-9]{32}", run_id):
        raise ValueError("An exact carrier retention receipt ID is required")
    path = workspace / "receipts" / f"retained-{run_id}.json"
    receipt = json.loads(path.read_text(encoding="utf-8"))
    for key, expected in dict(
        network_requests=0,
        paid_requests=0,
        new_source_capture=False,
        source_capture_dates_preserved=True,
        activation="none",
        publication="not_authorized",
    ).items():
        if type(receipt.get(key)) is not type(expected) or receipt[key] != expected:
            raise ValueError("Carrier acquisition receipt flags differ")
    if receipt.get("run_id") != run_id or local_time(receipt["retained_at"]) < max(
        local_time(r["downloaded_at"]) for r in receipt["originals"].values()
    ):
        raise ValueError("Carrier retention identity/chronology differs")
    result, receipt_hash = retained_originals(workspace, product, run_id, cutoff)
    inspect(workspace / "data/bronze", product, {k: r["source_file"] for k, (_, r) in result.items()})
    if receipt_hash != digest(path):
        raise ValueError("Carrier receipt changed during verification")
    return result, receipt_hash
