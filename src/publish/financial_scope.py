"""Committed financial scope, immutable baseline and offline deployment checks."""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
from pathlib import Path

from src.config import PATHS
from . import editorial as transport
from . import manifest as manifests

ANCHOR = "config/publish/financial-release.json"
PROOF = "financial-publication.json"
EXECUTIVE = "data/v1/executive.json"
ANALYSIS = "data/v1/analysis/2026Q3.json"
SCOPE = "aeromexico_2026Q3_existing_financial_cards_v1"


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def encoded(value) -> bytes:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode()


def anchor(repo: Path) -> dict:
    raw = (repo / ANCHOR).read_bytes()
    if raw != transport._git(repo, "show", f"HEAD:{ANCHOR}"):
        raise ValueError("Financial anchor must be committed")
    spec = json.loads(raw)
    fields = {
        "schema_version",
        "scope",
        "baseline_commit",
        "baseline_manifest_sha256",
        "analysis_entry",
        "analysis_sha256",
        "analysis_bytes",
        "source_implementation_commit",
        "package_id",
        "calculation_fingerprint",
        "producer_commit",
        "producer_code_version",
        "executive_sha256",
        "executive_bytes",
        "authorization_sha256",
        "frontend_files",
    }
    if set(spec) != fields or spec["schema_version"] != "financial_release_v1" or spec["scope"] != SCOPE:
        raise ValueError("Invalid financial release scope")
    for name in ("baseline_commit", "source_implementation_commit", "producer_commit"):
        if not re.fullmatch("[a-f0-9]{40}", spec[name]):
            raise ValueError("Invalid financial source commit")
        transport._git(repo, "merge-base", "--is-ancestor", spec[name], "HEAD")
    transport._git(repo, "merge-base", "--is-ancestor", spec["baseline_commit"], spec["producer_commit"])
    for name in (
        "baseline_manifest_sha256",
        "analysis_sha256",
        "calculation_fingerprint",
        "producer_code_version",
        "executive_sha256",
        "authorization_sha256",
    ):
        if not re.fullmatch("[a-f0-9]{64}", spec[name]):
            raise ValueError("Invalid financial digest")
    if manifests.analysis_identity(spec["analysis_entry"]) != ("AEROMEXICO", "2026Q3"):
        raise ValueError("Financial scope cannot activate another reading")
    if any(type(spec[k]) is not int or spec[k] <= 0 for k in ("analysis_bytes", "executive_bytes")):
        raise ValueError("Invalid financial payload length")
    names = [item["path"] for item in spec["frontend_files"]]
    if len(names) != len(set(names)) or "index.html" not in names:
        raise ValueError("Invalid financial frontend inventory")
    for item in spec["frontend_files"]:
        if (
            set(item) != {"path", "sha256", "bytes"}
            or not (
                item["path"] == "index.html"
                or re.fullmatch(r"assets/[A-Za-z0-9_.-]+\.(js|css)", item["path"])
            )
            or not re.fullmatch("[a-f0-9]{64}", item["sha256"])
            or type(item["bytes"]) is not int
            or item["bytes"] <= 0
        ):
            raise ValueError("Invalid financial frontend pin")
    old, _ = transport.baseline(repo, spec)
    if spec["analysis_entry"] not in old["analysis_manifest"]:
        raise ValueError("Financial reading is not already published")
    cohorts = json.loads(
        transport._git(repo, "show", f"{spec['baseline_commit']}:config/publish/approval-cohorts.json")
    )["cohorts"]
    cohort = next((c for c in cohorts if spec["analysis_entry"] in c["analysis_manifest"]), None)
    if not cohort or cohort["implementation_commit"] != spec["source_implementation_commit"]:
        raise ValueError("Financial source implementation differs from published provenance")
    expected = {"path": ANALYSIS, "sha256": spec["analysis_sha256"], "bytes": spec["analysis_bytes"]}
    if expected not in cohort["files"]:
        raise ValueError("Financial reading pin differs from published source")
    return spec


def preserved_executive(before: dict, after: dict) -> None:
    """Structural scope is independent of the expected full-output hash."""
    period = "2026Q3"
    if period in before["views"] or any(r["period_id"] == period for r in before["records"]):
        raise ValueError("Financial baseline already contains the quarter")
    expected = json.loads(json.dumps(after))
    if (
        after["metadata"]["last_period"] != period
        or after["metadata"]["quarter_count"] != len(before["records"]) + 1
    ):
        raise ValueError("Financial root metadata is inconsistent")
    if (
        len(expected["records"]) != len(before["records"]) + 1
        or expected["records"][-1]["period_id"] != period
    ):
        raise ValueError("Financial release must append exactly one record")
    expected["records"].pop()
    if set(expected["views"]) != set(before["views"]) | {period}:
        raise ValueError("Financial release must append exactly one view")
    expected["views"].pop(period)
    block = expected["entities"]["AEROMEXICO"]
    old_block = before["entities"]["AEROMEXICO"]
    top_record = after["records"][-1]
    entity_record = block["records"][-1]
    if any(
        entity_record.get(key) != value for key, value in top_record.items() if key != "load_factor_reported"
    ):
        raise ValueError("Financial root and entity records disagree")
    if (
        "load_factor_reported" in top_record
        and entity_record.get("load_factor") != top_record["load_factor_reported"]
    ):
        raise ValueError("Financial root and entity occupancy disagree")
    if after["views"][period] != block["views"].get(period):
        raise ValueError("Financial root and entity views disagree")
    if len(block["records"]) != len(old_block["records"]) + 1 or block["records"][-1]["period_id"] != period:
        raise ValueError("Financial entity record is not a single append")
    if set(block["views"]) != set(old_block["views"]) | {period}:
        raise ValueError("Financial entity views changed out of scope")
    block["records"].pop()
    block["views"].pop(period)
    if block["last_period"] != period or block["quarter_count"] != len(old_block["records"]) + 1:
        raise ValueError("Financial entity metadata is inconsistent")
    for key in ("last_period", "quarter_count"):
        block[key] = old_block[key]
    allowed = {
        "last_period",
        "quarter_count",
        "coverage_label",
        "data_as_of",
        "source_view",
        "method_note",
        "load_rask_interpretation",
    }
    for key in allowed:
        expected["metadata"][key] = before["metadata"][key]
    if encoded(expected) != encoded(before):
        raise ValueError("Financial release changed historical records, peers or unrelated metadata")


def preserved_files(site: Path, repo: Path, spec: dict) -> frozenset[str]:
    old, _ = transport.baseline(repo, spec)
    current = manifests.load_manifest(site)
    proof = json.loads((site / PROOF).read_bytes())
    if (
        set(proof) != {"schema_version", "anchor_sha256", "remote_witness", "authorization_sha256"}
        or proof["schema_version"] != "financial_publication_v1"
    ):
        raise ValueError("Invalid financial proof")
    if (
        proof["anchor_sha256"] != sha((repo / ANCHOR).read_bytes())
        or proof["authorization_sha256"] != spec["authorization_sha256"]
    ):
        raise ValueError("Financial proof differs from committed authority")
    witness = proof["remote_witness"]
    if (
        witness["baseline_commit"] != spec["baseline_commit"]
        or witness["manifest_sha256"] != spec["baseline_manifest_sha256"]
        or witness["files_verified"] != len(old["files"])
        or witness["origin"] != transport.ORIGIN
        or type(witness["deployment_run"]) is not int
    ):
        raise ValueError("Financial remote witness is incomplete")
    transport._git(repo, "merge-base", "--is-ancestor", witness["deployment_commit"], spec["baseline_commit"])
    if transport._git(
        repo, "diff", "--name-only", witness["deployment_commit"], spec["baseline_commit"], "--", "site"
    ):
        raise ValueError("Financial witness has another deployed baseline")
    if current["contracts"] != old["contracts"] or current["analysis_manifest"] != old["analysis_manifest"]:
        raise ValueError("Financial update changed contracts or thesis identities")
    if any(p.is_symlink() for p in site.rglob("*")):
        raise ValueError("Financial site contains symlinks")
    old_names = {e["path"] for e in old["files"]}
    frontend_names = {e["path"] for e in spec["frontend_files"]}
    actual = {p.relative_to(site).as_posix() for p in site.rglob("*") if p.is_file()}
    if actual != old_names | frontend_names | {PROOF, "publication_manifest.json"}:
        raise ValueError("Financial update introduced or removed unrelated files")
    for item in spec["frontend_files"]:
        raw = (site / item["path"]).read_bytes()
        if sha(raw) != item["sha256"] or len(raw) != item["bytes"]:
            raise ValueError("Financial frontend differs from reviewed pins")
    for item in old["files"]:
        name = item["path"]
        if name not in {"index.html", EXECUTIVE} and (site / name).read_bytes() != transport._git(
            repo, "show", f"{spec['baseline_commit']}:site/{name}"
        ):
            raise ValueError(f"Financial release changed preserved file: {name}")
    raw = (site / EXECUTIVE).read_bytes()
    if sha(raw) != spec["executive_sha256"] or len(raw) != spec["executive_bytes"]:
        raise ValueError("Financial projection differs from the reviewed output")
    before = json.loads(transport._git(repo, "show", f"{spec['baseline_commit']}:site/{EXECUTIVE}"))
    preserved_executive(before, json.loads(raw))
    return frozenset(old_names - {"index.html", EXECUTIVE})


def verify_financial(site: Path, repo: Path = PATHS.root) -> list[str]:
    from .verify import _verify_site
    from src.analysis_agent.entity_adapter import code_version

    try:
        spec = anchor(repo)
        if code_version() != spec["producer_code_version"]:
            raise ValueError("Financial runtime differs from reviewed producer")
        preserved = preserved_files(site, repo, spec)
    except (ValueError, KeyError, OSError, subprocess.CalledProcessError) as error:
        return [f"Invalid financial preservation proof: {error}"]
    return _verify_site(site, preserved_approval_files=preserved)


def main(argv=None):
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("site", type=Path)
    args = parser.parse_args(argv)
    problems = verify_financial(args.site)
    if problems:
        print("\n".join(problems))
        return 1
    print("Financial site valid: new projection pinned; all unrelated published bytes preserved.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
