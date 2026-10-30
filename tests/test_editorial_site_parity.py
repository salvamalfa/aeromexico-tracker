"""Editorial parity inherits published bytes and replays only the new evidence."""

import hashlib
import json
from pathlib import Path

import pytest

from src.publish.editorial import ANALYSIS, PROOF, anchor, preserved_files, verify_editorial
from tests._site_publication_parity import verify_current_publication

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "site"


def _unavailable(request, message):
    if request.config.getoption("--require-local-data"):
        pytest.fail(message, pytrace=False)
    pytest.skip(message)


@pytest.fixture(scope="module")
def editorial_site(request):
    from scripts.check_pages_publication import verifier_for
    from src.publish.financial_scope import (
        PROOF as FINANCIAL_PROOF,
    )
    from src.publish.financial_scope import (
        anchor as financial_anchor,
    )

    manifest_path = SITE / "publication_manifest.json"
    assert not manifest_path.is_symlink(), "Publication manifest cannot be a symlink"
    if not manifest_path.is_file():
        assert not manifest_path.exists(), "Publication manifest must be a regular file"
        assert not any(
            (SITE / name).exists() or (SITE / name).is_symlink()
            for name in (PROOF, FINANCIAL_PROOF, "issuer-publication.json")
        ), "An existing publication receipt requires its manifest"
        _unavailable(request, "Editorial candidate has not been assembled")
    try:
        profile = verifier_for(SITE)
    except (ValueError, OSError, KeyError, TypeError) as error:
        raise AssertionError(f"Invalid publication verification selection: {error}") from error
    assert profile in {
        "src.publish.verify",
        "src.publish.editorial",
        "src.publish.financial_scope",
        "src.publish.issuer_scope",
    }, f"Unsupported publication verifier: {profile}"
    if profile == "src.publish.issuer_scope":
        checker = request.getfixturevalue("verify_financial_publication")
        verify_current_publication(SITE, ROOT, checker)
        spec = anchor(ROOT)
        payload = (SITE / ANALYSIS).read_bytes()
        assert len(payload) == spec["analysis_bytes"]
        assert hashlib.sha256(payload).hexdigest() == spec["analysis_sha256"]
        return spec
    if (SITE / FINANCIAL_PROOF).exists():
        verify_financial_publication = request.getfixturevalue("verify_financial_publication")
        assert verify_financial_publication(SITE, ROOT) == []
        return financial_anchor(ROOT)
    if not (SITE / PROOF).exists():
        manifest_path = SITE / "publication_manifest.json"
        if manifest_path.is_file():
            manifest = json.loads(manifest_path.read_bytes())
            spec = anchor(ROOT)
            # A later normal publication legitimately replaces the frontend and
            # drops the editorial receipt. It must still contain this reading,
            # have no missing inventoried receipt, and pass all general checks.
            if spec["analysis_entry"] in manifest["analysis_manifest"]:
                from src.publish.verify import verify_site

                problems = verify_site(SITE)
                assert not problems, problems
                payload = (SITE / ANALYSIS).read_bytes()
                assert len(payload) == spec["analysis_bytes"]
                assert hashlib.sha256(payload).hexdigest() == spec["analysis_sha256"]
                return spec
        _unavailable(
            request, "Editorial candidate has not been assembled; general publication checks still apply"
        )
    return anchor(ROOT)


def test_editorial_site_preserves_every_historical_file(editorial_site):
    from scripts.check_pages_publication import verifier_for
    from src.publish.financial_scope import PROOF as FINANCIAL_PROOF

    if verifier_for(SITE) == "src.publish.issuer_scope":
        from src.publish.issuer_scope import anchor as issuer_anchor
        from src.publish.issuer_scope import preserved_files as issuer_preserved

        inherited = issuer_preserved(SITE, ROOT, issuer_anchor(ROOT))
        assert ANALYSIS in inherited
        assert "data/v1/news.json" in inherited
        assert any(p.startswith("data/v1/flights/") for p in inherited)
        return
    if (SITE / FINANCIAL_PROOF).exists():
        pytest.skip("Financial mode has its own strict historical structure/byte preservation check")
    if not (SITE / PROOF).exists():
        pytest.skip("Verified later normal publication; editorial frontend preservation does not apply")
    assert verify_editorial(SITE) == []
    preserved = preserved_files(SITE, ROOT, editorial_site)
    assert "data/v1/executive.json" in preserved
    assert "data/v1/news.json" in preserved
    assert len([p for p in preserved if p.startswith("data/v1/analysis/")]) == 4
    assert any(p.startswith("data/v1/flights/") for p in preserved)
    document = json.loads((SITE / "data/v1/executive.json").read_bytes())
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


def test_editorial_new_payload_matches_its_full_approved_source_replay(editorial_site, request):
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
    assert json.loads((SITE / ANALYSIS).read_bytes()) == replay["payloads"][0]
