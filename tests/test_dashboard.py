from __future__ import annotations

from pathlib import Path

import pandas as pd
from streamlit.testing.v1 import AppTest

from src.config import PATHS
from src.dashboard.check_manual_freshness import check
from src.dashboard.data import metric_definition, query_df
from src.dashboard.validate_stage8 import DASHBOARD_METRICS, PAGES, contrast
from src.dashboard.theme import CARRIER_COLORS, INK, MUTED, WHITE


def test_dashboard_registers_exactly_ten_pages() -> None:
    source = (PATHS.root / "src" / "dashboard" / "app.py").read_text(encoding="utf-8")
    assert len(PAGES) == 10
    assert source.count("st.Page(") == 10


def test_every_dashboard_metric_has_business_interpretation() -> None:
    for key in DASHBOARD_METRICS:
        definition = metric_definition(key)
        for field in ("why_it_matters", "business_interpretation_up", "business_interpretation_down"):
            assert pd.notna(definition[field]) and str(definition[field]).strip(), (key, field)


def test_stage8_extracts_are_bounded_and_valid() -> None:
    routes = pd.read_parquet(PATHS.gold / "fact_route_traffic_summary.parquet")
    assert len(routes) == 66_770
    assert routes["load_factor"].dropna().between(0, 1.10).all()
    assert routes["source_hash"].str.fullmatch(r"[0-9a-f]{64}").all()
    spread = pd.read_parquet(PATHS.gold / "fact_spread_decomposition.parquet")
    assert len(spread) == 4
    assert (~spread["is_identified"]).sum() == 1
    coverage = pd.read_parquet(PATHS.gold / "fact_dashboard_coverage.parquet")
    assert len(coverage) > 200
    assert coverage["coverage_pct"].dropna().ge(0).all()


def test_summary_page_renders_real_anchor_without_exception() -> None:
    app = AppTest.from_file(str(PATHS.root / "src" / "dashboard" / "app.py"), default_timeout=30).run()
    assert not app.exception
    assert len(app.metric) == 6
    quarter = query_df("SELECT total_revenue FROM v_aeromexico_quarterly WHERE period_id='2026Q1'").iloc[0, 0]
    assert quarter == 1_341_000_000


def test_palette_meets_wcag_thresholds() -> None:
    assert contrast(INK, WHITE) >= 4.5
    assert contrast(MUTED, WHITE) >= 4.5
    assert all(contrast(color, WHITE) >= 3.0 for color in CARRIER_COLORS.values())


def test_afac_freshness_uses_real_source_date() -> None:
    result = check("afac", max_age_days=62)
    assert result["last_date"] == "2026-06-30"
    assert result["age_days"] >= 0
    assert isinstance(result["is_stale"], bool)


def test_refresh_workflow_has_failure_and_manual_source_controls() -> None:
    workflow = (PATHS.root / ".github" / "workflows" / "refresh.yml").read_text(encoding="utf-8")
    assert "issues: write" in workflow
    assert "validation-failed" in workflow
    assert "manual-source" in workflow
    assert "check_manual_freshness" in workflow
