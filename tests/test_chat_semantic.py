from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from src.conversational_analytics.data.snapshot import Snapshot, SnapshotError, data_version
from src.conversational_analytics.evaluation import load_cases
from src.conversational_analytics.providers._openai_helpers import SYSTEM_INSTRUCTIONS
from src.conversational_analytics.semantic.context import validate_context
from src.conversational_analytics.semantic.plan import PlanValidationError, QueryPlan, validate_plan

FIXTURE = Path(__file__).parent / "fixtures/chat/site"


def test_system_instructions_resolve_omitted_period_without_resolving_other_ambiguity() -> None:
    assert "(1) un periodo explícito en la pregunta actual" in SYSTEM_INSTRUCTIONS
    assert "(2) el periodo previo solo si" in SYSTEM_INSTRUCTIONS
    assert "(3) el periodo seleccionado en el contexto validado" in SYSTEM_INSTRUCTIONS
    assert "pide el periodo" in SYSTEM_INSTRUCTIONS
    assert "no infieras ni reemplaces métrica, entidad, segmento, mercado" in SYSTEM_INSTRUCTIONS
    assert "denominador o fuente con el contexto" in SYSTEM_INSTRUCTIONS


def test_supported_holdout_contexts_pass_production_validation() -> None:
    supported_contexts = [
        case["context"]
        for case in load_cases()
        if case["expected"]["status"] == "supported" and "context" in case
    ]

    assert supported_contexts
    for context in supported_contexts:
        assert validate_context(context) == context


def test_catalog_and_context_are_versioned_and_allowlisted() -> None:
    snapshot = Snapshot(FIXTURE)
    catalog = snapshot.catalog()
    manifest = json.loads((FIXTURE / "publication_manifest.json").read_text())
    assert snapshot.version == data_version(manifest)
    assert catalog["metrics"]["metadata"]["review_status"] == "owner_approved_mvp"
    assert catalog["entities"]["metadata"]["review_status"] == "owner_approved_mvp"
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


def test_data_version_ignores_interface_releases_but_tracks_data() -> None:
    manifest = json.loads((FIXTURE / "publication_manifest.json").read_text())
    baseline = data_version(manifest)

    ui_release = json.loads(json.dumps(manifest))
    ui_release["code_commit"] = "0" * 40
    ui_release["generated_at"] = "2099-01-01T00:00:00+00:00"
    ui_release["files"].append({"path": "assets/new-ui.js", "sha256": "1" * 64, "bytes": 10})
    assert data_version(ui_release) == baseline

    data_change = json.loads(json.dumps(manifest))
    entry = next(item for item in data_change["files"] if item["path"].startswith("data/"))
    entry["sha256"] = "2" * 64
    assert data_version(data_change) != baseline

    contract_change = json.loads(json.dumps(manifest))
    first_contract = next(iter(contract_change["contracts"]))
    contract_change["contracts"][first_contract] = "3" * 64
    assert data_version(contract_change) != baseline
