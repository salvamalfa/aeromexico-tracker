"""Offline verification of the explicit Q3 source-and-story replacement scope."""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

from src.config import PATHS

from . import editorial as transport
from . import manifest as manifests
from .issuer_scope import sha, verify_historical_baseline

ANCHOR = "config/publish/quarterly-story-release.json"
PROOF = "quarterly-story-publication.json"
SCHEMA = "quarterly_story_release_v1"
ENTITIES = {"AEROMEXICO", "VIVA_AEROBUS", "VOLARIS", "INDUSTRY"}
DATA_TARGETS = {
    "data/v1/executive.json",
    "data/v1/market.json",
    "data/v1/news.json",
    "data/v1/flights/quarters.json",
    *{
        f"data/v1/{prefix}/international/{period}.json"
        for prefix in ("flights", "flights/entities/INDUSTRY")
        for period in ("2026Q3", "2026M07", "2026M08", "2026M09")
    },
    *{f"data/v1/analysis/{entity}/2026Q3.json" for entity in ENTITIES},
}


def analysis_slots(entries, entities, period):
    if len(entries) != len(entities) or {manifests.analysis_identity(e) for e in entries} != {
        (e, period) for e in entities
    }:
        raise ValueError("Story release analysis slots missing, duplicated or outside the reviewed scope")


def anchor(repo=PATHS.root):
    raw = (repo / ANCHOR).read_bytes()
    if raw != transport._git(repo, "show", f"HEAD:{ANCHOR}"):
        raise ValueError("Story release anchor must be committed")
    spec = json.loads(raw)
    fields = {
        "schema_version",
        "baseline_commit",
        "baseline_manifest_sha256",
        "producer_code_version",
        "scope",
        "analysis_manifest",
        "retained_analysis_manifest",
        "superseded_analysis_manifest",
        "data_files",
        "frontend_files",
        "contracts",
        "authorization_sha256",
        "independent_audit_sha256",
    }
    if set(spec) != fields or spec["schema_version"] != SCHEMA:
        raise ValueError("Unknown story release contract")
    analysis_slots(spec["analysis_manifest"], ENTITIES, "2026Q3")
    analysis_slots(spec["retained_analysis_manifest"], ENTITIES, "2026Q2")
    analysis_slots(spec["superseded_analysis_manifest"], ENTITIES - {"INDUSTRY"}, "2026Q3")
    if {p["path"] for p in spec["data_files"]} != DATA_TARGETS:
        raise ValueError("Story release changed an undeclared data surface")
    for pin in spec["data_files"] + spec["frontend_files"]:
        if (
            set(pin) != {"path", "sha256", "bytes"}
            or not re.fullmatch(r"[a-f0-9]{64}", pin["sha256"])
            or type(pin["bytes"]) is not int
            or pin["bytes"] <= 0
        ):
            raise ValueError("Story release output pin is malformed")
    if any(
        p["path"] != "index.html" and not re.fullmatch(r"assets/[A-Za-z0-9_.-]+\.(?:js|css)", p["path"])
        for p in spec["frontend_files"]
    ):
        raise ValueError("Story release frontend path escapes its reviewed asset closure")
    for key in (
        "baseline_manifest_sha256",
        "producer_code_version",
        "authorization_sha256",
        "independent_audit_sha256",
    ):
        if not re.fullmatch(r"[a-f0-9]{64}", spec[key]):
            raise ValueError("Story release digest missing or malformed")
    if not re.fullmatch(r"[a-f0-9]{40}", spec["baseline_commit"]):
        raise ValueError("Story release baseline commit malformed")
    transport._git(repo, "merge-base", "--is-ancestor", spec["baseline_commit"], "HEAD")
    return spec


def preserved_files(site, repo, spec):
    """Verify output scope against exact Git history; no private approvals here."""
    old, _ = transport.baseline(repo, spec)
    if sorted(old["analysis_manifest"], key=manifests.analysis_sort_key) != sorted(
        spec["retained_analysis_manifest"] + spec["superseded_analysis_manifest"],
        key=manifests.analysis_sort_key,
    ):
        raise ValueError("Story release does not account for every historical approval")
    manifest = manifests.load_manifest(site)
    if manifest["analysis_manifest"] != sorted(
        spec["retained_analysis_manifest"] + spec["analysis_manifest"], key=manifests.analysis_sort_key
    ):
        raise ValueError("Story release consumed an obsolete or unapproved analysis slot")
    if manifest["contracts"] != spec["contracts"]:
        raise ValueError("Story release contract hashes changed")
    proof_raw = (site / PROOF).read_bytes()
    proof = json.loads(proof_raw)
    if (
        set(proof) != {"schema_version", "anchor_sha256", "remote_witness", "historical_source_status"}
        or proof["schema_version"] != "quarterly_story_publication_v1"
        or proof["anchor_sha256"] != sha((repo / ANCHOR).read_bytes())
        or proof["remote_witness"].get("baseline_commit") != spec["baseline_commit"]
        or proof["remote_witness"].get("manifest_sha256") != spec["baseline_manifest_sha256"]
        or proof["historical_source_status"] != "superseded_Q3_source_not_replayed_not_consumed"
    ):
        raise ValueError("Story release proof or historical-source status differs")
    witness = proof["remote_witness"]
    if (
        witness.get("files_verified") != len(old["files"])
        or witness.get("origin") != transport.ORIGIN
        or type(witness.get("deployment_run")) is not int
        or witness["deployment_run"] <= 0
        or not re.fullmatch(r"[a-f0-9]{40}", witness.get("deployment_commit", ""))
    ):
        raise ValueError("Story release witness does not identify the exact served baseline")
    transport._git(repo, "merge-base", "--is-ancestor", witness["deployment_commit"], spec["baseline_commit"])
    if transport._git(
        repo, "diff", "--name-only", witness["deployment_commit"], spec["baseline_commit"], "--", "site"
    ):
        raise ValueError("Story release witnessed deployment differs from its baseline site")
    if any(path.is_symlink() for path in site.rglob("*")):
        raise ValueError("Story release site cannot contain symlinks")
    if transport.frontend_entries(site) != spec["frontend_files"]:
        raise ValueError("Story release frontend closure differs from reviewed pins")
    pins = spec["data_files"] + spec["frontend_files"]
    names = [p["path"] for p in pins]
    if len(names) != len(set(names)) or "index.html" not in names:
        raise ValueError("Story release output pins duplicate or omit the frontend")
    changed = set(names)
    for pin in pins:
        path = site / pin["path"]
        if (
            path.is_symlink()
            or not path.is_file()
            or sha(path.read_bytes()) != pin["sha256"]
            or path.stat().st_size != pin["bytes"]
        ):
            raise ValueError("Story release data or frontend differs from reviewed output pins")
    removed = {
        "data/v1/" + manifests.analysis_relative_path(e).as_posix()
        for e in spec["superseded_analysis_manifest"]
    }
    # An entity's namespaced new thesis may have the same path as its old one.
    removed -= changed
    preserved = set()
    for pin in old["files"]:
        name = pin["path"]
        if name in changed:
            continue
        if name in removed:
            if (site / name).exists():
                raise ValueError("Superseded legacy thesis still exposed in the new site")
            continue
        raw = (site / name).read_bytes()
        if sha(raw) != pin["sha256"] or len(raw) != pin["bytes"]:
            raise ValueError("Story release changed an unrelated historical file")
        if name.startswith("data/v1/"):
            preserved.add(name)
    expected = ({p["path"] for p in old["files"]} - removed) | changed | {PROOF}
    if {p["path"] for p in manifests.file_entries(site)} != expected:
        raise ValueError("Story release introduced or removed an undeclared file")
    return frozenset(preserved)


def verify_story(site, repo=PATHS.root):
    from .verify import _verify_site

    try:
        spec = anchor(repo)
        verify_historical_baseline(repo, spec, site)
        preserved = preserved_files(site, repo, spec)
        return _verify_site(site, preserved_approval_files=preserved)
    except (ValueError, KeyError, TypeError, OSError, subprocess.CalledProcessError) as error:
        return [f"Invalid quarterly story release: {error}"]


def main():
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("site", type=Path)
    problems = verify_story(parser.parse_args().site)
    print(json.dumps({"valid": not problems, "problems": problems}, ensure_ascii=False))
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
