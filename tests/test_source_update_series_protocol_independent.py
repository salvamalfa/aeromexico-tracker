"""Independent synthetic replay contracts; these never certify live sources."""

import hashlib
import json
import shutil
from uuid import uuid4

import pandas as pd
import pytest

from src.source_updates import readiness, retained, series_candidate
from src.source_updates import series_gold as gold
from src.source_updates.catalog import ROOT
from tests.test_source_update_series_independent import (
    FUEL_SERIES,
    FUEL_URL,
    equities_inputs,
    fuel_bytes,
    macro_inputs,
    materialize,
    original,
)


@pytest.fixture
def candidate():
    path = ROOT / "tmp/source-updates" / ("pytest-independent-series-" + uuid4().hex)
    yield path
    if path.exists():
        shutil.rmtree(path)


def certified_candidate(product, candidate, source_root, period="2026Q3"):
    inputs = equities_inputs() if product == "equities" else macro_inputs(product)
    materialize(inputs, source_root)
    acquisition = retained.retain(
        candidate,
        source_root / "data/bronze",
        product,
        {role: row["source_file"] for role, (_, row) in inputs.items()},
        execute=True,
    )
    result = series_candidate.run(
        candidate,
        product,
        period,
        "2026-10-21T12:00:00-06:00",
        acquisition["run_id"],
        execute=True,
    )
    return acquisition["run_id"], result


@pytest.mark.parametrize("product", ["banxico", "fuel", "equities"])
def test_whole_product_protocol_and_readiness_replay_are_immutable(product, candidate, tmp_path):
    run_id, accepted = certified_candidate(product, candidate, tmp_path)
    before = {
        p.relative_to(candidate).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in candidate.rglob("*")
        if p.is_file()
    }
    checked = readiness.check_task(
        {
            "id": product,
            "product": product,
            "period": "2026Q3",
            "adapter": "series",
            "workspace": str(candidate),
            "receipt_id": run_id,
            "required": True,
            "candidate_as_of": accepted["effective_as_of"],
        },
        accepted["effective_as_of"],
    )
    assert checked["status"] == "checks_passed"
    assert checked["latest_source_availability_verified"] is False
    assert "retained_original_does_not_verify_current_source_availability" in checked["source_conditions"]
    assert checked["activation"] == "none" and checked["publication"] == "not_authorized"
    assert before == {
        p.relative_to(candidate).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in candidate.rglob("*")
        if p.is_file()
    }


def test_direct_series_replay_rejects_active_source_writer(candidate, tmp_path):
    run_id, accepted = certified_candidate("fuel", candidate, tmp_path)
    (candidate / ".source-update.lock").write_text("independent synthetic competing writer")
    with pytest.raises(ValueError, match="writer|lock"):
        series_candidate.run(candidate, "fuel", "2026Q3", accepted["effective_as_of"], run_id, check=True)


@pytest.mark.parametrize("changed", ["cutoff", "gold", "receipt", "code"])
def test_direct_series_replay_cannot_reinterpret_or_mutate_accepted_result(
    changed, candidate, tmp_path, monkeypatch
):
    run_id, accepted = certified_candidate("fuel", candidate, tmp_path)
    cutoff = accepted["effective_as_of"]
    receipt = candidate / "receipts/series-fuel-2026Q3.json"
    if changed == "cutoff":
        cutoff = "2026-10-22T12:00:00-06:00"
    elif changed == "gold":
        path = candidate / "data/gold/fact_macro.parquet"
        frame = pd.read_parquet(path)
        frame.loc[0, "value"] += 1
        frame.to_parquet(path, index=False)
    elif changed == "receipt":
        value = json.loads(receipt.read_text())
        value["latest_source_availability_verified"] = True
        receipt.write_text(json.dumps(value))
    else:
        original_fingerprints = series_candidate.fingerprints
        monkeypatch.setattr(
            series_candidate, "fingerprints", lambda: {**original_fingerprints(), "changed": "x"}
        )
    before = receipt.read_bytes()
    with pytest.raises(ValueError):
        series_candidate.run(candidate, "fuel", "2026Q3", cutoff, run_id, check=True)
    assert receipt.read_bytes() == before


def test_offsetting_fuel_revisions_remain_visible_when_all_gold_aggregates_match(tmp_path):
    inputs = {
        "workbook": original(
            fuel_bytes(
                [
                    (pd.Timestamp("2026-07-01"), 4),
                    (pd.Timestamp("2026-08-03"), 5),
                    (pd.Timestamp("2026-09-01"), 1),
                    (pd.Timestamp("2026-09-02"), 2),
                    (pd.Timestamp("2026-09-30"), 3),
                ]
            ),
            "eia",
            FUEL_SERIES,
            FUEL_URL,
            "xls",
        )
    }
    silver, _ = series_candidate.read("fuel", inputs, "2026Q3")
    previous = silver["fuel_prices"].copy()
    first = previous.date.eq(pd.Timestamp("2026-09-01"))
    second = previous.date.eq(pd.Timestamp("2026-09-02"))
    previous.loc[first, "price_usd_per_gallon"] += 0.25
    previous.loc[second, "price_usd_per_gallon"] -= 0.25
    changed = first | second
    previous.loc[changed, "source_value"] = previous.loc[changed, "price_usd_per_gallon"].map(str)
    pd.testing.assert_frame_equal(
        gold.macro_facts("fuel", "2026Q3", {"fuel_prices": previous}),
        gold.macro_facts("fuel", "2026Q3", silver),
        check_exact=True,
    )
    baseline = tmp_path / "baselines/fuel-native.parquet"
    baseline.parent.mkdir()
    previous.to_parquet(baseline, index=False)
    result = series_candidate.revisions(
        tmp_path,
        "baselines/fuel-native.parquet",
        "fuel",
        {"silver/fuel_prices": silver["fuel_prices"]},
    )
    assert result["baseline_table"] == "silver/fuel_prices"
    assert result["changed"] == 2 and result["added"] == result["removed"] == 0
    assert result["unchanged"] == len(previous) - 2


def test_opening_price_revision_is_visible_without_any_gold_price_change(tmp_path):
    silver, _ = series_candidate.read("equities", equities_inputs(), "2026Q3")
    previous = silver["market_prices"].copy()
    changed = previous.ticker.eq("AERO") & previous.date.eq(pd.Timestamp("2026-07-01"))
    assert changed.sum() == 1
    previous.loc[changed, "open"] += 0.25
    pd.testing.assert_frame_equal(
        gold.market_facts("2026Q3", previous),
        gold.market_facts("2026Q3", silver["market_prices"]),
        check_exact=True,
    )
    baseline = tmp_path / "baselines/market-native.parquet"
    baseline.parent.mkdir()
    previous.to_parquet(baseline, index=False)
    result = series_candidate.revisions(
        tmp_path,
        "baselines/market-native.parquet",
        "equities",
        {"silver/market_prices": silver["market_prices"]},
    )
    assert result["baseline_table"] == "silver/market_prices"
    assert result["changed"] == 1 and result["added"] == result["removed"] == 0
    assert result["unchanged"] == len(previous) - 1


def test_aggregate_only_baseline_cannot_claim_native_source_revision_comparison(tmp_path):
    silver, _ = series_candidate.read("fuel", macro_inputs("fuel"), "2026Q3")
    baseline = tmp_path / "baselines/old-gold.parquet"
    baseline.parent.mkdir()
    gold.macro_facts("fuel", "2026Q3", silver).to_parquet(baseline, index=False)
    with pytest.raises(ValueError, match="native Silver"):
        series_candidate.revisions(
            tmp_path,
            "baselines/old-gold.parquet",
            "fuel",
            {"silver/fuel_prices": silver["fuel_prices"]},
        )
