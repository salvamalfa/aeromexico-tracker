from __future__ import annotations

import pandas as pd

from src.config import PATHS
from src.dashboard.check_manual_freshness import check
from src.dashboard.data import data_as_of, query_df
from src.dashboard.navigation import READER_TAB_SPECS


def test_portable_dashboard_registers_flights_as_the_third_tab() -> None:
    assert [(spec.key, spec.title) for spec in READER_TAB_SPECS] == [
        ("reading", "Lectura ejecutiva"),
        ("economy", "Economía unitaria"),
        ("flights", "Vuelos"),
    ]


def test_afac_freshness_uses_real_source_date() -> None:
    result = check("afac", max_age_days=62)
    assert result["last_date"] == "2026-06-30"
    assert result["age_days"] >= 0
    assert isinstance(result["is_stale"], bool)


def test_dashboard_cutoff_uses_latest_preserved_artifact_not_future_period_end() -> None:
    expected = query_df(
        "SELECT MAX(CAST(downloaded_at AS DATE)) AS date FROM dim_source_artifact"
    ).iloc[0, 0]
    expected_date = pd.to_datetime(expected)
    months = (
        "", "ene", "feb", "mar", "abr", "may", "jun",
        "jul", "ago", "sep", "oct", "nov", "dic",
    )
    assert data_as_of() == f"{expected_date.day:02d} {months[expected_date.month]} {expected_date.year}"
    assert expected_date.date() <= pd.Timestamp.now().date()


def test_refresh_workflow_has_failure_and_manual_source_controls() -> None:
    workflow = (PATHS.root / ".github" / "workflows" / "refresh.yml").read_text(encoding="utf-8")
    assert "issues: write" in workflow
    assert "validation-failed" in workflow
    assert "manual-source" in workflow
    assert "check_manual_freshness" in workflow
