"""Editorial parity inherits published bytes and replays only the new evidence."""

import hashlib
import json
from pathlib import Path

import pytest

from src.publish.editorial import ANALYSIS, PROOF, anchor, preserved_files, verify_editorial
from tests._site_publication_parity import official_map_baseline, verify_current_publication

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "site"


def _unavailable(request, message):
    if request.config.getoption("--require-local-data"):
        pytest.fail(message, pytrace=False)
    pytest.skip(message)


@pytest.fixture(scope="module")
def editorial_comparison_site(request):
    checker = request.getfixturevalue("verify_financial_publication")
    base_commit = request.config.getoption("--financial-publication-base")
    with official_map_baseline(SITE, ROOT, checker, base_commit=base_commit) as comparison_site:
        yield comparison_site


@pytest.fixture(scope="module")
def editorial_site(request, editorial_comparison_site):
    from scripts.check_pages_publication import verifier_for
    from src.publish.financial_scope import (
        PROOF as FINANCIAL_PROOF,
    )
    from src.publish.financial_scope import (
        anchor as financial_anchor,
    )

    site = editorial_comparison_site
    manifest_path = site / "publication_manifest.json"
    assert not manifest_path.is_symlink(), "Publication manifest cannot be a symlink"
    if not manifest_path.is_file():
        from scripts.check_pages_publication import VERIFIERS

        assert not manifest_path.exists(), "Publication manifest must be a regular file"
        assert not any((site / name).exists() or (site / name).is_symlink() for name, _ in VERIFIERS), (
            "An existing publication receipt requires its manifest"
        )
        _unavailable(request, "Editorial candidate has not been assembled")
    try:
        profile = verifier_for(site, ROOT)
    except (ValueError, OSError, KeyError, TypeError) as error:
        raise AssertionError(f"Invalid publication verification selection: {error}") from error
    assert profile in {
        "src.publish.verify",
        "src.publish.editorial",
        "src.publish.financial_scope",
        "src.publish.issuer_scope",
        "src.publish.movements_scope",
        "src.publish.source_data_scope",
        "src.publish.quarterly_story_scope",
        "src.publish.afac_history_scope",
    }, f"Unsupported publication verifier: {profile}"
    if profile in {"src.publish.quarterly_story_scope", "src.publish.afac_history_scope"}:
        from tests._quarterly_story_parity import publication

        return publication(site, ROOT)[0]
    if profile in {
        "src.publish.issuer_scope",
        "src.publish.movements_scope",
        "src.publish.source_data_scope",
    }:
        checker = request.getfixturevalue("verify_financial_publication")
        verify_current_publication(
            site, ROOT, checker, base_commit=request.config.getoption("--financial-publication-base")
        )
        spec = anchor(ROOT)
        payload = (site / ANALYSIS).read_bytes()
        assert len(payload) == spec["analysis_bytes"]
        assert hashlib.sha256(payload).hexdigest() == spec["analysis_sha256"]
        return spec
    if (site / FINANCIAL_PROOF).exists():
        verify_financial_publication = request.getfixturevalue("verify_financial_publication")
        assert verify_financial_publication(site, ROOT) == []
        return financial_anchor(ROOT)
    if not (site / PROOF).exists():
        manifest_path = site / "publication_manifest.json"
        if manifest_path.is_file():
            manifest = json.loads(manifest_path.read_bytes())
            spec = anchor(ROOT)
            # A later normal publication legitimately replaces the frontend and
            # drops the editorial receipt. It must still contain this reading,
            # have no missing inventoried receipt, and pass all general checks.
            if spec["analysis_entry"] in manifest["analysis_manifest"]:
                from src.publish.verify import verify_site

                problems = verify_site(site)
                assert not problems, problems
                payload = (site / ANALYSIS).read_bytes()
                assert len(payload) == spec["analysis_bytes"]
                assert hashlib.sha256(payload).hexdigest() == spec["analysis_sha256"]
                return spec
        _unavailable(
            request, "Editorial candidate has not been assembled; general publication checks still apply"
        )
    return anchor(ROOT)


def test_editorial_site_preserves_every_historical_file(editorial_site, editorial_comparison_site):
    from scripts.check_pages_publication import verifier_for
    from src.publish.financial_scope import PROOF as FINANCIAL_PROOF

    site = editorial_comparison_site
    module = verifier_for(site, ROOT)
    if module in {"src.publish.quarterly_story_scope", "src.publish.afac_history_scope"}:
        from tests._quarterly_story_parity import publication

        spec, _, _ = publication(site, ROOT)
        assert spec == editorial_site
        return
    if module in {
        "src.publish.issuer_scope",
        "src.publish.movements_scope",
        "src.publish.source_data_scope",
    }:
        from importlib import import_module

        scope = import_module(module)
        inherited = scope.preserved_files(site, ROOT, scope.anchor(ROOT))
        assert ANALYSIS in inherited
        assert "data/v1/news.json" in inherited
        assert any(p.startswith("data/v1/flights/") for p in inherited)
        return
    if (site / FINANCIAL_PROOF).exists():
        pytest.skip("Financial mode has its own strict historical structure/byte preservation check")
    if not (site / PROOF).exists():
        pytest.skip("Verified later normal publication; editorial frontend preservation does not apply")
    assert verify_editorial(site) == []
    preserved = preserved_files(site, ROOT, editorial_site)
    assert "data/v1/executive.json" in preserved
    assert "data/v1/news.json" in preserved
    assert len([p for p in preserved if p.startswith("data/v1/analysis/")]) == 4
    assert any(p.startswith("data/v1/flights/") for p in preserved)
    document = json.loads((site / "data/v1/executive.json").read_bytes())
    assert "2026Q3" not in document["views"]
    assert all(row["period_id"] != "2026Q3" for row in document["records"])


def _required_source_record(entry, request):
    path = ROOT / "analysis_runs/drafts/2026Q3" / (entry["version"] + ".json")
    if not path.is_file():
        _unavailable(
            request,
            "Current editorial source record is not restored; its full source replay is required locally",
        )
    return path


def test_editorial_new_payload_matches_its_full_approved_source_replay(
    editorial_site, editorial_comparison_site, request
):
    from scripts.check_pages_publication import verifier_for

    site = editorial_comparison_site
    if verifier_for(site, ROOT) in {"src.publish.quarterly_story_scope", "src.publish.afac_history_scope"}:
        from tests._quarterly_story_parity import missing_records, replay

        if missing_records(site, ROOT):
            _unavailable(request, "Restore the complete story/Q2/superseded ledger for full source replay")
        result = replay(site, ROOT)
        assert len(result["authorized"]) == len(result["payloads"]) == 8
        return
    from src.analysis_agent import lifecycle as flow
    from src.publish.frozen_data import verify_baseline_approvals

    entry = editorial_site["analysis_entry"]
    path = _required_source_record(entry, request)
    cohorts = json.loads((ROOT / "config/publish/approval-cohorts.json").read_bytes())["cohorts"]
    cohort = next(c for c in cohorts if entry in c["analysis_manifest"])
    replay = verify_baseline_approvals(
        [path], cohort["implementation_commit"], flow.ROOT, include_public_payloads=True
    )
    assert len(replay["payloads"]) == 1
    assert json.loads((site / ANALYSIS).read_bytes()) == replay["payloads"][0]
