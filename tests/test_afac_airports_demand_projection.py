from __future__ import annotations

import copy
import hashlib
import json

import pandas as pd
import pytest

from src.publish import afac_airports_demand_projection as module


def baseline():
    return {
        "schema_version": "market_demand_v1",
        "universe": "Existing airports, all carriers",
        "months": ["2025M09", "2026M09"],
        "airports": [
            {
                "key": "MEX",
                "group": "GOVERNMENT",
                "period_id": "2026M09",
                "passengers": 101,
                "previous_period": "2025M09",
                "previous_passengers": 99,
                "yoy_pct": 2.020202,
                "source_system": "aicm",
                "source_hash": "a" * 64,
                "source_url": "https://www.aicm.com.mx/report.pdf",
                "captured_at": "2026-10-28T10:00:00Z",
            }
        ],
        "groups": [],
        "quality_notes": ["Existing source note"],
        "quarantined_group_months": ["OMA:2025M09"],
    }


def facts(tmp_path):
    gold = tmp_path / "data/gold"
    gold.mkdir(parents=True)
    rows = [
        dict(
            period_id="2026M09",
            period_type="month",
            metric_key="passengers",
            market=market,
            value=value,
            airport_name_as_reported=name,
            airport_group_as_reported=group,
            service_scope="as_reported_airport_group_statistics",
            source_system="afac",
            source_hash="b" * 64,
            ingested_at="2026-10-28T23:49:53Z",
        )
        for name, group in [("CIUDAD DE MÉXICO/MEXICO CITY", "AICM"), ("CANCUN", "ASUR")]
        for market, value in [("domestic", 70), ("international", 30)]
    ]
    pd.DataFrame(rows).to_parquet(gold / "fact_afac_airport_observations.parquet")
    pd.DataFrame(
        [{"artifact_sha256": "b" * 64, "source_url": "https://www.gob.mx/afac/report.xlsx"}]
    ).to_parquet(gold / "dim_source_artifact.parquet")
    checked = {
        "output_sha256": {
            "gold/" + p.stem: hashlib.sha256(p.read_bytes()).hexdigest() for p in gold.glob("*.parquet")
        }
    }
    reference = tmp_path / "afac-city.csv"
    reference.write_text("afac_city,airport_iata\nMEXICO,MEX\nCANCUN,CUN\n")
    return {"product": "afac_airports", "period": "2026M09", "workspace": str(tmp_path)}, checked, reference


def projection(tmp_path):
    item, checked, reference = facts(tmp_path)
    return module.project_rows(item, checked, baseline(), reference)


def test_only_existing_airports_are_admitted_and_sources_stay_distinct(tmp_path):
    before = baseline()
    value = projection(tmp_path)
    assert [row["key"] for row in value["airports"]] == ["MEX"]
    assert value["baseline_airport_keys"] == ["MEX"]
    assert value["unmapped_existing_airports"] == []
    raw = module.public_outputs({module.TARGETS[0]: json.dumps(before).encode()}, value)[module.TARGETS[0]]
    after = json.loads(raw)
    assert after["airports"] == before["airports"]  # AFAC 100 never replaces direct report 101.
    assert after["afac_airports"][0]["passengers"] == 100
    assert after["afac_airports"][0]["source_system"] == "afac"
    assert after["afac_airports"][0]["previous_passengers"] is None
    assert after["afac_airports"][0]["yoy_pct"] is None
    assert after["groups"] == before["groups"]
    assert after["quarantined_group_months"] == before["quarantined_group_months"]
    assert module.public_outputs({module.TARGETS[0]: raw}, value)[module.TARGETS[0]] == raw


@pytest.mark.parametrize(
    "change", ["new_airport", "historical_month", "fictitious_yoy", "other_source", "baseline_scope"]
)
def test_rejects_coverage_expansion_backfill_or_mixed_series(tmp_path, change):
    value = projection(tmp_path)
    if change == "new_airport":
        value["airports"][0]["key"] = "CUN"
    elif change == "historical_month":
        value["airports"][0]["period_id"] = "2025M09"
    elif change == "fictitious_yoy":
        value["airports"][0]["yoy_pct"] = 0
    elif change == "other_source":
        value["airports"][0]["source_system"] = "aicm"
    else:
        value["baseline_airport_keys"].append("CUN")
    with pytest.raises(ValueError):
        module.public_outputs({module.TARGETS[0]: json.dumps(baseline()).encode()}, value)


@pytest.mark.parametrize("change", ["one_market_missing", "scope", "negative", "duplicated_city"])
def test_native_grain_and_scope_are_required(tmp_path, change):
    item, checked, reference = facts(tmp_path)
    path = tmp_path / "data/gold/fact_afac_airport_observations.parquet"
    frame = pd.read_parquet(path)
    if change == "one_market_missing":
        frame = frame.drop(index=0)
    elif change == "scope":
        frame.loc[0, "service_scope"] = "commercial_only"
    elif change == "negative":
        frame.loc[0, "value"] = -1
    else:
        frame = pd.concat([frame, frame.iloc[[0]]], ignore_index=True)
    frame.to_parquet(path)
    checked["output_sha256"]["gold/fact_afac_airport_observations"] = hashlib.sha256(
        path.read_bytes()
    ).hexdigest()
    with pytest.raises(ValueError):
        module.project_rows(item, checked, baseline(), reference)


def test_ambiguous_crosswalk_is_not_replaced_by_fuzzy_matching(tmp_path):
    item, checked, reference = facts(tmp_path)
    reference.write_text("afac_city,airport_iata\nMEXICO,MEX\nMEXICO,NLU\n")
    with pytest.raises(ValueError, match="unambiguous"):
        module.project_rows(item, checked, baseline(), reference)


def test_missing_existing_mapping_is_explicit_and_not_zero(tmp_path):
    item, checked, reference = facts(tmp_path)
    before = baseline()
    missing = copy.deepcopy(before["airports"][0])
    missing["key"] = "AAA"
    before["airports"].append(missing)
    result = module.project_rows(item, checked, before, reference)
    assert result["unmapped_existing_airports"] == ["AAA"]
    assert all(row["key"] != "AAA" for row in result["airports"])
