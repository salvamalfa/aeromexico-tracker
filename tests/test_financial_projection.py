"""Unit definitions and preservation use synthetic values; real sources replay separately."""

import copy
import json
from pathlib import Path
import pytest
from jsonschema import Draft202012Validator
from src.publish import financial_projection as p
from src.publish.financial_scope import preserved_executive


@pytest.fixture
def package(monkeypatch):
    values = {
        "2026Q3": dict(
            revenue=1619e6,
            asm=9395e6,
            trasm=17.2,
            casm=15.1,
            expenses=1429e6,
            load=0.883,
            trasm_yoy=12.2,
            casm_yoy=19.4,
            asm_yoy=1.3,
            passengers_yoy=-3.2,
        ),
        "2025Q3": dict(revenue=1425e6, asm=9277e6, trasm=15.4, casm=12.7, expenses=1172e6, load=0.882),
    }
    package = {
        "metrics": [
            {"period_id": period, "metric_key": key, "value": value}
            for period, row in values.items()
            for key, value in row.items()
        ]
    }

    def verify(value):
        if value.get("invalid_source"):
            raise ValueError("Source bytes changed")

    monkeypatch.setattr(p, "verify", verify)
    nodes = dict(
        values["2026Q3"],
        passengers=6161e3,
        ask=9395e6 * p.MILE_KM,
        rask=17.2 / p.MILE_KM,
        cask=15.1 / p.MILE_KM,
        spread=(17.2 - 15.1) / p.MILE_KM,
        rpm=8296e6,
        casm_ex=10.1,
    )
    monkeypatch.setattr(
        p,
        "calculate",
        lambda value: {"nodes": [{"period_id": "2026Q3", "key": k, "value": v} for k, v in nodes.items()]},
    )
    return package


def test_total_revenue_and_capacity_reproduce_reported_growth_not_passenger_yield(package):
    recon = p.reconciliation(package)
    assert recon["periods"]["2026Q3"]["trasm_from_printed_totals"] == pytest.approx(17.232570516232038)
    assert recon["periods"]["2025Q3"]["trasm_from_printed_totals"] == pytest.approx(15.36056914950954)
    assert recon["growth_from_printed_total_revenue_and_asm_percent"] == pytest.approx(12.187057318655858)
    assert recon["growth_from_rounded_unit_values_percent"] == pytest.approx(11.688311688311682)
    assert recon["reported_trasm_growth_percent"] == 12.2
    assert recon["reported_casm_growth_percent"] == 19.4
    assert recon["casm_growth_from_rounded_unit_values_percent"] == pytest.approx(18.89763779527559)
    current = recon["periods"]["2026Q3"]
    assert current["casm_implied_cost_usd_not_statement_expenses"] == 1418645e3
    assert current["statement_operating_expenses_usd"] == 1429e6
    assert current["rask_reported_converted_cents_usd_per_ask"] * p.MILE_KM == pytest.approx(17.2)
    assert "not passenger-only" in recon["numerator"]


def test_missing_or_inconsistent_source_is_not_filled_with_a_financial_ratio(package):
    bad = copy.deepcopy(package)
    bad["invalid_source"] = True
    with pytest.raises(ValueError, match="Source bytes"):
        p.reconciliation(bad)
    bad = copy.deepcopy(package)
    for metric in bad["metrics"]:
        if metric["metric_key"] == "revenue" and metric["period_id"] == "2026Q3":
            metric["value"] = 1414e6
    with pytest.raises(ValueError, match="TRASM precision"):
        p.reconciliation(bad)


def test_projection_has_only_one_new_aeromexico_quarter_and_explicit_comparison_versions(package):
    root = Path(__file__).resolve().parents[1]
    baseline = json.loads((root / "site/data/v1/executive.json").read_bytes())
    if "2026Q3" in baseline["views"]:
        baseline["records"] = [r for r in baseline["records"] if r["period_id"] != "2026Q3"]
        baseline["views"].pop("2026Q3")
        block = baseline["entities"]["AEROMEXICO"]
        block["records"] = [r for r in block["records"] if r["period_id"] != "2026Q3"]
        block["views"].pop("2026Q3")
        block["last_period"] = "2026Q2"
        block["quarter_count"] = len(block["records"])
    before = copy.deepcopy(baseline)
    new = p.executive_projection(baseline, package)
    assert baseline == before
    preserved_executive(before, new)
    assert new["metadata"]["default_period"] == before["metadata"]["default_period"]
    assert new["metadata"]["load_rask_correlation"] == before["metadata"]["load_rask_correlation"]
    kpis = {k["key"]: k for k in new["views"]["2026Q3"]["kpis"]}
    assert kpis["rask_cents_per_km"]["yoy"]["display"] == "+12.2%"
    assert kpis["cask_cents_per_km"]["yoy"]["display"] == "+19.4%"
    assert kpis["load_factor_reported"]["yoy"]["display"] == "+0.1 pp"
    assert (
        kpis["rask_cents_per_km"]["qoq"]
        == p._period_view(new["records"][-1], {r["period_id"]: r for r in before["records"]})["kpis"][0][
            "qoq"
        ]
    )
    assert new["records"][-1]["unit_margin_cents_per_km"] == pytest.approx(1.3048795036984)
    old = next(r for r in new["records"] if r["period_id"] == "2025Q3")
    assert old["load_factor_reported"] == 0.883
    notes = " ".join(new["views"]["2026Q3"]["narrative"]["paragraphs"])
    assert "88,2%" in notes and "88,3%" in notes and "17,2/15,4" in notes and "19,4%" in notes
    schema = json.loads((root / "contracts/web/executive.schema.json").read_bytes())
    assert list(Draft202012Validator(schema).iter_errors(new)) == []
    with pytest.raises(ValueError, match="already exists"):
        p.executive_projection(new, package)
