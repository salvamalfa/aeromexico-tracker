"""Offline safety gates for no-replay F2.9 stage-2 continuation."""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from pathlib import Path

import pytest

from scripts.chat.continue_stage2_campaign import _require_private_destination
from src.conversational_analytics.evaluation import load_cases, phase_cases
from src.conversational_analytics.evaluation_campaign import (
    CAMPAIGN_CANDIDATES,
    _digest,
    build_campaign_runs,
)
from src.conversational_analytics.evaluation_continuation import prepare_stage2_continuation

ROOT = Path(__file__).resolve().parents[1]
BUSINESS = load_cases(ROOT / "tests/fixtures/chat_evals/business_proposed.json")
SAFETY = load_cases(ROOT / "tests/fixtures/chat_evals/safety_current.json")
COMMON = {
    "data_version": "data-v7",
    "semantic_version": "semantic-v3",
    "prompts": {"current": "Instrucciones actuales.", "proposed": "Instrucciones propuestas."},
    "tool_specs": [{"name": "query_metrics", "parameters": {"type": "object"}}],
    "limits": {"max_tool_calls": 8, "max_turn_seconds": 120},
    "text_verbosity": "medium",
}


def _fixtures() -> tuple[list[dict], dict, dict, bytes, bytes, bytes, dict]:
    cases = phase_cases(BUSINESS, SAFETY, 2)
    planned = build_campaign_runs(2, cases, **COMMON)
    for run in planned:
        run["identity"]["execution_commit"] = "a" * 40
        run["identity_hash"] = _digest(run["identity"])
        run["execution_commit"] = "a" * 40
    catalog_bytes = (ROOT / "config/chat/models.json").read_bytes()
    catalog = json.loads(catalog_bytes)
    identity = {
        "runs": [deepcopy(run["identity"]) for run in planned],
        "run_identity_hashes": [run["identity_hash"] for run in planned],
        "budget_usd": 8.0,
        "expected_versions": {"data_version": "data-v7", "semantic_version": "semantic-v3"},
        "snapshot_root": "/private/snapshot",
        "prices": {
            candidate: [
                catalog["models"][definition["model"]]["input_usd_per_million"],
                catalog["models"][definition["model"]]["output_usd_per_million"],
            ]
            for candidate, definition in CAMPAIGN_CANDIDATES.items()
        },
    }
    campaign_hash = _digest(identity)
    failed = planned[0]
    attempted = failed["case_ids"][:9]
    failed_case = attempted[-1]
    source = {
        "identity": identity,
        "identity_hash": campaign_hash,
        "status": "stopped_unknown_spend",
        "budget_usd": 8.0,
        "known_spend_usd": 0.05460125,
        "spent_unknown": True,
        "active_run_id": None,
        "completed_runs": {
            failed["run_id"]: {
                "identity": deepcopy(failed["identity"]),
                "identity_hash": failed["identity_hash"],
                "complete": False,
                "stopped_reason": "provider_error",
                "known_estimated_cost_usd": 0.05460125,
                "spent_unknown": True,
                "cases": [
                    *[
                        {
                            "case_id": cid,
                            "status": "supported",
                            "usage_complete": True,
                            "model_turn_completed": True,
                        }
                        for cid in attempted[:-1]
                    ],
                    {
                        "case_id": failed_case,
                        "status": "provider_error",
                        "usage_complete": False,
                        "model_turn_completed": False,
                    },
                ],
            }
        },
    }
    ledger_bytes = json.dumps(source, sort_keys=True, separators=(",", ":")).encode()
    report = {
        "campaign_identity_hash": campaign_hash,
        "run_identity_hash": failed["identity_hash"],
        "run_identity": failed["identity"],
        "case_count": 15,
    }
    report_bytes = json.dumps(report, sort_keys=True, separators=(",", ":")).encode()
    evidence = {
        "schema_version": 1,
        "kind": "f2_9_owner_usage_confirmation",
        "owner_attestation": {
            "source": "owner_reported_OpenAI_Usage",
            "aggregate_date": "2026-10-10",
            "model": "gpt-6-luna",
            "input_tokens": 408_550,
            "output_tokens": 7_065,
            "includes_failed_call": True,
            "exact_question": "owner confirmation recorded privately",
            "exact_owner_answer": "owner confirmation recorded privately",
            "external_usage_independently_verified": False,
        },
        "source_identity": {
            "campaign_ledger_sha256": hashlib.sha256(ledger_bytes).hexdigest(),
            "report_sha256": hashlib.sha256(report_bytes).hexdigest(),
            "execution_commit": failed["identity"]["execution_commit"],
            "campaign_identity_hash": campaign_hash,
            "run_identity_hash": failed["identity_hash"],
        },
        "reconciliation": {
            "complete_responses": 8,
            "attempted_responses": 9,
            "aggregate_tokens_match_known_case_lower_bounds": True,
            "failed_case_individual_usage": None,
            "failed_case_cost_estimate_usd": None,
            "known_completed_case_cost_estimate_usd": 0.05460125,
            "invoice_total_usd": None,
        },
    }
    evidence_bytes = json.dumps(evidence, sort_keys=True, separators=(",", ":")).encode()
    reconciliation = {
        "status": "owner_confirmed_aggregate",
        "source_campaign_identity_hash": campaign_hash,
        "source_ledger_sha256": hashlib.sha256(ledger_bytes).hexdigest(),
        "source_report_sha256": hashlib.sha256(report_bytes).hexdigest(),
        "evidence_sha256": hashlib.sha256(evidence_bytes).hexdigest(),
    }
    return planned, source, reconciliation, ledger_bytes, report_bytes, evidence_bytes, catalog


def _prepare(
    planned: list[dict],
    source: dict,
    reconciliation: dict,
    ledger: bytes,
    report: bytes,
    evidence: bytes,
    catalog: dict,
) -> dict:
    for run in planned:
        run["identity"]["execution_commit"] = "b" * 40
        run["identity_hash"] = _digest(run["identity"])
        run["execution_commit"] = "b" * 40
    catalog_bytes = (ROOT / "config/chat/models.json").read_bytes()
    return prepare_stage2_continuation(
        planned,
        source,
        usage_reconciliation=reconciliation,
        evidence_bytes=evidence,
        source_ledger_bytes=ledger,
        source_ledger_sha256=hashlib.sha256(ledger).hexdigest(),
        source_report_bytes=report,
        source_report_sha256=hashlib.sha256(report).hexdigest(),
        model_catalog_bytes=catalog_bytes,
        model_catalog=catalog,
    )


def test_continuation_selects_only_unattempted_slots_and_carries_aggregate_without_double_count() -> None:
    planned, source, reconciliation, ledger, report, evidence, catalog = _fixtures()
    continuation = _prepare(planned, source, reconciliation, ledger, report, evidence, catalog)

    assert len(continuation["runs"]) == 4
    assert continuation["case_count"] == 51
    assert continuation["source_completed_response_count"] == 8
    assert continuation["source_unresolved_failure_count"] == 1
    assert continuation["response_count_ceiling_if_continuation_completes"] == 59
    assert continuation["daily_aggregate_usage_scope"] == "daily_account_aggregate"
    assert continuation["daily_aggregate_estimated_cost_usd"] == pytest.approx(0.05460125)
    assert continuation["accounted_spend_usd"] == pytest.approx(0.05460125)
    assert continuation["remaining_budget_usd"] == pytest.approx(7.94539875)
    assert continuation["reconciled_failed_case_cost_usd"] is None
    assert continuation["failed_case_usage"] == "unknown"
    partial = next(run for run in continuation["runs"] if run["candidate"] == planned[0]["candidate"])
    assert partial["case_ids"] == planned[0]["case_ids"][9:]
    assert len(partial["case_ids"]) == 6
    assert not set(partial["case_ids"]) & set(
        source["completed_runs"][planned[0]["run_id"]]["cases"][i]["case_id"] for i in range(9)
    )
    assert all(run["identity"]["execution_commit"] == "b" * 40 for run in continuation["runs"])


def test_continuation_rejects_changed_source_bytes_and_wrong_owner_attestation() -> None:
    planned, source, reconciliation, ledger, report, evidence, catalog = _fixtures()
    with pytest.raises(ValueError, match="ledger"):
        prepare_stage2_continuation(
            planned,
            source,
            usage_reconciliation=reconciliation,
            evidence_bytes=evidence,
            source_ledger_bytes=ledger + b" ",
            source_ledger_sha256=hashlib.sha256(ledger).hexdigest(),
            source_report_bytes=report,
            source_report_sha256=hashlib.sha256(report).hexdigest(),
            model_catalog_bytes=(ROOT / "config/chat/models.json").read_bytes(),
            model_catalog=catalog,
        )
    altered = json.loads(evidence)
    altered["reconciliation"]["failed_case_cost_estimate_usd"] = 0
    altered_bytes = json.dumps(altered, sort_keys=True, separators=(",", ":")).encode()
    bad_reconciliation = dict(reconciliation, evidence_sha256=hashlib.sha256(altered_bytes).hexdigest())
    with pytest.raises(ValueError, match="importe exacto"):
        _prepare(planned, source, bad_reconciliation, ledger, report, altered_bytes, catalog)


def test_continuation_rejects_overspend_and_identity_drift() -> None:
    planned, source, reconciliation, ledger, report, evidence, catalog = _fixtures()
    overspend_source = deepcopy(source)
    overspend_source["known_spend_usd"] = 8.0
    overspend_run = next(iter(overspend_source["completed_runs"].values()))
    overspend_run["known_estimated_cost_usd"] = 8.0
    overspend_ledger = json.dumps(overspend_source, sort_keys=True, separators=(",", ":")).encode()
    altered_evidence = json.loads(evidence)
    altered_evidence["source_identity"]["campaign_ledger_sha256"] = hashlib.sha256(
        overspend_ledger
    ).hexdigest()
    altered_evidence["reconciliation"]["known_completed_case_cost_estimate_usd"] = 8.0
    altered_bytes = json.dumps(altered_evidence, sort_keys=True, separators=(",", ":")).encode()
    altered_rec = dict(
        reconciliation,
        source_ledger_sha256=hashlib.sha256(overspend_ledger).hexdigest(),
        evidence_sha256=hashlib.sha256(altered_bytes).hexdigest(),
    )
    with pytest.raises(ValueError, match="No queda presupuesto"):
        prepare_stage2_continuation(
            planned,
            overspend_source,
            usage_reconciliation=altered_rec,
            evidence_bytes=altered_bytes,
            source_ledger_bytes=overspend_ledger,
            source_ledger_sha256=hashlib.sha256(overspend_ledger).hexdigest(),
            source_report_bytes=report,
            source_report_sha256=hashlib.sha256(report).hexdigest(),
            model_catalog_bytes=(ROOT / "config/chat/models.json").read_bytes(),
            model_catalog=catalog,
        )
    drifted = deepcopy(planned)
    drifted[0]["case_ids"][0] = "N99"
    with pytest.raises(ValueError, match="IDs planeados"):
        _prepare(drifted, source, reconciliation, ledger, report, evidence, catalog)


def test_plan_path_must_be_private_before_any_directory_permission_change(tmp_path: Path) -> None:
    outside = tmp_path / "public-plan.json"
    mode_before = tmp_path.stat().st_mode & 0o777
    with pytest.raises(ValueError, match="dentro de .state"):
        _require_private_destination(outside, label="plan-path")
    assert tmp_path.stat().st_mode & 0o777 == mode_before
