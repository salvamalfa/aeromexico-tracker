from datetime import UTC, datetime

import pytest

from src.parse.sec.crosscheck import _comparison


def test_crosscheck_materiality_uses_relative_difference() -> None:
    checked_at = datetime(2026, 8, 20, tzinfo=UTC)

    within = _comparison(
        metric_key="asm_total",
        period_id="2026Q1",
        source_a="quarterly",
        value_a=100.0,
        source_b="monthly",
        value_b=100.5,
        source_file_a="a",
        source_file_b="b",
        flagged_at=checked_at,
    )
    material = _comparison(
        metric_key="asm_total",
        period_id="2026Q1",
        source_a="quarterly",
        value_a=100.0,
        source_b="monthly",
        value_b=102.0,
        source_file_a="a",
        source_file_b="b",
        flagged_at=checked_at,
    )

    assert within["pct_diff"] == pytest.approx(0.005)
    assert within["is_material"] is False
    assert material["pct_diff"] == pytest.approx(0.02)
    assert material["is_material"] is True
