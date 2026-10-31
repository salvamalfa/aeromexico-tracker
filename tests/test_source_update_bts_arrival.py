"""Synthetic unit probes for literal BTS originals; real dossier replay is retained separately."""

from copy import deepcopy
from pathlib import Path
from zipfile import ZipFile

import pandas as pd
import pytest

from scripts import source_update_handoffs as handoffs
from scripts import source_update_monthly_handoff as monthly
from src.source_updates import collection
from src.transform.stage6_facts import stable_hash

NOW = "2026-10-29T04:00:00Z"


@pytest.fixture
def arrival(tmp_path, monkeypatch):
    monkeypatch.setattr(collection, "ROOT", tmp_path)
    candidate = tmp_path / "tmp/source-updates/bts-candidate"
    candidate.mkdir(parents=True)
    original = candidate / "original.zip"
    with ZipFile(original, "w") as archive:
        archive.writestr("segments.csv", "YEAR,MONTH,PASSENGERS\n2026,7,1\n")
    original_ref = handoffs.file_ref(original)
    frames = {
        "silver/bts_t100_segment": pd.DataFrame({"source_hash": [original_ref["sha256"]]}),
        "gold/fact_route_traffic": pd.DataFrame(
            {"passengers": [1], "source_hash": [stable_hash([original_ref["sha256"]])]}
        ),
        "gold/bridge_record_lineage": pd.DataFrame({"source_record_id": ["synthetic-row"]}),
    }
    outputs = {}
    for key, frame in frames.items():
        path = candidate / "data" / (key + ".parquet")
        path.parent.mkdir(parents=True, exist_ok=True)
        frame.to_parquet(path)
        outputs[key] = handoffs.file_hash(path)
    checked = {
        "status": "checks_passed",
        "latest_source_availability_verified": True,
        "output_sha256": outputs,
    }
    monkeypatch.setattr(handoffs.readiness, "check_task", lambda *args: deepcopy(checked))
    observation = {
        "item": {
            "id": "bts",
            "product": "bts_segments",
            "adapter": "bts",
            "period": "2026M09",
            "source_period": "2026M07",
            "workspace": str(candidate),
            "receipt_id": "a" * 32,
            "candidate_as_of": NOW,
            "required": True,
        },
        "as_of": NOW,
        "mode": "validated_publication_arrival",
        "publication_evidence": original_ref,
    }
    return observation, checked, tmp_path / "tmp/source-updates/outbox"


def test_bts_literal_zip_uses_replayed_pinned_silver_after_gold_and_lineage(arrival):
    observation, checked, workspace = arrival
    verified = handoffs.verify_candidate(observation, workspace)
    assert verified["checked"] == checked
    assert verified["source_binding"]["item"]["period"] == "2026M09"
    assert monthly.native_item(observation["item"])["period"] == "2026M07"
    gold = pd.read_parquet(Path(observation["item"]["workspace"]) / "data/gold/fact_route_traffic.parquet")
    assert observation["publication_evidence"]["sha256"] not in set(gold.source_hash)


def test_bts_other_zip_cannot_borrow_a_valid_native_silver(arrival):
    observation, _, workspace = arrival
    other = Path(observation["item"]["workspace"]) / "other.zip"
    with ZipFile(other, "w") as archive:
        archive.writestr("other.csv", "not the selected source")
    with pytest.raises(ValueError, match="not the original"):
        handoffs.verify_candidate(
            {**observation, "publication_evidence": handoffs.file_ref(other)}, workspace
        )


@pytest.mark.parametrize("mutation", ["injected_silver", "stale_output_hash", "redirected_silver"])
def test_bts_only_reads_the_exact_pinned_silver_bytes(arrival, mutation):
    observation, checked, workspace = arrival
    path = Path(observation["item"]["workspace"]) / "data/silver/bts_t100_segment.parquet"
    if mutation == "injected_silver":
        pd.DataFrame({"source_hash": ["b" * 64]}).to_parquet(path)
    elif mutation == "stale_output_hash":
        checked["output_sha256"]["silver/bts_t100_segment"] = "0" * 64
    else:
        redirected = path.with_name("injected.parquet")
        path.rename(redirected)
        path.symlink_to(redirected)
    with pytest.raises(ValueError, match="BTS .*Silver|cannot contain symlinks"):
        handoffs.verify_candidate(observation, workspace)


@pytest.mark.parametrize(
    "key", ["silver/bts_t100_segment", "gold/fact_route_traffic", "gold/bridge_record_lineage"]
)
def test_bts_requires_the_full_replayed_source_proof_not_a_loose_silver_file(arrival, key):
    observation, checked, workspace = arrival
    del checked["output_sha256"][key]
    with pytest.raises(ValueError, match="replay-verified Gold, lineage and pinned native Silver"):
        handoffs.verify_candidate(observation, workspace)


def test_bts_failed_replay_cannot_fall_back_to_silver(arrival, monkeypatch):
    observation, _, workspace = arrival

    def failed_replay(*args):
        raise ValueError("Synthetic failed native Gold/lineage replay")

    def must_not_read(*args):
        pytest.fail("Publication hashes must not be read before readiness passes")

    monkeypatch.setattr(handoffs.readiness, "check_task", failed_replay)
    monkeypatch.setattr(monthly, "publication_source_hashes", must_not_read)
    with pytest.raises(ValueError, match="failed native Gold/lineage replay"):
        handoffs.verify_candidate(observation, workspace)


def test_other_products_keep_gold_literal_hash_requirement(arrival):
    observation, checked, _ = arrival
    item = {**observation["item"], "product": "am_traffic_ir"}
    assert observation["publication_evidence"]["sha256"] not in monthly.publication_source_hashes(
        item, checked
    )
