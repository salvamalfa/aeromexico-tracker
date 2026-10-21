"""Synthetic contract counterexamples only; never evidence of live GDELT access."""

import json

import pytest

from src.source_updates import gdelt
from tests.test_source_update_gdelt_candidate import AS_OF, capture
from tests.test_source_update_gdelt_candidate import workspace as workspace


def accepted(workspace):
    receipt = capture(workspace)
    gdelt.run(workspace, "2026M09", AS_OF, receipt["run_id"], execute=True)
    return receipt["run_id"]


def test_replay_cannot_silently_change_accepted_historical_cutoff(workspace):
    collection = accepted(workspace)
    with pytest.raises(ValueError, match="receipt|cutoff|changed"):
        gdelt.run(workspace, "2026M09", "2026-10-22T12:00:00-06:00", collection, check=True)


@pytest.mark.parametrize(
    "field,value",
    [("status", "blocked"), ("rows", 999), ("agent_eligible", True), ("agent_eligible", 0),
     ("publication", "authorized"),
     ("observation_period", "2026M08"), ("collection_run_id", "b" * 32)],
)
def test_replay_rejects_changed_acceptance_meaning(workspace, field, value):
    collection = accepted(workspace)
    path = workspace / "receipts/gdelt-2026M09.json"
    prior = json.loads(path.read_text())
    prior[field] = value
    path.write_text(json.dumps(prior))
    with pytest.raises(ValueError, match="receipt|changed"):
        gdelt.run(workspace, "2026M09", AS_OF, collection, check=True)


@pytest.mark.parametrize(
    "mutation", ["receipt_id", "item_http", "item_bytes", "source_http", "logical_key", "sidecar_key"]
)
def test_new_candidate_requires_consistent_successful_collection_identity(workspace, mutation):
    receipt = capture(workspace)
    path = workspace / "receipts" / f"collection-{receipt['run_id']}.json"
    if mutation in {"receipt_id", "item_http", "item_bytes"}:
        if mutation == "receipt_id":
            receipt["run_id"] = "b" * 32
        elif mutation == "item_http":
            receipt["items"][0]["http_status"] = 503
        else:
            receipt["items"][0]["bytes"] += 1
        path.write_text(json.dumps(receipt))
    else:
        manifest = workspace / "data/bronze/_manifest.jsonl"
        source = json.loads(manifest.read_text())
        if mutation == "source_http":
            source["http_status"] = None
        elif mutation == "logical_key":
            source["logical_key"] = "gdelt|unrelated_query|2026M08|json"
        manifest.write_text(json.dumps(source) + "\n")
        if mutation == "sidecar_key":
            source["logical_key"] = "gdelt|unrelated_query|2026M08|json"
        sidecar = workspace / "data/bronze" / (source["source_file"] + ".meta.json")
        sidecar.write_text(json.dumps(source))
    # Keep the filename/run selected before deliberate receipt corruption.
    collection = path.stem.removeprefix("collection-")
    with pytest.raises(ValueError, match="identity|successful|HTTP"):
        gdelt.run(workspace, "2026M09", AS_OF, collection, execute=True)
    assert not (workspace / "data/silver").exists()
    assert not (workspace / "data/gold").exists()
