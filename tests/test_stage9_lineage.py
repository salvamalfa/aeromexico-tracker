from __future__ import annotations

import hashlib
from pathlib import Path

import pandas as pd

from src.transform.stage9 import build_record_lineage_specs
from src.transform.stage6_contracts import validate_table
from src.transform.stage9_lineage import (
    add_record_ids,
    build_bridge_record_lineage,
)
from src.transform.validate_stage9 import run as validate_stage9
from src.transform.validate_stage9 import validate_lineage_frames


def _artifact(index: int, *, digest: str | None = None) -> dict[str, object]:
    value = digest or hashlib.sha256(f"artifact-{index}".encode()).hexdigest()
    return {
        "artifact_id": f"art_{hashlib.sha256(f'id-{index}'.encode()).hexdigest()}",
        "artifact_sha256": value,
        "source_file": f"sec/file-{index}.htm",
        "source_url": f"https://www.sec.gov/file-{index}.htm",
    }


def _identified(table_name: str, frame: pd.DataFrame, grain: list[str]) -> pd.DataFrame:
    return add_record_ids(
        frame, table_name=table_name, natural_key_columns=grain
    )


def test_materializer_distinguishes_direct_aggregate_parent_and_declaration(
    tmp_path: Path,
) -> None:
    artifacts = pd.DataFrame([_artifact(1)])
    digest = str(artifacts.iloc[0]["artifact_sha256"])
    singleton_aggregate = hashlib.sha256(digest.encode()).hexdigest()

    direct = _identified(
        "fact_direct",
        pd.DataFrame(
            [{"key": "direct", "source_hash": digest, "source_file": "sec/file-1.htm"}]
        ),
        ["key"],
    )
    aggregate = _identified(
        "fact_macro",
        pd.DataFrame(
            [{"key": "aggregate", "source_hash": singleton_aggregate, "source_file": "silver/macro.parquet"}]
        ),
        ["key"],
    )
    route = _identified(
        "fact_route_traffic",
        pd.DataFrame(
            [
                {
                    "carrier_key": "AEROMEXICO",
                    "route_key": "MEX-JFK",
                    "period_id": "2026M01",
                    "source_hash": singleton_aggregate,
                    "source_file": "silver/bts.parquet",
                }
            ]
        ),
        ["carrier_key", "route_key", "period_id"],
    )
    summary = _identified(
        "fact_route_traffic_summary",
        pd.DataFrame(
            [
                {
                    "carrier_key": "AEROMEXICO",
                    "market_key": "JFK<>MEX",
                    "period_id": "2026M01",
                }
            ]
        ),
        ["carrier_key", "market_key", "period_id"],
    )
    study = _identified(
        "fact_study_results",
        pd.DataFrame([{"study_key": "opaque-study"}]),
        ["study_key"],
    )
    tables = {
        "fact_direct": direct,
        "fact_macro": aggregate,
        "fact_route_traffic": route,
        "fact_route_traffic_summary": summary,
        "fact_study_results": study,
    }
    dim_route = pd.DataFrame(
        [{"route_key": "MEX-JFK", "market_key": "JFK<>MEX"}]
    )

    specs = build_record_lineage_specs(
        tables,
        artifacts,
        silver_dir=tmp_path,
        dim_route=dim_route,
    )
    bridge = build_bridge_record_lineage(specs, artifacts)
    assert len(validate_table("bridge_record_lineage", bridge)) == len(bridge)

    direct_row = bridge[bridge["table_name"].eq("fact_direct")].iloc[0]
    assert direct_row["lineage_type"] == "direct_artifact"
    aggregate_row = bridge[bridge["table_name"].eq("fact_macro")].iloc[0]
    assert aggregate_row["lineage_type"] == "derived"
    summary_row = bridge[
        bridge["table_name"].eq("fact_route_traffic_summary")
    ].iloc[0]
    assert summary_row["link_type"] == "parent_record"
    assert summary_row["parent_record_id"] == route.iloc[0]["record_id"]
    study_row = bridge[bridge["table_name"].eq("fact_study_results")].iloc[0]
    assert study_row["lineage_status"] == "declared_without_artifact"
    assert pd.notna(study_row["lineage_note"])

    contracts = {
        "tables": {
            name: {"grain": grain}
            for name, grain in {
                "fact_direct": ["key"],
                "fact_macro": ["key"],
                "fact_route_traffic": ["carrier_key", "route_key", "period_id"],
                "fact_route_traffic_summary": ["carrier_key", "market_key", "period_id"],
                "fact_study_results": ["study_key"],
            }.items()
        }
    }
    result = validate_lineage_frames(
        tables=tables,
        artifacts=artifacts,
        bridge=bridge,
        contracts=contracts,
    )
    assert result["coverage_pct"] == 1.0
    assert result["unknown_parent_records"] == 0


def test_scd2_record_keeps_all_sec_artifacts_that_attest_same_state(
    tmp_path: Path,
) -> None:
    artifacts = pd.DataFrame([_artifact(1), _artifact(2)])
    gold = _identified(
        "fact_carrier_metrics",
        pd.DataFrame(
            [
                {
                    "carrier_key": "AEROMEXICO",
                    "period_id": "2026Q1",
                    "metric_key": "total_revenue",
                    "segment": "total",
                    "source_system": "sec_edgar",
                    "source_hash": artifacts.iloc[0]["artifact_sha256"],
                    "source_file": artifacts.iloc[0]["source_file"],
                    "value": 100.0,
                    "unit_normalized": "usd",
                    "is_preliminary": False,
                    "is_derived": False,
                    "is_current": True,
                    "confidence": 1.0,
                    "ingested_at": pd.Timestamp("2026-01-01"),
                    "valid_from": pd.Timestamp("2026-01-01"),
                    "valid_to": pd.NaT,
                }
            ]
        ),
        ["carrier_key", "period_id", "metric_key", "segment", "source_system", "valid_from"],
    )
    silver = pd.DataFrame(
        [
            {
                "carrier_key": "AEROMEXICO",
                "period_id": "2026Q1",
                "metric_key": "total_revenue",
                "segment": "total",
                "value_normalized": 100.0,
                "unit_normalized": "usd",
                "is_preliminary": False,
                "source_system": "sec_edgar",
                "source_hash": row["artifact_sha256"],
                "ingested_at": pd.Timestamp(f"2026-0{index}-01", tz="UTC"),
            }
            for index, row in enumerate(artifacts.to_dict("records"), start=1)
        ]
    )
    silver.to_parquet(tmp_path / "sec_financials.parquet", index=False)

    specs = build_record_lineage_specs(
        {"fact_carrier_metrics": gold},
        artifacts,
        silver_dir=tmp_path,
    )
    bridge = build_bridge_record_lineage(specs, artifacts)
    links = bridge[bridge["link_type"].eq("artifact")]
    assert set(links["artifact_id"]) == set(artifacts["artifact_id"])
    assert links["lineage_fingerprint"].nunique() == 1
    assert not set(links["lineage_fingerprint"]) & set(links["artifact_sha256"])


def test_derived_carrier_metric_uses_metric_parents_not_template_artifact(
    tmp_path: Path,
) -> None:
    artifacts = pd.DataFrame([_artifact(1), _artifact(2)])
    common = {
        "carrier_key": "AEROMEXICO",
        "period_id": "2026Q1",
        "segment": "total",
        "is_preliminary": False,
        "is_current": True,
        "confidence": 1.0,
        "ingested_at": pd.Timestamp("2026-01-01"),
        "valid_from": pd.Timestamp("2026-01-01"),
        "valid_to": pd.NaT,
    }
    rows = [
        {
            **common,
            "metric_key": metric,
            "value": value,
            "unit_normalized": "count",
            "is_derived": False,
            "source_system": "sec_edgar",
            "source_hash": artifacts.iloc[index]["artifact_sha256"],
            "source_file": artifacts.iloc[index]["source_file"],
        }
        for index, (metric, value) in enumerate(
            [("rpm_total", 80.0), ("asm_total", 100.0)]
        )
    ]
    rows.append(
        {
            **common,
            "metric_key": "load_factor_derived",
            "value": 0.8,
            "unit_normalized": "fraction",
            "is_derived": True,
            "source_system": "derived_gold",
            # Deliberately looks like one source artifact.  It is only the
            # template hash and cannot replace the two formula inputs.
            "source_hash": artifacts.iloc[0]["artifact_sha256"],
            "source_file": "fact_carrier_metrics inputs",
        }
    )
    grain = [
        "carrier_key",
        "period_id",
        "metric_key",
        "segment",
        "source_system",
        "valid_from",
    ]
    gold = _identified("fact_carrier_metrics", pd.DataFrame(rows), grain)
    specs = build_record_lineage_specs(
        {"fact_carrier_metrics": gold}, artifacts, silver_dir=tmp_path
    )
    bridge = build_bridge_record_lineage(specs, artifacts)
    derived_id = gold.loc[
        gold["metric_key"].eq("load_factor_derived"), "record_id"
    ].iloc[0]
    links = bridge[bridge["record_id"].eq(derived_id)]
    expected_parents = set(
        gold.loc[gold["metric_key"].isin(["rpm_total", "asm_total"]), "record_id"]
    )
    assert set(links["parent_record_id"].dropna()) == expected_parents
    assert links["artifact_id"].isna().all()


def test_materialized_stage9_acceptance_gate_passes() -> None:
    result = validate_stage9()

    assert result["all_passed"]
    assert result["passed"] == result["total"] == 12
    assert result["lineage"]["coverage_pct"] == 1.0
