from __future__ import annotations

import pandas as pd

from src.transform.stage6_facts import _build_afac_aggregate_history


def _row(service: str, value: float, ingested_at: str, source_file: str) -> dict[str, object]:
    return {
        "carrier_key": "AEROMEXICO",
        "period_id": "2026M06",
        "market": "domestic",
        "service_type": service,
        "period_start_date": pd.Timestamp("2026-06-01"),
        "period_end_date": pd.Timestamp("2026-06-30"),
        "value": value,
        "is_preliminary": True,
        "is_estimated": False,
        "source_file": source_file,
        "source_hash": (source_file[0] * 64),
        "ingested_at": pd.Timestamp(ingested_at),
    }


def test_complementary_afac_inputs_create_one_baseline_then_real_revision() -> None:
    source = pd.DataFrame(
        [
            _row("charter", 10, "2026-07-10", "charter-v1.xlsx"),
            _row("scheduled", 100, "2026-07-11", "scheduled-v1.pdf"),
            _row("scheduled", 100, "2026-07-12", "scheduled-repeat.pdf"),
            _row("scheduled", 105, "2026-07-13", "scheduled-v2.pdf"),
        ]
    )

    history = _build_afac_aggregate_history(
        source,
        ["carrier_key", "period_id", "market"],
    )

    assert history["value"].tolist() == [110.0, 115.0]
    assert history["restatement_count"].tolist() == [0, 1]
    assert history["is_current"].tolist() == [False, True]
    assert history.iloc[0]["valid_from"] == pd.Timestamp("2026-07-11")
    assert history.iloc[1]["valid_from"] == pd.Timestamp("2026-07-13")


def test_current_afac_anchor_keeps_scheduled_plus_charter() -> None:
    source = pd.DataFrame(
        [
            _row("charter", 713, "2026-08-20 22:42:11", "charter.xlsx"),
            _row("scheduled", 832_733, "2026-08-20 22:53:57", "scheduled.pdf"),
        ]
    )
    history = _build_afac_aggregate_history(
        source,
        ["carrier_key", "period_id", "market"],
    )
    assert len(history) == 1
    assert history.iloc[0]["value"] == 833_446
    assert history.iloc[0]["restatement_count"] == 0
