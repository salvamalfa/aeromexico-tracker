from __future__ import annotations

import pandas as pd
import pytest

from src.transform.silver_contracts import load_silver_contracts, validate_all_silver, validate_silver_table
from src.config import PATHS


def test_every_physical_silver_dataset_is_declared() -> None:
    assert len(validate_all_silver()) == 28


def test_every_silver_contract_declares_grain_and_lineage_type() -> None:
    definitions = load_silver_contracts()["tables"]
    assert all(definition["grain"] for definition in definitions.values())
    assert all(definition["lineage_type"] for definition in definitions.values())


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
