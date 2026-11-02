import copy
import json
from pathlib import Path

import pytest

from scripts.audit_dashboard_periods import audit
from src.dashboard.financial_periods import financial_periods, with_financial_default
from src.dashboard.industry_review import build_industry_review
from src.web_export.executive import export_executive

ROOT = Path(__file__).resolve().parents[1]


def test_real_constructed_data_export_and_industry_candidate_do_not_activate_or_mutate(tmp_path):
    source = ROOT / "site/data/v1/executive.json"
    before = source.read_bytes()
    result = audit(ROOT / "site", tmp_path)
    exported = json.loads((tmp_path / "data/v1/executive.json").read_bytes())
    assert exported["metadata"]["default_period"] == result["financial_latest"] == "2026Q3"
    assert exported["entities"]["INDUSTRY"]["last_period"] == "2026Q2"
    assert result["industry_candidate"]["record"]["passengers"] == 22777000
    assert result["data_activation"] == "none"
    assert source.read_bytes() == before


def test_future_incomplete_record_or_view_does_not_control_default():
    payload = json.loads((ROOT / "site/data/v1/executive.json").read_bytes())
    before = copy.deepcopy(payload)
    latest = financial_periods(payload)[-1]
    future = {**payload["records"][-1], "period_id": "2030Q1"}
    payload["records"].append(future)
    assert with_financial_default(payload)["metadata"]["default_period"] == latest
    payload["views"]["2030Q1"] = {}
    future["ask_km"] = None
    assert with_financial_default(payload)["metadata"]["default_period"] == latest
    assert before["records"] == payload["records"][:-1]


def test_normalizing_the_default_does_not_bypass_input_schema_validation(tmp_path):
    payload = json.loads((ROOT / "site/data/v1/executive.json").read_bytes())
    payload["metadata"]["default_period"] = 3
    with pytest.raises(ValueError, match="does not match its schema"):
        export_executive(payload, tmp_path, skip_input_check=True)


def test_real_industry_review_has_q3_values_and_preserves_every_published_input(tmp_path):
    payload = json.loads((ROOT / "site/data/v1/executive.json").read_bytes())
    before = copy.deepcopy(payload)
    review = build_industry_review(payload, "2026Q3")
    written = export_executive(review, tmp_path, skip_input_check=True)
    industry = review["entities"]["INDUSTRY"]
    current = industry["records"][-1]
    assert current["passengers"] == 22777000
    assert current["rask_cents_per_km"] == pytest.approx(8.156345041427636)
    assert current["cask_cents_per_km"] == pytest.approx(7.574922166159674)
    assert current["ask_km"] == 41072068224
    assert industry["views"]["2026Q3"]["conclusions"] == []
    assert industry["records"][:-1] == payload["entities"]["INDUSTRY"]["records"]
    assert payload == before
    for key in ("AEROMEXICO", "VIVA_AEROBUS", "VOLARIS"):
        assert review["entities"][key] == payload["entities"][key]
    assert review["records"] == payload["records"]
    assert written == [tmp_path / "executive.json"]
    for entity in ("AEROMEXICO", "VIVA_AEROBUS", "VOLARIS"):
        missing = copy.deepcopy(payload)
        missing["entities"][entity]["records"] = [
            row for row in missing["entities"][entity]["records"] if row["period_id"] != "2026Q3"
        ]
        with pytest.raises(ValueError, match="Missing or ambiguous"):
            build_industry_review(missing, "2026Q3")
