import copy
import json
from pathlib import Path

import pytest

from src.conversational_analytics.tools._catalog_periods import compact_catalog_periods


def _expanded(value):
    if isinstance(value, dict):
        return {key: _expanded(child) for key, child in value.items()}
    if not isinstance(value, list):
        return value
    periods = []
    for item in value:
        if ".." not in item:
            periods.append(item)
            continue
        start, end = item.split("..")
        grain = start[4]
        year, phase = int(start[:4]), int(start[5:])
        while True:
            current = f"{year}M{phase:02}" if grain == "M" else f"{year}Q{phase}"
            periods.append(current)
            if current == end:
                break
            phase += 1
            if phase > (12 if grain == "M" else 4):
                year, phase = year + 1, 1
    return sorted(periods)


def test_period_transport_keeps_gaps_grains_and_all_metadata():
    months = [f"2020M{month:02}" for month in range(1, 13) if month != 8]
    quarters = [f"2020Q{quarter}" for quarter in range(1, 5)]
    original = {
        "periods": {"flight": months + quarters},
        "metrics": [{"id": "flights", "unit": "vuelos", "coverage": "partial"}],
        "route_periods": {"carrier": {"monthly": months}},
    }
    saved = copy.deepcopy(original)
    compact = compact_catalog_periods(original)
    assert original == saved
    assert compact["periods"]["flight"] == ["2020M01..2020M07", "2020M09..2020M12", "2020Q1..2020Q4"]
    assert _expanded(compact["periods"]) == _expanded(original["periods"])
    assert _expanded(compact["route_periods"]) == _expanded(original["route_periods"])
    assert "2020M08" not in _expanded(compact["periods"]["flight"])
    assert compact["metrics"] == original["metrics"]
    assert "export presence does not establish" in compact["period_id_encoding"]


def test_period_transport_crosses_years_without_joining_missing_month():
    values = [f"2025M{month:02}" for month in range(7, 13)] + [
        f"2026M{month:02}" for month in (1, 2, 4, 5, 6)
    ]
    compact = compact_catalog_periods({"periods": {"monthly": values}})
    assert compact["periods"]["monthly"] == ["2025M07..2026M02", "2026M04..2026M06"]
    assert _expanded(compact["periods"]["monthly"]) == sorted(values)


@pytest.mark.parametrize("invalid", ["2026M13", "2026Q5", None, "2026M01"])
def test_period_transport_does_not_normalize_malformed_or_duplicate_ids(invalid):
    original = {"periods": {"monthly": [f"2026M{month:02}" for month in range(1, 10)] + [invalid]}}
    assert compact_catalog_periods(original) == original


def test_real_model_catalog_fits_transport_and_preserves_full_http_catalog():
    from src.conversational_analytics.data.snapshot import Snapshot
    from src.conversational_analytics.presentation import DisplayRegistry
    from src.conversational_analytics.tools.registry import ToolRegistry

    registry = ToolRegistry(Snapshot(Path("site")))
    full = registry.catalog()
    result = registry.invoke("get_data_catalog", {})
    presented = DisplayRegistry().add_tool_result(result, "get_data_catalog", "catalog-call")
    assert len(json.dumps(presented, ensure_ascii=False, separators=(",", ":")).encode()) <= 16_000
    assert _expanded(result["periods"]) == _expanded(full["periods"])
    assert _expanded(result["route_periods"]) == _expanded(full["route_periods"])
    assert {key: result[key] for key in full if key not in {"periods", "route_periods"}} == {
        key: value for key, value in full.items() if key not in {"periods", "route_periods"}
    }
    assert registry.catalog() == full
