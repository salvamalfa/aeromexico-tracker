"""Editorial parity inherits published bytes and replays only the new evidence."""
import json
from pathlib import Path

import pytest

from src.publish.editorial import ANALYSIS, PROOF, anchor, preserved_files, verify_editorial

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "site"


@pytest.fixture
def editorial_site():
    if not (SITE / PROOF).exists():
        pytest.skip("Editorial candidate has not been assembled; general publication checks still apply")
    return anchor(ROOT)


def test_editorial_site_preserves_every_historical_file(editorial_site):
    assert verify_editorial(SITE) == []
    preserved = preserved_files(SITE, ROOT, editorial_site)
    assert "data/v1/executive.json" in preserved
    assert "data/v1/news.json" in preserved
    assert len([p for p in preserved if p.startswith("data/v1/analysis/")]) == 4
    assert any(p.startswith("data/v1/flights/") for p in preserved)
    document = json.loads((SITE / "data/v1/executive.json").read_bytes())
    assert "2026Q3" not in document["views"]
    assert all(row["period_id"] != "2026Q3" for row in document["records"])


@pytest.mark.local_data
def test_editorial_new_payload_matches_its_full_approved_source_replay(editorial_site):
    from src.analysis_agent import lifecycle as flow
    from src.publish.frozen_data import verify_baseline_approvals
    entry = editorial_site["analysis_entry"]
    cohorts = json.loads((ROOT / "config/publish/approval-cohorts.json").read_bytes())["cohorts"]
    cohort = next(c for c in cohorts if entry in c["analysis_manifest"])
    path = ROOT / "analysis_runs/drafts/2026Q3" / (entry["version"] + ".json")
    replay = verify_baseline_approvals([path], cohort["implementation_commit"], flow.ROOT, include_public_payloads=True)
    assert len(replay["payloads"]) == 1
    assert json.loads((SITE / ANALYSIS).read_bytes()) == replay["payloads"][0]
