"""Protect the corporate monthly chart boundary and retained AFAC series."""

from copy import deepcopy
from pathlib import Path

import pandas as pd
import pytest
from jsonschema import ValidationError

from src.publish import am_monthly_projection as projection


def series():
    return {
        "entity": "AEROMEXICO",
        "source_url": "https://ir.aeromexico.com/node/9131/html",
        "source_sha256": "a" * 64,
        "captured_at": "2026-10-28T22:09:43+00:00",
        "documentary_date": "2026-10-06",
        "scope": "company_reported_month_including_charter_and_its_prior_year_comparative_not_AFAC",
        "records": [
            {
                "period_id": "2026M09",
                "date": "2026-09-01",
                "domestic": 1226000,
                "international": 627000,
                "reported_total": 1853000,
                "total_segment_sum": 1853000,
                "reconciliation_delta": 0,
            }
        ],
    }


def test_projection_preserves_afac_all_other_data_and_its_inputs():
    old = {
        "monthly_passengers": {"records": [{"date": "2026-06-01", "total": 3}]},
        "quarters": [{"period_id": "2026Q2"}],
        "route_network": {"world_geometry": {}},
    }
    before = deepcopy(old)
    corporate = series()
    result = projection.apply(old, corporate)
    assert old == before
    assert {k: v for k, v in result.items() if k != "corporate_monthly_passengers"} == old
    corporate["records"][0]["domestic"] = 0
    assert result["corporate_monthly_passengers"]["records"][0]["domestic"] == 1226000


@pytest.mark.parametrize(
    "change",
    [
        {"entity": "VOLARIS"},
        {"source_url": "javascript:alert(1)"},
        {"source_sha256": "unknown"},
        {"records": []},
    ],
)
def test_wrong_corporate_payload_fails_closed(change):
    value = series() | change
    with pytest.raises(ValidationError):
        projection.apply({}, value)


def test_project_requires_full_native_replay_before_reading_a_chart_cell(monkeypatch):
    called = []

    def reject(*args, **kwargs):
        called.append(kwargs)
        raise ValueError("physical source replay rejected")

    monkeypatch.setattr(projection, "run", reject)
    monkeypatch.setattr(pd, "read_parquet", lambda *a: pytest.fail("read before replay"))
    with pytest.raises(ValueError, match="physical source replay"):
        projection.project(Path("not-a-candidate"), "2026M09", "frozen-cutoff", "id")
    assert called == [{"check": True}]


@pytest.mark.parametrize("value", [float("inf"), float("-inf"), float("nan")])
@pytest.mark.parametrize(
    "field", ["domestic", "international", "reported_total", "total_segment_sum", "reconciliation_delta"]
)
def test_nonfinite_projection_never_reaches_browser_json(field, value):
    candidate = series()
    candidate["records"][0][field] = value
    with pytest.raises(ValueError):
        projection.apply({}, candidate)


def test_another_corporate_edition_cannot_silently_delete_prior_months():
    previous = series()
    previous["records"][0]["period_id"] = "2026M08"
    previous["records"][0]["date"] = "2026-08-01"
    retained = {"corporate_monthly_passengers": previous}
    before = deepcopy(retained)
    with pytest.raises(ValueError, match="Preserve prior corporate months"):
        projection.apply(retained, series())
    assert retained == before
