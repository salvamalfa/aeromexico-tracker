"""Native AFAC method history and isolated market-only export regressions."""

from copy import deepcopy

import pandas as pd
import pytest

from src.config import PATHS
from src.parse.afac.market_scope import TOTAL_FORMULA
from src.transform.afac_native_update import append_versions
from src.transform.stage6_contracts import validate_table


def old_fact():
    frame = pd.read_parquet(PATHS.gold / "fact_carrier_metrics.parquet")
    row = (
        frame[
            frame.metric_key.eq("passengers_afac")
            & frame.carrier_key.eq("MARKET_TOTAL_MX")
            & frame.is_current
        ]
        .iloc[[0]]
        .copy()
        .reset_index(drop=True)
    )
    return row


def test_native_scope_method_change_versions_without_rewriting_previous_fact():
    baseline = old_fact()
    incoming = baseline.drop(columns="record_id").copy()
    incoming["derivation_formula"] = TOTAL_FORMULA
    output, count = append_versions(baseline, incoming, "2026-11-05T04:00:00+00:00")
    assert count == 1
    assert output.value.tolist() == [baseline.iloc[0].value] * 2
    assert output.restatement_count.tolist() == [0, 1]
    retained = output.iloc[[0]][baseline.columns].copy()
    retained["valid_to"] = baseline.valid_to
    retained["is_current"] = baseline.is_current
    pd.testing.assert_frame_equal(retained, baseline)
    validate_table("fact_carrier_metrics", output)


def test_source_hash_capture_only_and_cosmetic_formula_do_not_add_history():
    baseline = old_fact()
    baseline["derivation_formula"] = TOTAL_FORMULA
    incoming = baseline.drop(columns="record_id").copy()
    incoming["derivation_formula"] = "  " + TOTAL_FORMULA + "\n"
    incoming["source_hash"] = "a" * 64
    incoming["ingested_at"] = pd.Timestamp("2026-11-04")
    output, count = append_versions(baseline, incoming, "2026-11-05T04:00:00+00:00")
    assert count == 0
    pd.testing.assert_frame_equal(output, baseline)


def test_source_reported_estimation_flag_is_a_material_version():
    baseline = old_fact()
    baseline["derivation_formula"] = TOTAL_FORMULA
    baseline["is_estimated"] = False
    incoming = baseline.drop(columns="record_id").copy()
    incoming["is_estimated"] = True
    output,count = append_versions(baseline,incoming,"2026-11-05T04:00:00+00:00")
    assert count == 1
    assert output["is_estimated"].tolist() == [False,True]
    validate_table("fact_carrier_metrics",output)


def test_unknown_formula_cannot_manufacture_restatement():
    baseline = old_fact()
    incoming = baseline.drop(columns="record_id").copy()
    incoming["derivation_formula"] = "New arbitrary label"
    with pytest.raises(ValueError, match="canonical formula"):
        append_versions(baseline, incoming, "2026-11-05T04:00:00+00:00")


def test_scd2_contract_still_rejects_equal_state_and_cosmetic_only_version():
    baseline = old_fact()
    baseline["derivation_formula"] = TOTAL_FORMULA
    incoming = baseline.drop(columns="record_id").copy()
    incoming["value"] += 1
    output, _ = append_versions(baseline, incoming, "2026-11-05T04:00:00+00:00")
    output.loc[1, "value"] = output.loc[0, "value"]
    output.loc[1, "derivation_formula"] = "  " + TOTAL_FORMULA + "\n"
    with pytest.raises(ValueError, match="without a value change"):
        validate_table("fact_carrier_metrics", output)


def test_financial_rows_and_outside_periods_remain_identical():
    source = pd.read_parquet(PATHS.gold / "fact_carrier_metrics.parquet")
    financial = source[~source.metric_key.eq("passengers_afac")].iloc[:10]
    baseline = pd.concat([old_fact(), financial], ignore_index=True)
    before = deepcopy(baseline)
    incoming = old_fact().drop(columns="record_id")
    incoming["derivation_formula"] = TOTAL_FORMULA
    output, _ = append_versions(baseline, incoming, "2026-11-05T04:00:00+00:00")
    pd.testing.assert_frame_equal(
        output.iloc[1:11].reset_index(drop=True), before.iloc[1:11].reset_index(drop=True)
    )


def test_out_of_order_correction_and_missing_native_selection_fail_closed(tmp_path, monkeypatch):
    baseline = old_fact()
    incoming = baseline.drop(columns="record_id").copy()
    incoming["derivation_formula"] = TOTAL_FORMULA
    with pytest.raises(ValueError, match="correction time"):
        append_versions(baseline, incoming, "2010-01-01T00:00:00+00:00")
    from src.config import ProjectPaths
    from src.parse.afac import annual_series

    monkeypatch.setattr(annual_series, "PATHS", ProjectPaths(root=tmp_path))
    with pytest.raises(FileNotFoundError, match="no legacy fallback"):
        annual_series.run()
