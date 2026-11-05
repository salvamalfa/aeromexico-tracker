import copy
import hashlib
import json
import subprocess
from pathlib import Path

import pytest

from scripts.audit_dashboard_periods import audit
from src.dashboard.financial_periods import financial_periods, with_financial_default
from src.dashboard.industry_review import build_industry_review
from src.web_export.executive import export_executive

ROOT = Path(__file__).resolve().parents[1]
PRE_INDUSTRY_COMMIT = "3a299fbc3ea5c709a209b794e79565a69e4af714"


@pytest.fixture
def pre_industry_site(tmp_path):
    """Use one complete historical input edition, without removing a published quarter."""
    def original(relative):
        return subprocess.check_output(
            ["git", "show", f"{PRE_INDUSTRY_COMMIT}:site/{relative}"], cwd=ROOT,
        )

    manifest = json.loads(original("publication_manifest.json"))
    pins = {item["path"]: item for item in manifest["files"]}
    paths = ["data/v1/executive.json", "data/v1/market.json"]
    for entity in ("AEROMEXICO", "INDUSTRY", "VIVA_AEROBUS", "VOLARIS"):
        prefix = "flights" if entity == "AEROMEXICO" else f"flights/entities/{entity}"
        paths.append(f"data/v1/{prefix}/international/2026Q3.json")
    site = tmp_path / "pre-industry/site"
    for relative in paths:
        raw = original(relative)
        assert len(raw) == pins[relative]["bytes"]
        assert hashlib.sha256(raw).hexdigest() == pins[relative]["sha256"]
        target = site / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)
    return site


def test_real_constructed_data_export_and_industry_candidate_do_not_activate_or_mutate(
    tmp_path, pre_industry_site
):
    source = pre_industry_site / "data/v1/executive.json"
    before = source.read_bytes()
    published = (ROOT / "site/data/v1/executive.json").read_bytes()
    build = tmp_path / "build"
    result = audit(pre_industry_site, build)
    exported = json.loads((build / "data/v1/executive.json").read_bytes())
    assert exported["metadata"]["default_period"] == result["financial_latest"] == "2026Q3"
    assert exported["entities"]["INDUSTRY"]["last_period"] == "2026Q2"
    assert result["industry_candidate"]["record"]["passengers"] == 22777000
    assert result["data_activation"] == "none"
    assert source.read_bytes() == before
    assert (ROOT / "site/data/v1/executive.json").read_bytes() == published


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


def test_real_industry_review_has_q3_values_and_preserves_every_published_input(tmp_path, pre_industry_site):
    payload = json.loads((pre_industry_site / "data/v1/executive.json").read_bytes())
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


def test_review_cannot_replace_the_already_published_industry_quarter():
    source = ROOT / "site/data/v1/executive.json"
    before = source.read_bytes()
    payload = json.loads(before)
    assert any(row["period_id"] == "2026Q3" for row in payload["entities"]["INDUSTRY"]["records"])
    with pytest.raises(ValueError, match="Do not replace an existing industry period"):
        build_industry_review(payload, "2026Q3")
    assert source.read_bytes() == before
