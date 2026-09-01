from __future__ import annotations

import pandas as pd
import pytest

from src.transform.scd2 import SCD2ValidationError, build_scd2_history
from src.transform.stage6_contracts import validate_table_invariants
from src.transform.stage6_facts import _bmv_rows


LOGICAL_KEY = ["carrier_key", "period_id", "metric_key", "segment"]


def test_afac_frozen_revision_collapses_unchanged_observation() -> None:
    observations = pd.DataFrame(
        [
            {
                "carrier_key": "AEROMEXICO",
                "period_id": "2025-06",
                "metric_key": "passengers_afac",
                "segment": "total",
                "value": 2_100_000,
                "ingested_at": "2025-07-10T12:00:00-06:00",
                "source_file": "afac/2025-06-v1.xlsx",
                "source_hash": "a" * 64,
            },
            {
                "carrier_key": "AEROMEXICO",
                "period_id": "2025-06",
                "metric_key": "passengers_afac",
                "segment": "total",
                "value": 2_100_000,
                "ingested_at": "2025-07-12T18:00:00Z",
                "source_file": "afac/2025-06-v1-redownload.xlsx",
                "source_hash": "b" * 64,
            },
            {
                "carrier_key": "AEROMEXICO",
                "period_id": "2025-06",
                "metric_key": "passengers_afac",
                "segment": "total",
                "value": 2_050_000,
                "ingested_at": "2025-08-01T00:00:00Z",
                "source_file": "afac/2025-06-revised.xlsx",
                "source_hash": "c" * 64,
            },
        ]
    )

    result = build_scd2_history(observations, key_columns=LOGICAL_KEY)

    assert result["value"].tolist() == [2_100_000, 2_050_000]
    assert result["restatement_count"].tolist() == [0, 1]
    assert result["is_current"].tolist() == [False, True]
    assert result.loc[0, "valid_from"] == pd.Timestamp("2025-07-10 18:00:00")
    assert result.loc[0, "valid_to"] == pd.Timestamp("2025-07-31 23:59:59.999999")
    assert result.loc[1, "valid_from"] == pd.Timestamp("2025-08-01 00:00:00")
    assert pd.isna(result.loc[1, "valid_to"])
    assert result["source_file"].tolist() == [
        "afac/2025-06-v1.xlsx",
        "afac/2025-06-revised.xlsx",
    ]


def test_sec_frozen_revision_preserves_real_change_and_extra_columns() -> None:
    observations = pd.DataFrame(
        [
            {
                "carrier_key": "AEROMEXICO",
                "period_id": "2025Q2",
                "metric_key": "total_revenue",
                "segment": "total",
                "value": 1_250_000_000.0,
                "ingested_at": "2025-07-24T13:00:00Z",
                "accession_number": "0001561861-25-000010",
                "currency": "USD",
            },
            {
                "carrier_key": "AEROMEXICO",
                "period_id": "2025Q2",
                "metric_key": "total_revenue",
                "segment": "total",
                "value": 1_255_000_000.0,
                "ingested_at": "2025-08-05T09:30:00Z",
                "accession_number": "0001561861-25-000011",
                "currency": "USD",
            },
        ]
    )

    result = build_scd2_history(observations, key_columns=LOGICAL_KEY)

    assert result["value"].tolist() == [1_250_000_000.0, 1_255_000_000.0]
    assert result["accession_number"].tolist() == [
        "0001561861-25-000010",
        "0001561861-25-000011",
    ]
    assert result["currency"].tolist() == ["USD", "USD"]
    assert result["restatement_count"].tolist() == [0, 1]


def test_null_values_are_compared_explicitly() -> None:
    observations = pd.DataFrame(
        {
            "carrier_key": ["AEROMEXICO"] * 5,
            "period_id": ["2025Q3"] * 5,
            "metric_key": ["operating_margin"] * 5,
            "segment": ["total"] * 5,
            "value": [None, float("nan"), 0.143, 0.143, None],
            "ingested_at": pd.date_range("2025-10-01", periods=5, tz="UTC"),
            "note": ["not reported", "still absent", "published", "redownload", "withdrawn"],
        }
    )

    result = build_scd2_history(observations, key_columns=LOGICAL_KEY)

    assert len(result) == 3
    assert pd.isna(result.loc[0, "value"])
    assert result.loc[1, "value"] == pytest.approx(0.143)
    assert pd.isna(result.loc[2, "value"])
    assert result["restatement_count"].tolist() == [0, 1, 2]
    assert result["note"].tolist() == ["not reported", "published", "withdrawn"]


def test_identical_duplicate_does_not_create_a_version() -> None:
    observation = {
        "carrier_key": "AEROMEXICO",
        "period_id": "2025-06",
        "metric_key": "passengers_afac",
        "segment": "total",
        "value": 2_050_000,
        "ingested_at": "2025-08-01T00:00:00Z",
        "source_hash": "c" * 64,
    }

    result = build_scd2_history(pd.DataFrame([observation, observation]), key_columns=LOGICAL_KEY)

    assert len(result) == 1
    assert result.loc[0, "restatement_count"] == 0
    assert bool(result.loc[0, "is_current"])


def test_output_is_deterministic_for_unsorted_input() -> None:
    observations = pd.DataFrame(
        {
            "carrier_key": ["AEROMEXICO"] * 3,
            "period_id": ["2026-01"] * 3,
            "metric_key": ["passengers_afac"] * 3,
            "segment": ["total"] * 3,
            "value": [10, 11, 10],
            "ingested_at": [
                "2026-01-03T00:00:00Z",
                "2026-01-02T00:00:00Z",
                "2026-01-01T00:00:00Z",
            ],
        }
    )

    result = build_scd2_history(observations, key_columns=LOGICAL_KEY)

    assert result["value"].tolist() == [10, 11, 10]
    assert result["restatement_count"].tolist() == [0, 1, 2]


def test_real_bmv_history_uses_one_effective_time_per_artifact_and_valid_intervals() -> None:
    history = _bmv_rows()
    keys = ["carrier_key", "period_id", "metric_key", "segment", "source_system"]

    assert not history.empty
    assert history.groupby("source_file")["valid_from"].nunique().le(1).all()
    assert history.loc[history["valid_to"].notna(), "valid_to"].ge(
        history.loc[history["valid_to"].notna(), "valid_from"]
    ).all()
    for _, group in history.groupby(keys, dropna=False):
        ordered = group.sort_values("valid_from")
        assert ordered["restatement_count"].tolist() == list(range(len(ordered)))
        assert int(ordered["is_current"].sum()) == 1
        assert bool(ordered.iloc[-1]["is_current"])
        assert ordered["value"].astype("string").ne(
            ordered["value"].shift().astype("string")
        ).iloc[1:].all()

    current = history[history["is_current"]]
    volaris_2021 = current[
        current["carrier_key"].eq("VOLARIS")
        & current["period_id"].astype(str).str.startswith("2021")
        & current["metric_key"].eq("net_income")
    ]
    annual = float(volaris_2021.loc[volaris_2021["period_id"].eq("2021"), "value"].iloc[0])
    quarters = float(
        volaris_2021.loc[volaris_2021["period_type"].eq("quarter"), "value"].sum()
    )
    assert quarters == pytest.approx(annual, abs=1.0)


@pytest.mark.parametrize("bad_timestamp", [None, "not-a-date"])
def test_invalid_timestamp_is_rejected(bad_timestamp: object) -> None:
    observations = pd.DataFrame(
        {
            "carrier_key": ["AEROMEXICO"],
            "period_id": ["2025Q2"],
            "metric_key": ["total_revenue"],
            "segment": ["total"],
            "value": [1.0],
            "ingested_at": [bad_timestamp],
        }
    )

    with pytest.raises(SCD2ValidationError, match="invalid timestamp"):
        build_scd2_history(observations, key_columns=LOGICAL_KEY)


@pytest.mark.parametrize("bad_key", [None, "", "   "])
def test_invalid_logical_key_is_rejected(bad_key: object) -> None:
    observations = pd.DataFrame(
        {
            "carrier_key": [bad_key],
            "period_id": ["2025-06"],
            "metric_key": ["passengers_afac"],
            "segment": ["total"],
            "value": [2_050_000],
            "ingested_at": ["2025-08-01T00:00:00Z"],
        }
    )

    with pytest.raises(SCD2ValidationError, match="invalid logical key"):
        build_scd2_history(observations, key_columns=LOGICAL_KEY)


def test_conflicting_values_at_same_timestamp_are_rejected() -> None:
    observations = pd.DataFrame(
        {
            "carrier_key": ["AEROMEXICO", "AEROMEXICO"],
            "period_id": ["2025Q2", "2025Q2"],
            "metric_key": ["total_revenue", "total_revenue"],
            "segment": ["total", "total"],
            "value": [1.0, 2.0],
            "ingested_at": ["2025-08-01T00:00:00Z", "2025-08-01T00:00:00Z"],
        }
    )

    with pytest.raises(SCD2ValidationError, match="conflicting values"):
        build_scd2_history(observations, key_columns=LOGICAL_KEY)


def test_declared_scd2_invariant_rejects_reversed_intervals() -> None:
    frame = pd.DataFrame(
        {
            "carrier_key": ["AEROMEXICO", "AEROMEXICO"],
            "period_id": ["2025Q1", "2025Q1"],
            "metric_key": ["total_revenue", "total_revenue"],
            "segment": ["total", "total"],
            "source_system": ["sec_edgar", "sec_edgar"],
            "value": [1.0, 2.0],
            "valid_from": pd.to_datetime(["2025-05-02", "2025-05-01"]),
            "valid_to": pd.to_datetime(["2025-05-01", None]),
            "is_current": [False, True],
            "restatement_count": [0, 1],
        }
    )
    definition = {
        "invariants": [
            {
                "name": "fixture_scd2",
                "kind": "scd2_history",
                "key_columns": [
                    "carrier_key",
                    "period_id",
                    "metric_key",
                    "segment",
                    "source_system",
                ],
                "value_columns": ["value"],
            }
        ]
    }

    with pytest.raises(ValueError, match="reversed validity intervals"):
        validate_table_invariants("fact_fixture", frame, definition)
