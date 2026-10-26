"""Explicit local verification of reviewed code preserving an existing financial release.

This has no publication entry point or fallback in financial_scope. Git-reviewed
policy pins an independent review; its digest is integrity, not a reviewer signature.
Original financial authority, original source replay and the entire site stay exact.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from src.config import PATHS
from src.analysis_agent import lifecycle as flow
from src.analysis_agent.entity_adapter import code_version
from . import financial_continuity_inputs as inputs
from .financial_scope import ANCHOR, EXECUTIVE, anchor, encoded, preserved_files, sha
from .financial_sources import authorization, approved_projection


def verify_local(site: Path, repo: Path = PATHS.root) -> list[str]:
    """Return problems; succeeds only with explicitly reviewed local continuity policy."""
    from .verify import _verify_site
    from .gate import PublicationRefused

    try:
        repo, site = Path(repo).resolve(), Path(site).absolute()
        if repo != PATHS.root.resolve():
            raise ValueError("Continuity verifier must run in its own repository")
        start_head = inputs.transport._git(repo, "rev-parse", "HEAD").decode().strip()
        local, policy_raw, review_raw = inputs.policy(repo)
        binding = local["binding"]
        inputs.ancestor(repo, binding["published_commit"], binding["production_commit"])
        inputs.ancestor(repo, binding["production_commit"], start_head)
        expected_runtime = binding["runtime_sha256"]
        if (
            code_version() != expected_runtime
            or inputs.runtime_at_commit(repo, binding["production_commit"]) != expected_runtime
        ):
            raise ValueError("Current runtime differs from independently reviewed continuity producer")
        spec = anchor(repo)
        original_anchor = inputs.regular(repo / ANCHOR, repo)
        if (
            sha(original_anchor) != binding["original_anchor_sha256"]
            or inputs.transport._git(repo, "show", f"{binding['published_commit']}:{ANCHOR}")
            != original_anchor
            or spec["authorization_sha256"] != binding["original_authorization_sha256"]
        ):
            raise ValueError("Continuity changed original financial authority")
        auth = authorization(spec, repo)
        if auth["independent_review_sha256"] != binding["original_review_sha256"]:
            raise ValueError("Continuity changed original financial review")
        expected_site = inputs.tree_files(repo, binding["published_commit"], "site")
        if inputs.fingerprint(expected_site) != binding["site_closure_sha256"]:
            raise ValueError("Continuity published site binding is invalid")
        record = repo / "analysis_runs/drafts/2026Q3" / (spec["analysis_entry"]["version"] + ".json")
        ledger = repo / "analysis_runs/lifecycle"
        with flow.writer(ledger):
            before = inputs.sources(repo, record, spec, ledger)
            if inputs.fingerprint(before) != binding["source_closure_sha256"]:
                raise ValueError("Continuity source or approval closure changed")
            if inputs.site_files(site) != expected_site:
                raise ValueError("Continuity must preserve every published site byte")
            preserved = preserved_files(site, repo, spec)
            projection = approved_projection([record], spec, ledger, repo)
            if encoded(projection) != inputs.regular(site / EXECUTIVE, site):
                raise ValueError("Continuity source replay differs from published projection")
            problems = _verify_site(site, preserved_approval_files=preserved)
            if problems:
                raise ValueError("Continuity site failed existing publication checks")
            # Repeat all mutable inputs after both slow verifiers under the ledger lock.
            if (
                inputs.sources(repo, record, spec, ledger) != before
                or inputs.site_files(site) != expected_site
                or anchor(repo) != spec
                or authorization(spec, repo) != auth
                or inputs.policy(repo) != (local, policy_raw, review_raw)
                or code_version() != expected_runtime
                or inputs.transport._git(repo, "rev-parse", "HEAD").decode().strip() != start_head
            ):
                raise ValueError("Continuity inputs changed during verification")
        return []
    except (
        ValueError,
        KeyError,
        OSError,
        TypeError,
        subprocess.CalledProcessError,
        PublicationRefused,
    ) as error:
        return [f"Invalid local financial continuity: {error}"]


def main(argv=None):
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("site", type=Path)
    parser.add_argument("--local-only", action="store_true", required=True)
    args = parser.parse_args(argv)
    problems = verify_local(args.site)
    print(
        json.dumps(
            {
                "scope": inputs.SCOPE,
                "valid": not problems,
                "publication_authorized": False,
                "problems": problems,
            }
        )
    )
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
