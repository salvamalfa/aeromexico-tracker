from datetime import date

import pandas as pd
import pytest

from src.config import ProjectPaths
from src.transform import stage6_dimensions as dimensions
from src.transform import stage6_macro as facts
from src.transform.stage6_contracts import add_record_id, validate_table
from src.transform.stage6_periods import observation_bounds


def write_silver(tmp_path, name, values):
    silver = tmp_path / "data/silver"
    silver.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(values).to_parquet(silver / f"{name}.parquet", index=False)
    return silver


def test_new_month_and_year_boundary_have_period_foreign_keys(tmp_path, monkeypatch):
    write_silver(
        tmp_path, "macro_indicators", {"date": pd.to_datetime(["2026-08-31", "2026-09-30", "2027-01-31"])}
    )
    monkeypatch.setattr(dimensions, "PATHS", ProjectPaths(root=tmp_path))
    frame = validate_table("dim_period", dimensions.build_dim_period())
    ids = set(frame.period_id)
    assert {"2026M09", "2026M12", "2027M01", "2026Q3", "2026Q4", "2027Q1", "2026", "2027"} <= ids
    january = frame.set_index("period_id").loc["2027M01"]
    assert january.prior_period_id == "2026M12"
    assert pd.isna(january.prior_year_period_id)
    for column in ["prior_period_id", "prior_year_period_id"]:
        assert set(frame[column].dropna()) <= ids


def test_fiscal_and_capture_metadata_do_not_extend_calendar(tmp_path):
    silver = write_silver(
        tmp_path,
        "observations",
        {
            "date": pd.to_datetime(["2026-09-30"]),
            "fiscal_period_id": ["FY2030Q2"],
            "fiscal_year": [2030],
            "ingested_at": pd.to_datetime(["2031-01-01"]),
        },
    )
    assert observation_bounds(silver) == (date(2026, 9, 30), date(2026, 9, 30))


def test_quarters_years_and_bts_months_are_observation_periods(tmp_path):
    silver = write_silver(tmp_path, "financials", {"period_id": ["2025", "2027Q2", "2026Q2TTM"]})
    write_silver(tmp_path, "bts_t100_segment", {"year": [2024, 2028], "month": [12, 2]})
    assert observation_bounds(silver) == (date(2024, 12, 1), date(2028, 2, 1))


def test_empty_or_only_fiscal_inputs_do_not_guess_a_horizon(tmp_path):
    silver = write_silver(
        tmp_path, "metadata", {"fiscal_period_id": ["FY2027Q1"], "ingested_at": ["2026-10-19"]}
    )
    with pytest.raises(ValueError, match="No observed calendar periods"):
        observation_bounds(silver)


def test_invalid_calendar_month_fails_instead_of_guessing(tmp_path):
    silver = write_silver(tmp_path, "observations", {"period_id": ["2026M13"]})
    with pytest.raises(ValueError):
        observation_bounds(silver)


def test_policy_rate_gold_is_percent_without_rescaling_and_new_periods_join(tmp_path, monkeypatch):
    stamps = pd.to_datetime(["2027-09-01", "2027-09-30"])
    macro = pd.DataFrame(
        {
            "date": stamps,
            "indicator_key": ["policy_rate"] * 2,
            "value": [7.75, 7.5],
            "source_system": ["banxico_sie"] * 2,
            "source_file": ["banxico.csv"] * 2,
            "source_hash": ["a" * 64] * 2,
            "ingested_at": pd.to_datetime(["2027-10-15"] * 2),
        }
    )
    write_silver(tmp_path, "macro_indicators", macro)
    write_silver(
        tmp_path,
        "fuel_prices",
        {
            "date": stamps,
            "price_usd_per_gallon": [2.2, 2.4],
            "source_system": ["eia"] * 2,
            "source_file": ["fuel.xls"] * 2,
            "source_hash": ["b" * 64] * 2,
            "ingested_at": pd.to_datetime(["2027-10-15"] * 2),
        },
    )
    paths = ProjectPaths(root=tmp_path)
    monkeypatch.setattr(facts, "PATHS", paths)
    monkeypatch.setattr(dimensions, "PATHS", paths)
    gold = validate_table("fact_macro", add_record_id("fact_macro", facts.build_fact_macro()))
    policy = gold[gold.indicator_key.eq("policy_rate")]
    assert set(policy.unit) == {"percent"}
    assert policy[policy.aggregation.eq("average")].value.eq(7.625).all()
    assert policy[policy.aggregation.eq("close")].value.eq(7.5).all()
    assert set(gold[gold.indicator_key.eq("jet_fuel_usd_per_gallon")].unit) == {"usd_per_gallon"}
    assert set(gold.period_id) <= set(dimensions.build_dim_period().period_id)
