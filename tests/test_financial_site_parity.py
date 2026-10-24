"""Strict financial scope and full new-source parity never require an unrelated warehouse."""

import json
from pathlib import Path
import pytest
from src.publish.financial_scope import ANCHOR, EXECUTIVE, PROOF, anchor, sha, verify_financial

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "site"


def unavailable(request, message):
    if request.config.getoption("--require-local-data"):
        pytest.fail(message, pytrace=False)
    pytest.skip(message)


@pytest.fixture
def financial_site(request):
    if not (ROOT / ANCHOR).is_file():
        unavailable(request, "Financial release is not configured")
    doc = json.loads((SITE / EXECUTIVE).read_bytes())
    if "2026Q3" not in doc["views"]:
        unavailable(request, "Financial 3Q26 candidate has not been assembled")
    spec = anchor(ROOT)
    raw = (SITE / EXECUTIVE).read_bytes()
    assert sha(raw) == spec["executive_sha256"] and len(raw) == spec["executive_bytes"]
    if (SITE / PROOF).exists():
        assert verify_financial(SITE, ROOT) == []
    else:
        from src.publish.verify import verify_site

        assert verify_site(SITE) == []
    return spec


def test_financial_site_preserves_all_history_peers_and_five_readings(financial_site):
    from src.publish.financial_scope import preserved_executive, preserved_files, transport

    spec = financial_site
    before = json.loads(transport._git(ROOT, "show", f"{spec['baseline_commit']}:site/{EXECUTIVE}"))
    after = json.loads((SITE / EXECUTIVE).read_bytes())
    preserved_executive(before, after)
    assert after["metadata"]["default_period"] == before["metadata"]["default_period"]
    assert after["views"]["2026Q3"]["kpis"][0]["yoy"]["display"] == "+12.2%"
    if (SITE / PROOF).exists():
        frozen = preserved_files(SITE, ROOT, spec)
        assert len([p for p in frozen if p.startswith("data/v1/analysis/")]) == 5


def test_financial_projection_matches_complete_approved_source_replay(financial_site, request):
    from src.publish.financial_sources import replay_published_projection

    path = ROOT / "analysis_runs/drafts/2026Q3" / (financial_site["analysis_entry"]["version"] + ".json")
    if not path.is_file():
        unavailable(request, "Financial source record is not restored; complete replay is required")
    expected = replay_published_projection(SITE, ROOT)
    assert json.loads((SITE / EXECUTIVE).read_bytes()) == expected
