"""Independent synthetic replay contracts; these never certify live sources."""

import hashlib
import json
import shutil
from uuid import uuid4

import pandas as pd
import pytest

from src.source_updates import readiness, retained, series_candidate
from src.source_updates.catalog import ROOT
from tests.test_source_update_series_independent import equities_inputs, macro_inputs, materialize


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
