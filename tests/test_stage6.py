from datetime import date

import pandas as pd

from src.transform.stage6_contracts import load_contracts
from src.transform.stage6_dimensions import build_dim_metric, gregorian_easter
from src.transform.stage6_facts import stage_length_adjusted
from src.parse.peers.stage5 import _line_value


def test_volaris_note_marker_is_not_parsed_as_negative_value() -> None:
    text = "Available seat miles (ASMs) (millions) (2) 9,059 8,885 2.0%"
    found = _line_value(text, (r"available seat miles \(asms\) \(millions.*?\)",))
    assert found is not None
    assert found[1] == 9_059


def test_stage_length_adjustment_uses_prospectus_reference() -> None:
    assert stage_length_adjusted(10.0, 1834.0) == 10.0
    assert stage_length_adjusted(10.0, None) is None


def test_gregorian_easter_and_quarter_split() -> None:
    assert gregorian_easter(2024) == date(2024, 3, 31)
    assert gregorian_easter(2026) == date(2026, 4, 5)


def test_dashboard_metric_catalog_is_glossary_backed() -> None:
    frame = build_dim_metric({"total_revenue"})
    dashboard = frame[frame["is_dashboard_metric"]]
    assert len(dashboard) >= 25
    assert dashboard["glossary_section"].notna().all()
    assert dashboard[["business_interpretation_up", "business_interpretation_down", "why_it_matters", "caveats"]].notna().all().all()


def test_every_stage6_gold_table_has_a_declared_contract() -> None:
    tables = load_contracts()["tables"]
    assert {"dim_carrier", "dim_period", "dim_metric", "dim_route"} <= set(tables)
    assert {"fact_carrier_metrics", "fact_route_traffic", "fact_airport_traffic", "fact_market_data", "fact_macro"} <= set(tables)
    assert all(definition.get("columns") for definition in tables.values())
