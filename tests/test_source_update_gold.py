import hashlib
from datetime import UTC, datetime
import shutil
from uuid import uuid4

import pandas as pd
import pytest

from src.common.storage import save_bronze
from src.source_updates.catalog import ROOT
from src.source_updates.checks import check_candidate
from src.source_updates.gold import validate_macro_units
from src.transform.stage6_contracts import add_record_id, validate_table
from src.transform.stage9 import build_record_lineage_specs
from src.transform.stage9_lineage import LineageSpec, build_bridge_record_lineage, build_dim_source_artifact


@pytest.fixture
def candidate():
    workspace = ROOT / "tmp/source-updates" / ("gold-test-" + uuid4().hex)
    bronze = workspace / "data/bronze"
    path = save_bronze(
        b"preserved public fixture",
        "eia",
        "jet_fuel",
        "2026M09",
        "csv",
        "https://www.eia.gov/test.csv",
        "manual",
        bronze_root=bronze,
        content_type="text/csv",
        http_status=200,
        downloaded_at=datetime(2026, 10, 1, tzinfo=UTC),
    )
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    frame = pd.DataFrame(
        [
            {
                "period_id": period,
                "period_type": kind,
                "calendar_period_id": period,
                "fiscal_period_id": period,
                "indicator_key": "jet_fuel_usd_per_gallon",
                "value": 2.5,
                "unit": "usd_per_gallon",
                "aggregation": "average",
                "source_system": "eia",
                "source_file": "silver/fuel_prices.parquet",
                "source_hash": hashlib.sha256(digest.encode()).hexdigest(),
                "ingested_at": pd.Timestamp("2026-10-01"),
            }
            for period, kind in [("2026M09", "month"), ("2026Q3", "quarter")]
        ]
    )
    frame = validate_table("fact_macro", add_record_id("fact_macro", frame))
    gold = workspace / "data/gold"
    gold.mkdir(parents=True)
    frame.to_parquet(gold / "fact_macro.parquet", index=False)
    artifacts = validate_table(
        "dim_source_artifact", build_dim_source_artifact(bronze / "_manifest.jsonl", verify_files=True)
    )
    artifacts.to_parquet(gold / "dim_source_artifact.parquet", index=False)
    bridge = validate_table(
        "bridge_record_lineage",
        build_bridge_record_lineage(
            build_record_lineage_specs(
                {"fact_macro": frame}, artifacts, silver_dir=workspace / "data/silver"
            ),
            artifacts,
        ),
    )
    bridge.to_parquet(gold / "bridge_record_lineage.parquet", index=False)
    yield workspace
    shutil.rmtree(workspace)


def specification():
    return {
        "as_of": "2026-10-19T12:00:00-06:00",
        "checks": [
            {
                "product": "fuel",
                "layer": "gold",
                "table": "fact_macro",
                "expected_period": "2026M09",
                "filters": {"indicator_key": "jet_fuel_usd_per_gallon"},
                "value_columns": ["value"],
            }
        ],
    }


def test_inherited_gold_uses_verified_bridge_and_actual_capture_time(candidate):
    result = check_candidate(candidate, specification())
    assert result["status"] == "checks_passed"
    check = result["checks"][0]
    assert check["latest_parsed_period"] == "2026M09"
    assert check["capture_age_days"] == 19
    assert check["latest_published_period"] is None


@pytest.mark.parametrize(
    "target", ["catalog_hash", "bridge_hash", "declaration", "missing_bridge", "raw_bytes"]
)
def test_gold_cannot_borrow_or_fabricate_documentary_lineage(candidate, target):
    gold = candidate / "data/gold"
    if target == "catalog_hash":
        path = gold / "dim_source_artifact.parquet"
        frame = pd.read_parquet(path)
        frame["artifact_sha256"] = "f" * 64
        frame.to_parquet(path, index=False)
    elif target == "bridge_hash":
        path = gold / "bridge_record_lineage.parquet"
        frame = pd.read_parquet(path)
        frame["artifact_sha256"] = "f" * 64
        frame.to_parquet(path, index=False)
    elif target == "declaration":
        frame = pd.read_parquet(gold / "fact_macro.parquet")
        artifacts = pd.read_parquet(gold / "dim_source_artifact.parquet")
        specs = [
            LineageSpec(
                record_id=r,
                table_name="fact_macro",
                lineage_type="derived",
                lineage_note="No documentary ancestry",
            )
            for r in frame.record_id
        ]
        bridge = build_bridge_record_lineage(specs, artifacts)
        bridge.to_parquet(gold / "bridge_record_lineage.parquet", index=False)
    elif target == "missing_bridge":
        (gold / "bridge_record_lineage.parquet").unlink()
    else:
        next((candidate / "data/bronze").rglob("*.csv")).write_bytes(b"altered")
    if target == "raw_bytes":
        with pytest.raises(ValueError, match="SHA-256 mismatch"):
            check_candidate(candidate, specification())
    else:
        assert check_candidate(candidate, specification())["status"] == "blocked"


def test_gold_unit_gate_rejects_index_for_policy_rate():
    with pytest.raises(ValueError, match="policy_rate requires unit=percent"):
        validate_macro_units(pd.DataFrame({"indicator_key": ["policy_rate"], "unit": ["index"]}))
