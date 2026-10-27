"""Approved comparable tolerance: synthetic amounts and metadata-only orchestration mocks."""

import copy
import json
import shutil
from decimal import Decimal as D
from uuid import uuid4

import pytest

from src.source_updates import readiness, retained_round
from src.source_updates.carrier_source_contract import (
    CASM_DEFINITION,
    NUMERIC_POLICY,
    comparable_relative_warning,
)
from src.source_updates.catalog import ROOT
from src.source_updates.volaris_sec_source import read
from src.source_updates.volaris_source_checks import reconcile
from tests.test_source_update_carrier import synthetic_volaris


def context():
    return dict(
        product="volaris_sec",
        edition="2026Q2",
        entity_as_reported="Synthetic issuer",
        carrier_key="VOLARIS",
        period_type="half_year",
        period_id="2025H1",
        period_start_date="2025-01-01",
        period_end_date="2025-06-30",
        segment="total",
        service_type=None,
        unit="usd_cents_per_seat_mile",
        definition=CASM_DEFINITION,
        coverage="scheduled_and_charter",
    )


def comparison(reference, derived, *, reported=None, calculated=None, resolution="0.01"):
    return comparable_relative_warning(
        D(reference),
        D(derived),
        reported_context=reported or context(),
        derived_context=calculated or context(),
        resolution=D(resolution),
    )


@pytest.mark.parametrize(
    "reference,derived",
    [
        ("100.00", "105.00"),
        ("100.00", "95.00"),
        ("100.00", "104.999999999999999999"),
        ("-100.00", "-105.00"),
        ("-100.00", "-95.00"),
    ],
)
def test_five_percent_is_inclusive_and_uses_absolute_official_reference(reference, derived):
    result = comparison(reference, derived)
    assert D(result["relative_difference_pct"]) <= 5
    assert D(result["absolute_difference"]) == abs(D(derived) - D(reference))
    assert result["reference_basis"] == "absolute_official_reported_value"
    assert result["official_reported_value"] == reference and result["official_value_preserved"] is True
    assert result["severity"] == "warning" and result["policy_id"] == NUMERIC_POLICY
    json.dumps(result, allow_nan=False)


@pytest.mark.parametrize(
    "reference,derived",
    [
        ("100.00", "105.000000000000001"),
        ("100.00", "94.999999999999999"),
        ("-100.00", "-105.000000000000001"),
        ("100", "-100"),
    ],
)
def test_above_five_percent_or_sign_reversal_remains_blocked(reference, derived):
    with pytest.raises(ValueError, match="exceeds"):
        comparison(reference, derived)


@pytest.mark.parametrize(
    "reference,derived", [("0", "0"), ("0", "0.001"), ("0.01", "0.0101"), ("-0.01", "-0.0101")]
)
def test_zero_and_one_quantum_reference_never_receive_an_automatic_percentage(reference, derived):
    with pytest.raises(ValueError, match="Zero/near-zero"):
        comparison(reference, derived)


@pytest.mark.parametrize("value", ["NaN", "Infinity", "-Infinity"])
def test_nonfinite_comparison_is_not_a_tolerated_difference(value):
    with pytest.raises(ValueError, match="finite"):
        comparison("100", value)


@pytest.mark.parametrize(
    "field,value",
    [
        ("period_id", "2026H1"),
        ("entity_as_reported", "Other issuer"),
        ("unit", "fraction"),
        ("definition", "CASM_ex_fuel"),
        ("coverage", "scheduled"),
    ],
)
def test_wrong_period_unit_definition_or_coverage_cannot_be_declared_comparable(field, value):
    calculated = context()
    calculated[field] = value
    with pytest.raises(ValueError, match="comparable"):
        comparison("100", "101", calculated=calculated)


def test_same_wrong_unit_or_definition_cannot_bypass_the_policy_and_pp_is_not_percent():
    for change in ({"unit": "percentage_points"}, {"unit": "percent"}, {"definition": "different_ratio"}):
        identity = {**context(), **change}
        with pytest.raises(ValueError, match="comparable"):
            comparison("80", "76", reported=identity, calculated=identity)
    result = comparison("100.00", "105.00")
    assert result["relative_difference_pct"] == "5.00"
    assert result["comparison_context"]["unit"] == "usd_cents_per_seat_mile"


@pytest.fixture
def tolerated_casm():
    native, _ = read(synthetic_volaris(), "2026Q2")
    target = native.index[
        native.source_table.eq("300") & native.source_row_number.eq(23) & native.source_column.eq(2)
    ][0]
    native.loc[target, ["source_value", "value"]] = ["8.20", 8.2]
    return native, target


def test_comparable_casm_keeps_official_value_and_all_three_source_references(tolerated_casm):
    from src.source_updates.carrier_source_contract import identifier
    from src.source_updates.carrier_source_gold import projection

    native, target = tolerated_casm
    before = native.copy(deep=True)
    details = reconcile(native)
    assert native.equals(before)
    assert details["numeric_check_status"] == "passed_with_warnings"
    assert details["numeric_warning_count"] == details["reconciliations_tolerated"] == 1
    warning = details["numeric_warnings"][0]
    assert warning["official_reported_value"] == "8.20" and D(warning["derived_value"]) == 8
    assert {r["metric_key"] for r in warning["sources"]} == {"casm", "operating_expenses", "asm_total"}
    assert all(r["source_locator"] and len(r["source_hash"]) == 64 for r in warning["sources"])
    assert warning["comparison_context"]["period_id"] == "2025H1"
    native["record_id"] = native.apply(identifier, axis=1)
    gold = projection(native, "volaris_sec")
    fact = gold.loc[gold.period_id.eq("2025H1") & gold.metric_key.eq("casm")].iloc[0]
    assert fact.value == 8.2 and fact.source_value == "8.20"
    assert fact.source_estimated is None and not fact.agent_eligible
    assert "numeric_warnings" not in gold.columns
    assert native.loc[target, "value"] == 8.2


@pytest.mark.parametrize(
    "field,value",
    [
        ("unit", "mxn"),
        ("period_id", "2026H1"),
        ("source_hash", "f" * 64),
        ("aviation_scope", "scheduled"),
    ],
)
def test_small_difference_cannot_relax_uncomparable_casm_inputs(tolerated_casm, field, value):
    native, _ = tolerated_casm
    target = native.index[
        native.source_table.eq("300") & native.source_row_number.eq(2) & native.source_column.eq(2)
    ][0]
    native.loc[target, field] = value
    with pytest.raises(ValueError, match="CASM fallback"):
        reconcile(native)


def test_official_repeated_values_are_still_strict_even_below_five_percent():
    native, _ = read(synthetic_volaris(), "2026Q2")
    for table, row, token in [(297, 23, "8.00"), (276, 9, "8.20")]:
        index = native.index[
            native.source_table.eq(str(table)) & native.source_row_number.eq(row) & native.source_column.eq(2)
        ][0]
        native.loc[index, ["source_value", "value"]] = [token, float(token)]
    with pytest.raises(ValueError, match="repeated metric"):
        reconcile(native)


def test_other_ratios_do_not_implicitly_gain_the_casm_policy():
    native, _ = read(synthetic_volaris(), "2026Q2")
    index = native.index[
        native.source_table.eq("300") & native.source_row_number.eq(13) & native.source_column.eq(2)
    ][0]
    native.loc[index, ["source_value", "value"]] = ["10.20", 10.2]
    # Give both values two decimals: the difference must not disappear into the
    # original integer token's rounding quantum.
    for row in (10, 11):
        selected = native.index[
            native.source_table.eq("300") & native.source_row_number.eq(row) & native.source_column.eq(2)
        ][0]
        native.loc[selected, "source_value"] = "1.00"
    with pytest.raises(ValueError, match="ADS=10CPO"):
        reconcile(native)


@pytest.fixture
def owned():
    path = ROOT / "tmp/source-updates" / ("numeric-policy-unit-" + uuid4().hex)
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)


def test_readiness_keeps_visible_warning_without_new_status_or_activation(owned, monkeypatch, tolerated_casm):
    from src.source_updates import carrier_source_candidate

    details = reconcile(tolerated_casm[0])
    receipts = owned / "receipts"
    receipts.mkdir(parents=True)
    (receipts / ("retained-" + "a" * 32 + ".json")).write_text(json.dumps({"status": "retained_unvalidated"}))
    (receipts / "carrier-source-volaris_sec-2026Q2.json").write_text(
        json.dumps(
            dict(
                retention_run_id="a" * 32,
                status="checks_passed",
                activation="none",
                publication="not_authorized",
                effective_as_of="2026-10-27T12:00:00-06:00",
            )
        )
    )
    returned = {
        **details,
        "status": "checks_passed",
        "output_sha256": {"unit_mock": "a" * 64},
        "code_files": {"unit_mock": "a" * 64},
        "activation": "none",
        "publication": "not_authorized",
    }
    monkeypatch.setattr(carrier_source_candidate, "run", lambda *a, **k: copy.deepcopy(returned))
    task = dict(
        id="volaris",
        product="volaris_sec",
        period="2026Q2",
        adapter="carrier_source",
        workspace=str(owned),
        receipt_id="a" * 32,
        required=True,
    )
    checked = readiness.check_task(task, "2026-10-27T12:00:00-06:00")
    assert checked["status"] == "checks_passed" and checked["numeric_check_status"] == "passed_with_warnings"
    assert (
        checked["numeric_warnings"] == details["numeric_warnings"] and checked["numeric_warning_count"] == 1
    )
    assert checked["latest_source_availability_verified"] is False and checked["activation"] == "none"


def test_batch_keeps_the_same_warning_in_its_receipt(owned, monkeypatch, tolerated_casm):
    details = reconcile(tolerated_casm[0])
    monkeypatch.setattr(retained_round, "spec", lambda p: {})
    monkeypatch.setattr(
        retained_round,
        "retain",
        lambda *a, **k: dict(
            run_id="a" * 32, originals={"fixture": {"downloaded_at": "2026-10-01T12:00:00Z"}}
        ),
    )
    returned = {
        **details,
        "rows": 1,
        "scope": "synthetic_propagation_only",
        "output_sha256": {"unit_mock": "a" * 64},
        "code_head": "synthetic",
        "lineage": {"records_expected": 1, "artifact_count": 1},
    }
    monkeypatch.setattr(retained_round, "run", lambda *a, **k: copy.deepcopy(returned))
    recipe = dict(
        version=1,
        source_root=str(owned.parent / "unused"),
        as_of="2026-10-27T12:00:00-06:00",
        items=[dict(product="afac_airports", period="2026M09", originals={"fixture": "unused"})],
    )
    result = retained_round.execute(recipe, owned, write=True)
    assert result["status"] == "checks_passed" and result["results"][0]["numeric_warning_count"] == 1
    assert result["results"][0]["numeric_warnings"] == details["numeric_warnings"]
    receipt = json.loads(next(owned.glob("retained-round-*.json")).read_text())
    assert receipt["results"][0]["numeric_check_status"] == "passed_with_warnings"
    assert receipt["publication"] == "not_authorized" and receipt["activation"] == "none"
