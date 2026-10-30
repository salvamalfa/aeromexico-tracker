"""Keep calendar target months distinct from the explicitly observed native month."""

from copy import deepcopy

import pytest

from scripts.source_update_monthly_handoff import native_item, release_kind


def item(product, source):
    return {
        "id": "retained",
        "product": product,
        "period": "2026M09",
        "source_period": source,
        "adapter": "retained",
        "workspace": "tmp/candidate",
        "receipt_id": "a" * 32,
        "candidate_as_of": "2026-10-28T12:00:00Z",
        "cadence": "monthly",
        "used": True,
        "depends_on": [],
    }


@pytest.mark.parametrize(
    "product,month", [("afac_carriers", "2026M08"), ("bts_segments", "2026M07"), ("afac_airports", "2026M09")]
)
def test_native_month_conversion_preserves_original_calendar_target(product, month):
    original = item(product, month)
    before = deepcopy(original)
    normalized = native_item(original)
    assert original == before and original["period"] == "2026M09"
    assert normalized["period"] == month and "source_period" not in normalized
    assert "cadence" not in normalized and normalized["required"] is True


@pytest.mark.parametrize(
    "product,month", [("am_traffic_ir", "2026M08"), ("bts_segments", "2026M10"), ("afac_carriers", "2026Q3")]
)
def test_unapproved_or_future_native_period_cannot_be_equated(product, month):
    with pytest.raises(ValueError):
        native_item(item(product, month))


def test_bts_assesses_dependency_without_selecting_a_data_exposure_gate():
    assert release_kind("bts_segments") == "source_dependency_assessment"
    assert release_kind("aicm_traffic") == "source_data"
