from __future__ import annotations

import pandas as pd

from src.transform.stage9_quality import build_canonical_quality_issues


def test_quality_ledgers_are_reconciled_and_deduplicated() -> None:
    operational = [
        {
            "issue_id": "same",
            "issue_type": "parse_failure",
            "severity": "warning",
            "layer": "silver",
            "table_name": "afac_monthly_stats",
            "source_file": "afac/example.xlsx",
            "description": "Parser failed",
            "affected_rows": 1,
            "resolved": False,
            "detected_at": "2026-01-01T00:00:00Z",
        },
        {
            "issue_id": "same",
            "issue_type": "parse_failure",
            "severity": "warning",
            "layer": "silver",
            "table_name": "afac_monthly_stats",
            "source_file": "afac/example.xlsx",
            "description": "Parser failed",
            "affected_rows": 1,
            "resolved": True,
            "resolved_at": "2026-01-03T00:00:00Z",
            "detected_at": "2026-01-02T00:00:00Z",
        },
    ]
    derived = pd.DataFrame(
        [
            {
                "issue_id": "derived",
                "issue_type": "reported_derived_discrepancy",
                "severity": "warning",
                "source_system": "derived_gold",
                "carrier_key": "AEROMEXICO",
                "period_id": "2026Q1",
                "metric_key": "load_factor_total",
                "observed_value": 0.843,
                "expected_value": 0.844,
                "difference_pct": 0.0012,
                "detail": "Reported value prevails",
                "source_file": "fact_carrier_metrics inputs",
                "detected_at": "2026-01-04T00:00:00Z",
            }
        ]
    )

    frame, evidence = build_canonical_quality_issues(derived, operational_records=operational)

    assert len(frame) == 2
    assert evidence == {
        "operational_baseline_rows": 0,
        "operational_run_rows": 2,
        "operational_raw_input_rows": 2,
        "operational_input_rows": 1,
        "operational_duplicate_rows": 1,
        "derived_input_rows": 1,
        "combined_raw_input_rows": 3,
        "combined_input_rows": 2,
        "canonical_rows": 2,
        "deduplicated_rows": 1,
    }
    assert frame["issue_signature"].is_unique
    resolved = frame.loc[frame["issue_origin"].eq("operational_ledger")].iloc[0]
    assert resolved["issue_id"].startswith("dqi_")
    assert resolved["status"] == "resolved"
    assert bool(resolved["resolved"])
    assert resolved["source_system"] == "afac"
    derived_row = frame.loc[frame["issue_origin"].eq("derived_reconciliation")].iloc[0]
    assert derived_row["issue_id"].startswith("dqi_")
    assert derived_row["calendar_period_id"] == "2026Q1"
