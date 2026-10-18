from pathlib import Path

import pandas as pd
import pytest

from src.dashboard.market_demand import build_market_demand


def write(gold: Path, duplicate=False):
    airports = [
        dict(
            airport_iata="MEX",
            operator_group="GOVERNMENT",
            period_id=p,
            passengers_total=v,
            country="Mexico",
            source_system="aicm",
            source_hash="a" * 64,
            ingested_at="2026-08-01",
        )
        for p, v in [("2025M06", 100), ("2026M06", 110)]
    ]
    airports += [
        dict(airports[0], airport_iata="MTY", operator_group="OMA", passengers_total=20),
        dict(airports[0], airport_iata="MBJ", country="Jamaica", passengers_total=300),
    ]
    if duplicate:
        airports.append(airports[0])
    pd.DataFrame(airports).to_parquet(gold / "fact_airport_traffic.parquet")
    pd.DataFrame(
        [
            dict(
                airport_group_key="OMA",
                period_id="2025M06",
                passengers_total=200,
                passengers_international=20,
                country="Mexico",
                source_system="oma_ir",
                source_hash="b" * 64,
                ingested_at="2026-08-01",
            )
        ]
    ).to_parquet(gold / "fact_airport_group_traffic.parquet")


def test_demand_keeps_universes_separate_and_quarantines_mislabelled_subtotal(tmp_path):
    write(tmp_path)
    result = build_market_demand(tmp_path)
    assert {r["key"] for r in result["airports"]} == {"MEX"}
    june = result["airports"][-1]
    assert june["yoy_pct"] == pytest.approx(10)
    assert result["airports"][0]["yoy_pct"] is None
    assert result["groups"][0]["passengers"] == 200
    assert result["quarantined_group_months"] == ["OMA:2025M06"]
    assert len(pd.read_parquet(tmp_path / "fact_airport_traffic.parquet")) == 4


def test_demand_rejects_duplicate_grain(tmp_path):
    write(tmp_path, True)
    with pytest.raises(ValueError, match="Duplicate"):
        build_market_demand(tmp_path)
