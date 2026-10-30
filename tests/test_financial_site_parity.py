"""Strict financial scope and full new-source parity never require an unrelated warehouse."""

import json
from pathlib import Path

import pytest

from src.publish.financial_scope import ANCHOR, EXECUTIVE, PROOF, anchor, encoded, sha
from tests._site_publication_parity import (
    preserved_financial_projection,
    preserved_readings,
    verify_current_publication,
)

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
    checker = request.getfixturevalue("verify_financial_publication")
    verify_current_publication(SITE, ROOT, checker)
    original = preserved_financial_projection(SITE, ROOT, spec)
    assert sha(encoded(original)) == spec["executive_sha256"]
    return spec


def test_financial_site_preserves_all_history_peers_and_five_readings_and_replays_sources(
    financial_site, request
):
    from src.publish.financial_scope import preserved_executive, preserved_files, transport

    spec = financial_site
    before = json.loads(transport._git(ROOT, "show", f"{spec['baseline_commit']}:site/{EXECUTIVE}"))
    after = preserved_financial_projection(SITE, ROOT, spec)
    preserved_readings(SITE, ROOT, spec)
    preserved_executive(before, after)
    assert after["metadata"]["default_period"] == before["metadata"]["default_period"]
    assert after["views"]["2026Q3"]["kpis"][0]["yoy"]["display"] == "+12.2%"
    if (SITE / PROOF).exists():
        frozen = preserved_files(SITE, ROOT, spec)
        assert len([p for p in frozen if p.startswith("data/v1/analysis/")]) == 5
    from src.publish.financial_sources import approved_projection

    path = ROOT / "analysis_runs/drafts/2026Q3" / (financial_site["analysis_entry"]["version"] + ".json")
    if not path.is_file():
        unavailable(request, "Financial source record is not restored; complete replay is required")
    from src.analysis_agent import lifecycle as flow

    expected = approved_projection([path], spec, flow.ROOT, ROOT)
    assert after == expected
