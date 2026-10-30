from __future__ import annotations

import copy
import hashlib
import json

import pandas as pd
import pytest

from src.publish import airport_demand_projection as bridge


def row(key="MEX", period="2026M09", passengers=120, source_hash="a" * 64):
    return dict(
        key=key,
        group="GOVERNMENT",
        period_id=period,
        passengers=passengers,
        previous_period="2025M09",
        previous_passengers=100,
        yoy_pct=20.0,
        source_system="aicm",
        source_hash=source_hash,
        source_url="https://www.aicm.com.mx/report.pdf",
        captured_at="2026-10-28T15:00:00Z",
    )


def baseline():
    return {
        "schema_version": "market_demand_v1",
        "universe": "All carriers, airport universe",
        "months": ["2025M09", "2026M09"],
        "airports": [row(period="2025M09", passengers=999), row(passengers=1), row(key="NLU")],
        "groups": [],
        "quality_notes": ["Preserve unrelated OMA quarantine"],
        "quarantined_group_months": ["OMA:2025M09"],
    }


def projection():
    return {
        "product": "aicm_traffic",
        "period": "2026M09",
        "airports": [row()],
        "groups": [],
        "quality_note": bridge.SCOPES["aicm_traffic"][2],
    }


def before(value=None):
    return {bridge.TARGETS[0]: json.dumps(value or baseline()).encode()}


def test_selective_update_preserves_unrelated_airport_and_historical_comparative():
    old = baseline()
    after = json.loads(bridge.public_outputs(before(old), projection())[bridge.TARGETS[0]])
    assert after["airports"][0] == old["airports"][0]
    assert next(r for r in after["airports"] if r["key"] == "NLU") == old["airports"][2]
    current = next(r for r in after["airports"] if (r["key"], r["period_id"]) == ("MEX", "2026M09"))
    assert current["previous_passengers"] == 100  # This edition's comparison, not baseline 999.
    assert current["passengers"] == 120
    assert after["quarantined_group_months"] == old["quarantined_group_months"]
    assert after["quality_notes"][0] == old["quality_notes"][0]


def test_equivalent_repeated_projection_is_byte_idempotent_and_does_not_mutate_inputs():
    initial = before()
    data = projection()
    retained = copy.deepcopy(data)
    first = bridge.public_outputs(initial, data)
    assert first == bridge.public_outputs(first, data)
    assert data == retained
    assert initial == before()


@pytest.mark.parametrize(
    "alter",
    [
        lambda p: p.update(product="oma_traffic"),
        lambda p: p.update(period="2026Q3"),
        lambda p: p.update(quality_note="All airlines flown passengers"),
        lambda p: p["airports"][0].update(key="CUN"),
        lambda p: p["airports"][0].update(group="ASUR"),
        lambda p: p["airports"][0].update(period_id="2025M09"),
        lambda p: p["airports"].append(row()),
        lambda p: p["groups"].append(row()),
    ],
)
def test_rejects_broader_or_mislabelled_projection(alter):
    data = projection()
    alter(data)
    with pytest.raises(ValueError):
        bridge.public_outputs(before(), data)


def test_rejects_unrelated_output_or_duplicate_baseline_grain():
    with pytest.raises(ValueError):
        bridge.public_outputs({"data/v1/executive.json": b"{}"}, projection())
    duplicate = baseline()
    duplicate["airports"].append(duplicate["airports"][0])
    with pytest.raises(ValueError, match="Duplicate"):
        bridge.public_outputs(before(duplicate), projection())


def facts(tmp_path):
    gold = tmp_path / "data/gold"
    gold.mkdir(parents=True)
    airport = pd.DataFrame(
        [
            dict(
                airport_iata="MEX",
                operator_group="GOVERNMENT",
                period_id=p,
                country="MX",
                passengers_total=n,
                source_system="aicm",
                source_hash="a" * 64,
                ingested_at="2026-10-28T15:00:00Z",
            )
            for p, n in [("2025M09", 100), ("2026M09", 120)]
        ]
    )
    airport.to_parquet(gold / "fact_airport_traffic.parquet")
    pd.DataFrame(
        [{"artifact_sha256": "a" * 64, "source_url": "https://www.aicm.com.mx/report.pdf"}]
    ).to_parquet(gold / "dim_source_artifact.parquet")
    hashes = {"gold/" + p.stem: hashlib.sha256(p.read_bytes()).hexdigest() for p in gold.glob("*.parquet")}
    return {"product": "aicm_traffic", "period": "2026M09", "workspace": str(tmp_path)}, {
        "output_sha256": hashes
    }


def test_bridge_normalizes_iso_country_only_on_temporary_copy(tmp_path):
    item, checked = facts(tmp_path)
    before_bytes = {p: p.read_bytes() for p in tmp_path.rglob("*.parquet")}
    result = bridge.projection_rows(item, checked)
    assert len(result["airports"]) == 1
    assert result["airports"][0]["passengers"] == 120
    assert result["airports"][0]["yoy_pct"] == pytest.approx(20)
    assert result["groups"] == []
    assert result["airports"][0]["source_url"].startswith("https://")
    assert {p: p.read_bytes() for p in before_bytes} == before_bytes


def test_verified_fact_hash_is_rechecked(tmp_path):
    item, checked = facts(tmp_path)
    path = tmp_path / "data/gold/fact_airport_traffic.parquet"
    frame = pd.read_parquet(path)
    frame.loc[0, "passengers_total"] = 90
    frame.to_parquet(path)
    with pytest.raises(ValueError, match="changed"):
        bridge.projection_rows(item, checked)


@pytest.mark.parametrize("country,airport", [("Jamaica", "MEX"), ("MX", "CUN")])
def test_country_and_airport_scope_cannot_be_widened(tmp_path, country, airport):
    item, checked = facts(tmp_path)
    path = tmp_path / "data/gold/fact_airport_traffic.parquet"
    frame = pd.read_parquet(path).assign(country=country, airport_iata=airport)
    frame.to_parquet(path)
    checked["output_sha256"]["gold/fact_airport_traffic"] = hashlib.sha256(path.read_bytes()).hexdigest()
    with pytest.raises(ValueError):
        bridge.projection_rows(item, checked)


def test_missing_source_profile_or_unknown_product_fails_closed():
    with pytest.raises(ValueError):
        bridge.replay({}, None)
    with pytest.raises(ValueError):
        bridge.replay(
            {
                "schema_version": "airport_demand_source_v1",
                "item": {"product": "oma_traffic"},
                "as_of": "2026-10-28T12:00:00Z",
            },
            None,
        )
