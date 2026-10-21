"""Pinned verifier cohorts are provenance; every approval still replays in full."""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
from pathlib import Path

from . import manifest as manifests
from .approval_anchor import approval_implementation
from .records import ANALYSIS_MANIFEST_FIELDS, _analysis_manifest_entry, load_records

CONFIG = "config/publish/approval-cohorts.json"
ANCHOR = "config/publish/preserved-analysis.json"
SCHEMA = "analysis_approval_cohorts_v1"


def _git_bytes(repo, commit, name):
    result = subprocess.run(["git", "show", f"{commit}:{name}"], cwd=repo, capture_output=True)
    if result.returncode:
        raise ValueError(f"Missing committed approval provenance: {name}")
    return result.stdout


def _optional_config(repo, commit):
    exists = (
        subprocess.run(
            ["git", "cat-file", "-e", f"{commit}:{CONFIG}"], cwd=repo, capture_output=True
        ).returncode
        == 0
    )
    return _git_bytes(repo, commit, CONFIG) if exists else None


def _hex(value, length):
    return isinstance(value, str) and re.fullmatch(rf"[a-f0-9]{{{length}}}", value)


def _cohorts(raw):
    if raw is None:
        return []
    config = json.loads(raw)
    if set(config) != {"schema_version", "cohorts"} or config["schema_version"] != SCHEMA:
        raise ValueError("Invalid approval cohort schema")
    if not isinstance(config["cohorts"], list):
        raise ValueError("Approval cohorts must be a list")
    seen = set()
    for cohort in config["cohorts"]:
        if set(cohort) != {"implementation_commit", "analysis_manifest", "files"}:
            raise ValueError("Invalid approval cohort fields")
        if not _hex(cohort["implementation_commit"], 40):
            raise ValueError("Invalid cohort implementation commit")
        entries = cohort["analysis_manifest"]
        if not isinstance(entries, list) or not entries:
            raise ValueError("Empty approval cohort")
        paths = set()
        for entry in entries:
            fields = set(ANALYSIS_MANIFEST_FIELDS)
            if "entity_key" in entry:
                fields.add("entity_key")
            if set(entry) != fields:
                raise ValueError("Incomplete cohort approval identity")
            identity = manifests.analysis_identity(entry)
            if identity in seen:
                raise ValueError("Duplicate or overlapping approval cohort")
            seen.add(identity)
            if any(not _hex(entry[k], 64) for k in ANALYSIS_MANIFEST_FIELDS if k != "period_id"):
                raise ValueError("Invalid cohort approval digest")
            paths.add("data/v1/" + manifests.analysis_relative_path(entry).as_posix())
        files = cohort["files"]
        if not isinstance(files, list) or len(files) != len(paths):
            raise ValueError("Missing cohort thesis file")
        found = set()
        for row in files:
            if (
                set(row) != {"path", "sha256", "bytes"}
                or row["path"] not in paths
                or row["path"] in found
                or not _hex(row["sha256"], 64)
                or type(row["bytes"]) is not int
                or row["bytes"] < 0
            ):
                raise ValueError("Invalid or duplicate cohort thesis file")
            found.add(row["path"])
    return config["cohorts"]


def _require_working(repo, name, raw):
    path = repo / name
    if path.is_symlink() or (path.read_bytes() if path.exists() else None) != raw:
        raise ValueError("Approval cohort provenance changed outside its committed edition")


def _ancestor(repo, code, commit):
    if subprocess.run(
        ["git", "merge-base", "--is-ancestor", code, commit], cwd=repo, capture_output=True
    ).returncode:
        raise ValueError("Cohort implementation is outside trusted publication history")


def approval_plan(repo: Path, trusted_commit: str, baseline: dict, *, pending=None):
    """Partition an exact trusted publication, optionally adding one reviewed pin.

    A pending pin is read from committed HEAD, never from an uncommitted file.
    It must be the sole append to the trusted config and match the new approved
    payload. Existing publications always use the trusted commit's config.
    """
    repo = Path(repo)
    original = json.loads(_git_bytes(repo, trusted_commit, "site/publication_manifest.json"))
    if original != baseline:
        raise ValueError("Cohort baseline differs from trusted publication")
    trusted_raw = _optional_config(repo, trusted_commit)
    trusted_cohorts = _cohorts(trusted_raw)
    if pending is None:
        _require_working(repo, CONFIG, trusted_raw)
        configured = trusted_cohorts
        pin_commit = trusted_commit
    else:
        pin_commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo, text=True).strip()
        raw = _optional_config(repo, pin_commit)
        _require_working(repo, CONFIG, raw)
        configured = _cohorts(raw)
        if len(configured) != len(trusted_cohorts) + 1 or configured[:-1] != trusted_cohorts:
            raise ValueError("Quarterly publication requires exactly one new cohort pin")
        expected = {"analysis_manifest": [pending["entry"]], "files": [pending["file"]]}
        if any(configured[-1][key] != value for key, value in expected.items()):
            raise ValueError("Pending cohort differs from the exact new thesis")
        _ancestor(repo, trusted_commit, configured[-1]["implementation_commit"])
    _ancestor(repo, trusted_commit, pin_commit)
    entries = list(baseline["analysis_manifest"])
    files = list(baseline["files"])
    if pending is not None:
        entries.append(pending["entry"])
        files.append(pending["file"])
    by_identity = {}
    for entry in entries:
        identity = manifests.analysis_identity(entry)
        if identity in by_identity:
            raise ValueError("Duplicate published thesis identity")
        by_identity[identity] = entry
    groups = []
    anchor_raw = _git_bytes(repo, trusted_commit, ANCHOR)
    _require_working(repo, ANCHOR, anchor_raw)
    anchor = json.loads(anchor_raw)
    anchored = json.loads(_git_bytes(repo, anchor["published_site_commit"], "site/publication_manifest.json"))
    historical = anchored["analysis_manifest"]
    if any(by_identity.get(manifests.analysis_identity(e)) != e for e in historical):
        raise ValueError("Historical approval cohort changed")
    subset = {**baseline, "analysis_manifest": historical}
    code = approval_implementation(repo, trusted_commit, subset)
    groups.append(
        {
            "implementation_commit": code,
            "analysis_manifest": historical,
            "files": [
                r
                for r in files
                if r["path"]
                in {"data/v1/" + manifests.analysis_relative_path(e).as_posix() for e in historical}
            ],
        }
    )
    covered = {manifests.analysis_identity(e) for e in historical}
    for index, cohort in enumerate(configured):
        history = trusted_commit if index < len(trusted_cohorts) else pin_commit
        _ancestor(repo, cohort["implementation_commit"], history)
        for entry in cohort["analysis_manifest"]:
            identity = manifests.analysis_identity(entry)
            if identity in covered or by_identity.get(identity) != entry:
                raise ValueError("Unmatched or overlapping approval cohort")
            covered.add(identity)
        for row in cohort["files"]:
            if [r for r in files if r["path"] == row["path"]] != [row]:
                raise ValueError("Cohort payload hash or size differs from publication")
        groups.append(cohort)
    if covered != set(by_identity):
        raise ValueError("Published thesis has no pinned approval cohort")
    # Read original public bytes from the trusted commit; the new bytes come
    # only from the current approved consumer payload supplied by the gate.
    payloads = {}
    for group in groups:
        for row in group["files"]:
            raw = (
                pending["bytes"]
                if pending is not None and row == pending["file"]
                else _git_bytes(repo, trusted_commit, "site/" + row["path"])
            )
            if len(raw) != row["bytes"] or hashlib.sha256(raw).hexdigest() != row["sha256"]:
                raise ValueError("Committed cohort payload differs from its pinned bytes")
            payloads[row["path"]] = json.loads(raw)
    return groups, payloads


def verify_approval_cohorts(record_paths, repo, trusted_commit, baseline, ledger_root, *, pending=None):
    """Replay each cohort's full ledger, sources, rendering and public payload."""
    from .frozen_data import verify_baseline_approvals

    groups, payloads = approval_plan(repo, trusted_commit, baseline, pending=pending)
    records = load_records(record_paths)
    selected = {
        (*manifests.analysis_identity(r["draft"]), r["version"]): path
        for r, path in zip(records, record_paths)
    }
    expected = {
        (*manifests.analysis_identity(e), e["version"])
        for group in groups
        for e in group["analysis_manifest"]
    }
    if set(selected) != expected:
        raise ValueError("Selected records differ from the exact approval cohorts")
    checked = []
    for group in groups:
        paths = [
            selected[(*manifests.analysis_identity(e), e["version"])] for e in group["analysis_manifest"]
        ]
        result = verify_baseline_approvals(
            paths, group["implementation_commit"], ledger_root, include_public_payloads=True
        )
        if [_analysis_manifest_entry(a) for a in result["authorized"]] != group["analysis_manifest"]:
            raise ValueError("Replayed approval differs from its pinned cohort")
        if len(result["payloads"]) != len(group["analysis_manifest"]):
            raise ValueError("Missing replayed cohort payload")
        for entry, authorized, payload in zip(
            group["analysis_manifest"], result["authorized"], result["payloads"]
        ):
            name = "data/v1/" + manifests.analysis_relative_path(entry).as_posix()
            if payload != payloads[name]:
                raise ValueError("Replayed thesis differs from its pinned public payload")
            checked.append((authorized, payload))
    checked.sort(key=lambda pair: manifests.analysis_sort_key(pair[0]))
    return {"authorized": [a for a, _ in checked], "payloads": [p for _, p in checked], "cohorts": groups}
