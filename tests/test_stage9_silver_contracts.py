from __future__ import annotations

import pandas as pd
import pytest

from src.transform.silver_contracts import load_silver_contracts, validate_all_silver, validate_silver_table
from src.config import PATHS


@pytest.mark.local_data
def test_every_physical_silver_dataset_is_declared() -> None:
    assert len(validate_all_silver()) == 30


def test_every_silver_contract_declares_grain_and_lineage_type() -> None:
    definitions = load_silver_contracts()["tables"]
    assert all(definition["grain"] for definition in definitions.values())
    assert all(definition["lineage_type"] for definition in definitions.values())


@pytest.mark.local_data
def test_bts_grain_distinguishes_carrier_entities_and_aircraft_configurations() -> None:
    definition = load_silver_contracts()["tables"]["bts_t100_segment"]
    assert "allow_duplicate_grain" not in definition
    assert {"unique_carrier_entity", "aircraft_config"} <= set(definition["grain"])
    frame = pd.read_parquet(PATHS.silver / "bts_t100_segment.parquet")
    assert not frame.duplicated(definition["grain"]).any()


def test_duplicate_declared_grain_is_rejected() -> None:
    row = {
        "date": pd.Timestamp("2026-01-01"),
        "currency_pair": "MXN_USD",
        "rate_close": 0.05,
        "source_system": "banxico",
        "source_file": "a.csv",
        "source_hash": "a" * 64,
        "ingested_at": pd.Timestamp("2026-01-02"),
        "parser_version": "1",
    }
    with pytest.raises(ValueError, match="Duplicate Silver grain"):
        validate_silver_table("fx_rates", pd.DataFrame([row, row]))


def test_candidate_schema_does_not_require_a_new_global_dataset():
    """Separating a candidate preserves both complete, strict contracts."""
    import subprocess
    import yaml

    def committed(commit):
        return yaml.safe_load(
            subprocess.check_output(
                ["git", "show", f"{commit}:config/silver_schema_contracts.yaml"], cwd=PATHS.root
            )
        )["tables"]

    global_tables = load_silver_contracts()["tables"]
    assert global_tables == committed("dad0a39b37fbdfe4367396ee4a9b640f3ce857e8")
    candidate = load_silver_contracts(PATHS.root / "config/source_update_candidate_silver.yaml")["tables"]
    assert candidate == {
        "airport_group_native": committed("98b71fb58ff42930f4a18d5411724aa662a5aba0")["airport_group_native"]
    }
    assert "airport_group_native" not in global_tables


@pytest.mark.parametrize("damage", ["column", "grain", "duplicate"])
def test_isolated_candidate_keeps_all_required_columns_and_grain_checks(damage):
    definition = load_silver_contracts(PATHS.root / "config/source_update_candidate_silver.yaml")["tables"][
        "airport_group_native"
    ]
    frame = pd.DataFrame([{name: "fixture" for name in definition["required_columns"]}])
    if damage == "duplicate":
        frame = pd.concat([frame, frame], ignore_index=True)
    else:
        frame = frame.drop(columns=["source_hash" if damage == "column" else "operator_group"])
    with pytest.raises(ValueError, match="missing columns|Duplicate Silver grain"):
        validate_silver_table("airport_group_native", frame)
