"""Every contributor preserves the exact retained shared payload on a retry."""

import copy
import json
from pathlib import Path

import pytest

from src.publish import source_data_members, source_data_scope


ROOT = Path(__file__).resolve().parents[1]
PRODUCTS = ("am_traffic_ir", "afac_carriers", "viva_traffic", "volaris_traffic_ir")
QUARTERS = "data/v1/flights/quarters.json"


@pytest.fixture
def retained_contributor(request):
    """Use the exact public projection and compact payload, without source replay."""
    spec = json.loads((ROOT / "config/publish/source-data-release.json").read_bytes())
    units = {unit["product"]: unit for unit in source_data_members.members(spec)}
    product = request.param
    adapter = source_data_scope.adapter(product)
    before = {name: (ROOT / "site" / name).read_bytes() for name in adapter.TARGETS}
    return adapter, before, copy.deepcopy(units[product]["projection"])


@pytest.mark.parametrize("retained_contributor", PRODUCTS, indirect=True)
def test_same_retained_projection_preserves_every_shared_payload_byte(retained_contributor):
    adapter, before, projection = retained_contributor
    original, original_projection = copy.deepcopy(before), copy.deepcopy(projection)
    output = adapter.public_outputs(before, projection)
    assert output == original
    assert adapter.public_outputs(output, projection) == original
    assert before == original and projection == original_projection


def test_changed_am_passenger_fact_changes_bytes_and_preserves_every_other_field():
    adapter = source_data_scope.adapter("am_traffic_ir")
    before = {QUARTERS: (ROOT / "site" / QUARTERS).read_bytes()}
    document = json.loads(before[QUARTERS])
    projection = copy.deepcopy(document["corporate_monthly_passengers"])
    original_projection = copy.deepcopy(projection)
    # Synthetic derivative for this pure projection test, never source authority.
    row = projection["records"][-1]
    for field in ("domestic", "reported_total", "total_segment_sum"):
        row[field] += 1
    output = adapter.public_outputs(before, projection)
    result = json.loads(output[QUARTERS])
    assert output[QUARTERS] != before[QUARTERS]
    assert result["corporate_monthly_passengers"] == projection
    assert {k: v for k, v in result.items() if k != "corporate_monthly_passengers"} == {
        k: v for k, v in document.items() if k != "corporate_monthly_passengers"
    }
    assert {k: v for k, v in projection.items() if k != "records"} == {
        k: v for k, v in original_projection.items() if k != "records"
    }
    assert json.loads(before[QUARTERS]) == document
    assert adapter.public_outputs(output, projection) == output


@pytest.mark.parametrize("retained_contributor", PRODUCTS, indirect=True)
@pytest.mark.parametrize("nonfinite", [float("nan"), float("inf"), float("-inf")])
def test_shared_contributor_rejects_nonfinite_candidate_passengers(retained_contributor, nonfinite):
    adapter, before, projection = retained_contributor
    rows = projection.get("series", projection)["records"]
    rows[-1]["reported_total"] = nonfinite
    original = copy.deepcopy(before)
    with pytest.raises(ValueError):
        adapter.public_outputs(before, projection)
    assert before == original


@pytest.mark.parametrize("retained_contributor", PRODUCTS, indirect=True)
def test_shared_contributor_does_not_accept_an_extra_publication_target(retained_contributor):
    adapter, before, projection = retained_contributor
    before["data/v1/executive.json"] = b'{"must_remain_outside_this_scope":true}\n'
    original = copy.deepcopy(before)
    with pytest.raises(ValueError):
        adapter.public_outputs(before, projection)
    assert before == original


@pytest.mark.parametrize("nonfinite", [float("nan"), float("inf"), float("-inf")])
def test_afac_new_month_append_rejects_nonfinite_existing_field(nonfinite):
    import math
    import subprocess
    from jsonschema import ValidationError

    spec = json.loads((ROOT / "config/publish/source-data-release.json").read_bytes())
    projection = copy.deepcopy(
        next(u["projection"] for u in spec["additional_sources"] if u["product"] == "afac_carriers")
    )
    adapter = source_data_scope.adapter("afac_carriers")
    before = {
        name: subprocess.check_output(["git", "show", f"{spec['baseline_commit']}:site/{name}"], cwd=ROOT)
        for name in adapter.TARGETS
    }
    quarters = json.loads(before["data/v1/flights/quarters.json"])
    assert quarters["monthly_passengers"]["records"][-1]["period_id"] < min(projection["periods"])
    row = projection["records"][-1]
    assert "reported_total" in row and math.isfinite(row["reported_total"])
    row["reported_total"] = nonfinite
    original = copy.deepcopy(before)
    with pytest.raises((ValueError, ValidationError)) as error:
        adapter.public_outputs(before, projection)
    assert "retry differs" not in str(error.value)
    assert before == original
