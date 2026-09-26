from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

import pytest

from src.analysis_agent.stage13 import build, normalize, reconcile
from src.parse import aeromexico_ir_financial as parser
from src.pipeline.offline import block_network

FIXTURES = Path(__file__).parent / "fixtures/aeromexico_ir"


@pytest.fixture(scope="module")
def frozen():
    manifest = json.loads((FIXTURES / "manifest.json").read_text(encoding="utf-8"))
    parsed = {}
    with pytest.MonkeyPatch.context() as patch:
        def verified(record):
            content = (FIXTURES / (record["period_id"] + ".pdf")).read_bytes()
            if hashlib.sha256(content).hexdigest() != record["sha256"]:
                raise ValueError("Fixture hash mismatch")
            return content
        patch.setattr(parser, "_verified_bytes", verified)
        with block_network():
            for record in manifest:
                parsed[record["period_id"]] = parser.parse_report(record)
    return parsed


def keyed(frozen, q):
    return {r["metric_key"]: r for r in frozen[q][0]}


def test_rotated_quarterly_appendix_preserves_signs_and_aggregates(frozen):
    d = keyed(frozen, "2021Q1")
    assert d["total_revenue"]["value_raw"] == 6850
    assert d["operating_income"]["value_raw"] == -3445
    assert d["net_income"]["value_raw"] == -4192
    assert d["income_tax"]["value_raw"] == -859
    assert d["wages_salaries_benefits"]["value_raw"] == 2565
    assert d["total_revenue"]["source_page"] == 10
    assert d["rent_depreciation_amortization_combined"]["value_raw"] == 3047
    assert "depreciation_amortization" not in d and "aircraft_leasing_expense" not in d


@pytest.mark.parametrize("q,reported,adjusted,margin", [
    ("2021Q4", -6495, 5022, -57), ("2022Q1", 2992, 1001, -6)])
def test_adjusted_first_column_is_not_the_accounting_result(frozen, q, reported, adjusted, margin):
    d = keyed(frozen, q)
    assert d["ebitdar_reported"]["value_raw"] == reported
    assert d["ebitdar_ex_restructuring"]["value_raw"] == adjusted
    assert d["operating_margin"]["value_raw"] == margin
    assert "cask_ex_fuel" not in d
    assert d["cask_ex_fuel_ex_restructuring"]["unit_raw"] == "USD per ASK-km"


def test_dual_currency_and_plm_are_separate(frozen):
    d = keyed(frozen, "2022Q4")
    assert d["total_revenue"]["value_raw"] == 23037
    assert d["total_revenue"]["reported_usd_millions"] == 1190
    assert d["reported_fx_rate"]["value_raw"] == 19.3615
    assert d["adjusted_ebitdar"]["value_raw"] == 271.2
    assert d["ebitdar_reported"]["value_raw"] == 578.2
    assert d["operating_income_ex_plm"]["value_raw"] == 109.5
    assert d["operating_income"]["value_raw"] == 8065
    assert d["operating_income"]["reported_usd_millions"] == 417
    assert d["depreciation_amortization"]["value_raw"] == 2613
    assert d["aircraft_leasing_expense"]["value_raw"] == 517


def test_reported_mxn_remains_original_and_conversion_has_fx_parent(frozen):
    original = frozen["2023Q1"][0]
    normalized = normalize(original)
    r = next(r for r in normalized if r["metric_key"] == "total_revenue")
    assert r["value_raw"] == 19303
    assert r["value_normalized"] == 19303000000
    assert r["value_usd"] == pytest.approx(19303000000 / 18.1052)
    assert r["conversion_type"] == "company_convenience_close"
    assert len(r["normalization_inputs"]) == 2
    assert all("value_usd" not in x for x in original)


def test_footnote_number_is_not_ebitdar(frozen):
    assert keyed(frozen, "2024Q1")["adjusted_ebitdar"]["value_raw"] == 365


def test_original_source_difference_is_not_rewritten(frozen):
    d = keyed(frozen, "2024Q3")
    assert d["fuel_liters"]["value_raw"] == 461976
    assert d["net_income"]["value_raw"] == 195
    assert d["income_tax"]["value_raw"] == 59


def test_material_numeric_mutation_fails_reconciliation(frozen):
    rows = normalize(copy.deepcopy(frozen["2021Q1"][0]))
    assert all(c["status"] == "passed" for c in reconcile(rows))
    next(r for r in rows if r["metric_key"] == "total_revenue")["value_normalized"] += 100_000_000
    assert any(c["status"] == "unexplained" for c in reconcile(rows))


def test_unknown_format_and_number_are_rejected():
    with pytest.raises(ValueError):
        parser.first_row(["Total income unknown"], "Total income")
    with pytest.raises(ValueError):
        parser.number("NA")
    assert parser.number("(1,234.5)") == -1234.5


@pytest.mark.local_data
def test_all_targets_accounted_for_and_references_resolve():
    result = build()
    assert not result["unexplained"]
    assert len(result["checks"]) == 94
    assert len(result["coverage"]) == 22
    rows = result["rows"]
    ids = {r["record_id"] for r in rows}
    assert len(ids) == len(rows)
    for q in {r["period_id"] for r in rows}:
        extracted = {r["metric_key"] for r in rows if r["period_id"] == q}
        gaps = {r["metric_key"] for r in result["gaps"] if r["period_id"] == q}
        assert set(parser.TARGETS) <= extracted | gaps
        assert not extracted & gaps
    for row in rows:
        assert row["source_page"] > 0 and row["source_excerpt"]
        assert set(row["normalization_inputs"]) <= ids
        assert row["temporal_status"] == "not_certified"
    assert sum(c["status"] == "documented_source_difference" for c in result["comparison"]) == 3

