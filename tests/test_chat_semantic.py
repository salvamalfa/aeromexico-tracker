from __future__ import annotations

import hashlib
import shutil
from pathlib import Path

import pytest

from src.conversational_analytics.data.snapshot import Snapshot, SnapshotError
from src.conversational_analytics.semantic.context import validate_context
from src.conversational_analytics.semantic.plan import PlanValidationError, QueryPlan, validate_plan

FIXTURE = Path(__file__).parent / "fixtures/chat/site"


def test_catalog_and_context_are_versioned_and_allowlisted() -> None:
    snapshot = Snapshot(FIXTURE)
    catalog = snapshot.catalog()
    assert (
        snapshot.version == hashlib.sha256((FIXTURE / "publication_manifest.json").read_bytes()).hexdigest()
    )
    assert catalog["metrics"]["metadata"]["review_status"] == "agent_reconciled_owner_review_pending"
    assert {entity["id"] for entity in catalog["entities"]["entities"]} >= {
        "AEROMEXICO",
        "AEROMEXICO_CONNECT",
        "INDUSTRY",
    }
    assert (
        validate_context(
            {
                "tab": "economy",
                "period": "2026Q2",
                "entity": ["AEROMEXICO", "VOLARIS"],
                "card_id": "unit-chart",
                "filters": {"range": "12", "entities": ["AEROMEXICO"]},
            }
        )["tab"]
        == "economy"
    )
    with pytest.raises(PlanValidationError):
        validate_context({"tab": "reading", "entity": "AEROMEXICO", "filters": {"prompt": "anything"}})
    with pytest.raises(PlanValidationError):
        validate_context({"tab": "market", "period": "2026Q2", "entity": "AEROMEXICO"})


def test_plan_rejects_unlisted_metric_and_wrong_dimensions() -> None:
    snapshot = Snapshot(FIXTURE)
    catalog = snapshot.catalog()
    with pytest.raises(PlanValidationError):
        validate_plan(
            QueryPlan(["secret_metric"], ["AEROMEXICO"], ["2026Q2"]),
            catalog,
            snapshot.version,
            snapshot.semantic_version,
        )
    with pytest.raises(PlanValidationError):
        validate_plan(
            QueryPlan(["company_passengers"], ["AEROMEXICO"], ["2026Q2"], dimensions=["route"]),
            catalog,
            snapshot.version,
            snapshot.semantic_version,
        )


def test_snapshot_rejects_modified_bytes_and_keeps_detached_payloads(tmp_path: Path) -> None:
    copied = tmp_path / "site"
    shutil.copytree(FIXTURE, copied)
    snapshot = Snapshot(copied)
    payload = snapshot.payload("data/v1/executive.json")
    payload["entities"]["AEROMEXICO"]["records"][0]["passengers"] = -1
    assert (
        snapshot.payload("data/v1/executive.json")["entities"]["AEROMEXICO"]["records"][0]["passengers"] > 0
    )

    target = copied / "data/v1/market.json"
    target.write_bytes(target.read_bytes() + b" ")
    with pytest.raises(SnapshotError, match="Hash o tamaño"):
        Snapshot(copied)
