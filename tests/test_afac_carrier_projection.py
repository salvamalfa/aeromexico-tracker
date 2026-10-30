"""Business-universe and preservation checks for the retained AFAC chart bridge."""

import copy
import json

import pandas as pd
import pytest

from src.publish import afac_carrier_projection as bridge
from src.source_updates.catalog import ROOT


@pytest.fixture
def native():
    rows = []
    for month in ("2026M06", "2026M07", "2026M08"):
        for segment in ("domestic", "international"):
            for key in sorted(bridge.MEMBERS):
                for service, value in (("scheduled", 100), ("charter", 1)):
                    rows.append(
                        dict(
                            statement="database_row",
                            period_id=month,
                            period_type="month",
                            entity_as_reported=key,
                            carrier_key=key,
                            source_group="Mexicana",
                            segment=segment,
                            service_type=service,
                            value=float(value),
                            metric_key="passengers_transported",
                            unit="passengers_transported",
                            scale=1.0,
                        )
                    )
            for name, country, value in (
                ("Unmapped Mexican charter", "Mexicana", 7),
                ("Foreign operator", "Europea", 9999),
            ):
                rows.append(
                    dict(
                        statement="database_row",
                        period_id=month,
                        period_type="month",
                        entity_as_reported=name,
                        carrier_key=None,
                        source_group=country,
                        segment=segment,
                        service_type="charter",
                        value=float(value),
                        metric_key="passengers_transported",
                        unit="passengers_transported",
                        scale=1.0,
                    )
                )
    return pd.DataFrame(rows)


@pytest.fixture
def source():
    return dict(
        database_sha256="a" * 64,
        pdf_sha256="b" * 64,
        source_url="https://datatur.sectur.gob.mx/Documentoscompartidos/afac/DB_AFAC.zip",
        captured_at="2026-10-28T15:02:22.412194+00:00",
        scope="reported_Mexican_carrier_passengers_scheduled_and_charter_not_foreign_or_route_estimates",
    )


@pytest.fixture
def before(native):
    q, m = [json.loads((ROOT / "site" / path).read_bytes()) for path in bridge.TARGETS]
    q["monthly_passengers"].update(
        period_start="2026-06-01", period_end="2026-06-30", observed_months=1, calendar_months=1
    )
    record = copy.deepcopy(q["monthly_passengers"]["records"][-1])
    record.update(
        period_id="2026M06",
        date="2026-06-01",
        domestic=202.0,
        international=202.0,
        total_segment_sum=404.0,
        reported_total=404.0,
        reconciliation_delta=0.0,
    )
    q["monthly_passengers"]["records"] = [record]
    q.pop("corporate_monthly_passengers", None)
    values, _ = bridge.monthly_values(native, "2026M06")
    m["months"] = [
        dict(
            period_id="2026M06",
            period_label="jun 26",
            segments={
                segment: bridge._segment_block(part["values"], part["denominator"])
                for segment, part in values.items()
            },
        )
    ]
    m["metadata"].update(first_period="2026M06", last_period="2026M06")
    m["metadata"].pop("source_editions", None)
    m["metadata"].pop("method_breaks", None)
    return {bridge.TARGETS[0]: json.dumps(q).encode(), bridge.TARGETS[1]: json.dumps(m).encode()}


def test_literal_mexican_denominator_includes_unknown_and_excludes_foreign(native):
    values, unknown = bridge.monthly_values(native, "2026M08")
    assert values["domestic"]["denominator"] == 411
    assert values["international"]["denominator"] == 411
    assert values["total"]["denominator"] == 822
    assert values["total"]["values"]["AEROMEXICO"] == 404
    assert unknown["domestic"] == ["Unmapped Mexican charter"]


def test_missing_explicit_charter_zero_is_not_imputed(native):
    remove = native.carrier_key.eq("AEROMEXICO_CONNECT") & native.service_type.eq("charter")
    with pytest.raises(ValueError, match="absence is not zero"):
        bridge.monthly_values(native[~remove], "2026M08")


@pytest.mark.parametrize("value", [-1, float("nan"), 1.5, float("inf")])
def test_invalid_passenger_counts_fail_closed(native, value):
    native.loc[native.source_group.eq("Mexicana"), "value"] = value
    with pytest.raises((ValueError, OverflowError)):
        bridge.monthly_values(native, "2026M08")


def test_duplicate_operator_service_is_rejected(native):
    with pytest.raises(ValueError, match="Duplicate"):
        bridge.monthly_values(pd.concat([native, native.iloc[[0]]]), "2026M06")


def test_subtotal_cannot_enter_operator_universe(native):
    native.loc[native.entity_as_reported.eq("Unmapped Mexican charter"), "entity_as_reported"] = (
        "Total general"
    )
    with pytest.raises(ValueError, match="subtotal"):
        bridge.monthly_values(native, "2026M08")


def test_append_preserves_all_history_and_no_incomplete_quarter(native, before, source):
    gold = native[native.period_id.eq("2026M08")]
    projection = bridge.project(native, gold, "2026M08", before, source)
    result = bridge.public_outputs(before, projection)
    q0, m0 = [json.loads(before[p]) for p in bridge.TARGETS]
    q1, m1 = [json.loads(result[p]) for p in bridge.TARGETS]
    assert projection["periods"] == ["2026M07", "2026M08"]
    assert q1["monthly_passengers"]["records"][:1] == q0["monthly_passengers"]["records"]
    assert m1["months"][:1] == m0["months"]
    assert q1["quarters"] == q0["quarters"] and m1["quarters"] == m0["quarters"]
    assert {k: v for k, v in q1.items() if k != "monthly_passengers"} == {
        k: v for k, v in q0.items() if k != "monthly_passengers"
    }
    assert m1["metadata"]["method_breaks"] == ["2026M07"]
    assert m1["metadata"]["source_editions"][0]["universe_version"] == bridge.UNIVERSE
    assert m1["months"][-1]["segments"]["total"]["carriers"]["AEROMEXICO"]["share"] == 404 / 822


def test_exact_retry_is_byte_identical(native, before, source):
    gold = native[native.period_id.eq("2026M08")]
    first = bridge.project(native, gold, "2026M08", before, source)
    after = bridge.public_outputs(before, first)
    second = bridge.project(native, gold, "2026M08", after, source)
    assert bridge.public_outputs(after, second) == after


def test_boundary_revision_needs_separate_review(native, before, source):
    native.loc[native.period_id.eq("2026M06") & native.carrier_key.eq("AEROMEXICO"), "value"] += 1
    with pytest.raises(ValueError, match="boundary"):
        bridge.project(native, native[native.period_id.eq("2026M08")], "2026M08", before, source)


def test_missing_july_does_not_skip_to_august(native, before, source):
    native = native[~native.period_id.eq("2026M07")]
    with pytest.raises(ValueError, match="No reported"):
        bridge.project(native, native[native.period_id.eq("2026M08")], "2026M08", before, source)


def test_gold_support_mismatch_is_rejected(native):
    gold = native[native.period_id.eq("2026M08")].copy()
    gold.iloc[0, gold.columns.get_loc("value")] += 1
    with pytest.raises(ValueError, match="Gold month"):
        bridge._check_current_gold(native, gold, "2026M08")
