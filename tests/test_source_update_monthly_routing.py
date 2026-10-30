"""Keep calendar target months distinct from the explicitly observed native month."""

from copy import deepcopy

import pytest

from scripts.source_update_monthly_handoff import native_item, publication_scope, release_kind


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


def test_single_source_scope_keeps_am_and_unrelated_data_constraints_as_default():
    scope = publication_scope("am_traffic_ir")
    assert scope.startswith("Default single-source scope: Only the separately labelled Aeromexico")
    assert "preserve AFAC, other airlines, all seven theses and every other data payload" in scope
    assert "no quarterly aggregation or Airline Monthly editorial" in scope


def test_coalescing_scope_needs_exact_authorized_request_and_individually_ready_members():
    for product in ("am_traffic_ir", "aicm_traffic", "afac_carriers", "viva_traffic", "volaris_traffic_ir"):
        scope = publication_scope(product)
        assert "Only an explicitly authorized request with additional_sources" in scope
        assert "exact union of its individually ready, pinned members" in scope
        assert "Do not select extra sources automatically or wait for other sources" in scope
        assert "preserve all data outside that authorized union" in scope
    assert "additional_sources" not in publication_scope("bts_segments")
