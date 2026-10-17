import copy
import hashlib
import json

import pandas as pd
import pytest

from scripts.research.build_flight_coverage_preview import load_us_admission, validate_us_admission


def policy():
    return {"default_enabled": False, "review_or_rejected_cells_included": 0,
            "new_calls": 0, "fits": 0, "activates_analysis": False,
            "retained_estimated_flights": 30,
            "cells": [{"carrier_key": "AEROMEXICO", "period_id": "2026M06",
                       "origin_iata": "MEX", "destination_iata": "EWR",
                       "estimated_flights_retained": 30}]}


def test_screen_is_default_off_and_requires_both_explicit_inputs(tmp_path):
    assert load_us_admission(None, enabled=False) == (None, {})
    with pytest.raises(ValueError, match="both explicit"):
        load_us_admission(None, enabled=True)
    with pytest.raises(ValueError, match="both explicit"):
        load_us_admission(tmp_path / "missing", enabled=False)


def test_exact_operator_direction_month_and_policy_hash_are_preserved(tmp_path):
    path = tmp_path / "admission.json"
    path.write_text(json.dumps(policy()))
    cells, receipt = load_us_admission(path, enabled=True)
    assert cells == {("AEROMEXICO", "2026M06", "MEX", "EWR"): 30.0}
    assert receipt["us_estimate_admission_sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()
    assert receipt["admitted_us_estimate_cell_count"] == 1
    assert receipt["retained_us_frequencies_admitted"] == 30


@pytest.mark.parametrize("change", ["duplicate", "review", "total", "month", "calls", "nan_total", "bool_value"])
def test_invalid_or_unreviewed_cell_policy_fails_before_a_preview(tmp_path, change):
    value = policy()
    if change == "duplicate":
        value["cells"].append(copy.deepcopy(value["cells"][0]))
        value["retained_estimated_flights"] = 60
    elif change == "review":
        value["review_or_rejected_cells_included"] = 1
    elif change == "total":
        value["retained_estimated_flights"] = 31
    elif change == "month":
        value["cells"][0]["period_id"] = "2026M13"
    elif change == "nan_total":
        value["retained_estimated_flights"] = float("nan")
    elif change == "bool_value":
        value["cells"][0]["estimated_flights_retained"] = True
    else:
        value["new_calls"] = 1
    path = tmp_path / "policy.json"
    path.write_text(json.dumps(value))
    with pytest.raises(ValueError):
        load_us_admission(path, enabled=True)


def _screen_and_gold(tmp_path, *, actual=30, missing=False, duplicate=False):
    path = tmp_path / "policy.json"
    path.write_text(json.dumps(policy()))
    cells, _ = load_us_admission(path, enabled=True)
    target = dict(carrier_key="AEROMEXICO", period_id="2026M06", origin_iata="MEX",
                  destination_iata="EWR", departures_estimated=actual)
    # An unrelated count is not part of this screen's frozen acceptance.
    rows = [{**target, "destination_iata": "JFK", "departures_estimated": 3000}]
    if not missing:
        rows.append(target)
    if duplicate:
        rows.append(target.copy())
    pd.DataFrame(rows).to_parquet(tmp_path / "fact_route_carrier_international_estimate.parquet")
    return cells


def test_screen_binds_the_exact_retained_value_without_admitting_other_keys(tmp_path):
    cells = _screen_and_gold(tmp_path)
    validate_us_admission(cells, tmp_path)
    assert cells == {("AEROMEXICO", "2026M06", "MEX", "EWR"): 30.0}


@pytest.mark.parametrize("actual", [3000, 30.0000000001, None, float("nan"), float("inf"), -30])
def test_changed_or_unknown_retained_values_cannot_reuse_a_screen(tmp_path, actual):
    cells = _screen_and_gold(tmp_path, actual=actual)
    with pytest.raises(ValueError, match="differs from the frozen"):
        validate_us_admission(cells, tmp_path)


def test_missing_retained_cell_cannot_reuse_a_screen(tmp_path):
    cells = _screen_and_gold(tmp_path, missing=True)
    with pytest.raises(ValueError, match="missing from Gold"):
        validate_us_admission(cells, tmp_path)


def test_duplicate_retained_cell_cannot_reuse_a_screen(tmp_path):
    cells = _screen_and_gold(tmp_path, duplicate=True)
    with pytest.raises(ValueError, match="Duplicate retained"):
        validate_us_admission(cells, tmp_path)


def test_default_off_does_not_read_estimate_gold(tmp_path):
    validate_us_admission(None, tmp_path / "not-present")


def test_changed_screen_value_fails_before_any_preview_build_or_write(tmp_path, monkeypatch):
    from types import SimpleNamespace
    from scripts.research import build_flight_coverage_preview as preview

    _screen_and_gold(tmp_path, actual=3000)
    monkeypatch.setattr(preview, "PATHS", SimpleNamespace(root=tmp_path, gold=tmp_path))
    monkeypatch.setattr(preview, "committed_preview_inputs", lambda: "a" * 40)

    def must_not_run(*args, **kwargs):
        pytest.fail("Invalid admission reached baseline verification or warehouse rebuilding")

    monkeypatch.setattr(preview, "verify_site", must_not_run)
    monkeypatch.setattr(preview, "refresh_retained_warehouse", must_not_run)
    out = tmp_path / "analysis_runs/research/candidate"
    with pytest.raises(ValueError, match="differs from the frozen"):
        preview.build_preview(out, include_existing_us_estimates=True,
                              us_estimate_admission=tmp_path / "policy.json")
    assert not out.exists()
    assert not (tmp_path / "web").exists()
