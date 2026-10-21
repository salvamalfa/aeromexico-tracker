"""Quarterly publication boundaries: duration, native units and frozen datasets."""
import copy
import json
from pathlib import Path

import pytest

from src.analysis_agent import quarterly_release as quarter
from src.analysis_agent.evidence import digest
from src.publish import quarterly_overlay as overlay


def package_identity():
    package = dict(schema_version=quarter.SCHEMA, entity_key="AEROMEXICO", period_id="2026Q3",
                   code_fingerprint=quarter.sha(Path(quarter.__file__).read_bytes()), metrics=[])
    package["evidence_fingerprint"] = digest(package)
    package["package_id"] = "2026Q3_" + package["evidence_fingerprint"]
    return package


def test_quarterly_identity_cannot_be_relabelled_or_silently_replayed():
    package = package_identity()
    assert quarter.verify(package, verify_files=False)["status"] == "passed"
    for key, value in [("period_id", "2026Q2"), ("entity_key", "VOLARIS"),
                       ("code_fingerprint", "0" * 64), ("metrics", [{"value": 541.7}])]:
        changed = {**package, key: value}
        with pytest.raises(ValueError):
            quarter.verify(changed, verify_files=False)


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value))


def test_quarterly_overlay_rejects_monthly_changes_and_unrelated_activation(tmp_path):
    before = tmp_path / "before"
    candidate = tmp_path / "candidate"
    old = {"months": ["2026M07"], "passengers": [123]}
    new_exec = {"new_financial_quarter": "2026Q3"}
    new_analysis = {"approved_thesis": "quarterly"}
    thesis_path = "data/v1/analysis/2026Q3.json"
    for folder in (before, candidate):
        write(folder / "data/v1/flights/quarters.json", old)
        write(folder / "data/v1/news.json", {"approved": 3})
        write(folder / "data/v1/analysis/VOLARIS/2026Q2.json", {"approved": True})
        write(folder / "data/v1/executive.json", {"prior": True})
    write(candidate / "data/v1/executive.json", new_exec)
    write(candidate / thesis_path, new_analysis)
    overlay.require_preserved_data(candidate, before, new_exec, new_analysis, thesis_path)
    for relative in ["flights/quarters.json", "news.json", "analysis/VOLARIS/2026Q2.json"]:
        file = candidate / "data/v1" / relative
        original = file.read_bytes()
        file.write_bytes(original + b" ")
        with pytest.raises(ValueError, match="frozen published dataset"):
            overlay.require_preserved_data(candidate, before, new_exec, new_analysis, thesis_path)
        file.write_bytes(original)
    write(candidate / "data/v1/analysis/VIVA_AEROBUS/2026Q3.json", {"unapproved": True})
    with pytest.raises(ValueError, match="unrelated datasets"):
        overlay.require_preserved_data(candidate, before, new_exec, new_analysis, thesis_path)


def test_executive_projection_preserves_published_peers_and_history(monkeypatch):
    baseline = json.loads(Path("site/data/v1/executive.json").read_bytes())
    original = copy.deepcopy(baseline)
    if "2026Q3" in baseline["views"]:
        # The committed site may already include this release. Use its retained
        # prior history as the explicit baseline, not synthetic peer values.
        baseline["records"] = [r for r in baseline["records"] if r["period_id"] != "2026Q3"]
        del baseline["views"]["2026Q3"]
        block = baseline["entities"]["AEROMEXICO"]
        block["records"] = [r for r in block["records"] if r["period_id"] != "2026Q3"]
        del block["views"]["2026Q3"]
        original = copy.deepcopy(baseline)
    values = {"passengers": 6161000, "ask": 9395000000 * 1.609344, "load": .883,
              "rask": 17.2 / 1.609344, "cask": 15.1 / 1.609344,
              "spread": 2.1 / 1.609344, "rpm": 8296000000, "casm_ex": 10.1}
    monkeypatch.setattr(overlay, "verify", lambda package: None)
    monkeypatch.setattr(overlay, "calculate", lambda package: {
        "nodes": [{"period_id": "2026Q3", "key": k, "value": v} for k, v in values.items()]})
    result = overlay.executive_projection(baseline, {})
    assert baseline == original
    assert result["records"][:-1] == baseline["records"]
    assert {k: v for k, v in result["views"].items() if k != "2026Q3"} == baseline["views"]
    for entity in ("VIVA_AEROBUS", "VOLARIS", "INDUSTRY"):
        assert result["entities"][entity] == baseline["entities"][entity]
    assert result["records"][-1]["ask_km"] == pytest.approx(15119786880)
    assert result["records"][-1]["rask_cents_per_km"] == pytest.approx(10.687584506482143)
    with pytest.raises(ValueError, match="absent financial period"):
        overlay.executive_projection(result, {})


@pytest.mark.local_data
def test_primary_source_replay_preserves_duration_and_canonical_calculations():
    folder = Path("/workspace/aeromexico-tracker/tmp/quarterly-2026Q3/review")
    if not (folder / "captures.json").exists():
        pytest.skip("The authorized quarterly primary-source capture is not present")
    package, calculations = quarter.prepare(folder)
    assert quarter.verify(package)["status"] == "passed"
    nodes = {(n["period_id"], n["key"]): n for n in calculations["nodes"]}
    assert ("2026Q3", "cashflow_ytd") not in nodes
    assert nodes[("2026YTD9", "cashflow_ytd")]["value"] == 541700000
    assert nodes[("2026Q3", "revenue")]["value"] == 1619000000
    assert nodes[("2026Q3", "ebitdar_rounded_yoy")]["value"] == -11.9
    assert nodes[("2026Q3", "operating_income_rounded_yoy")]["value"] == -25
    assert nodes[("2026Q3", "fuel_recapture_illustrative")]["value"] == pytest.approx(145.3 / 171.5)
    assert nodes[("2026Q3", "fuel_recapture_reported")]["value"] == pytest.approx(1.13)
    for node in calculations["nodes"]:
        assert node["calculation_id"] == "calc_" + digest({k: v for k, v in node.items() if k != "calculation_id"})
