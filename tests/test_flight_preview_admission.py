import copy
import hashlib
import json

import pytest

from scripts.research.build_flight_coverage_preview import load_us_admission


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
    assert cells == {("AEROMEXICO", "2026M06", "MEX", "EWR")}
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
