"""Offline proof that terminal usage-known failures resume only missing cases."""

import hashlib
import json
import stat
from pathlib import Path

import pytest

from src.conversational_analytics import evaluation_live_campaign as campaign
from src.conversational_analytics.evaluation_live_reconciliation import reconcile_terminal_report


def _run(run_id: str, prompt_variant: str, case_ids: list[str]) -> dict:
    identity = {
        "stage": 1,
        "run_id": run_id,
        "candidate": "gpt-6-luna@medium",
        "model": "gpt-6-luna",
        "reasoning_effort": "medium",
        "text_verbosity": "medium",
        "prompt_variant": prompt_variant,
        "prompt_content_hash": f"prompt-{prompt_variant}",
        "tool_spec_hash": "tools-v1",
        "data_version": "data-v1",
        "semantic_version": "semantic-v1",
        "limits": {"max_tool_calls": 16},
        "repetition": 1,
    }
    return {
        "run_id": run_id,
        "candidate": identity["candidate"],
        "prompt": "fixed test prompt",
        "identity": identity,
        "identity_hash": f"hash-{run_id}",
        "limits": identity["limits"],
        "case_ids": case_ids,
    }


def _completed_report(identity: dict, cases: list[dict], cost: float) -> dict:
    return {
        "output_path": "/missing/in-memory-report.json",
        "run_status": "completed",
        "run_identity": identity,
        "estimated_cost_usd": cost,
        "models": [
            {
                "candidate": identity["candidate"],
                "model": identity["model"],
                "run_identity": identity,
                "estimated_cost_usd": cost,
                "known_estimated_cost_usd": cost,
                "spent_unknown": False,
                "quality_summary": {},
                "cases": [
                    {
                        "case_id": case["id"],
                        "run_identity": identity,
                        "provider_turn_started": True,
                        "model_turn_completed": True,
                        "usage_complete": True,
                        "estimated_cost_usd": cost / len(cases),
                        "known_estimated_cost_lower_bound_usd": cost / len(cases),
                        "status": "supported",
                        "input_tokens": 10,
                        "output_tokens": 2,
                        "latency_seconds": 0.25,
                        "turn_count": 1,
                        "quality": {"scored": False},
                    }
                    for case in cases
                ],
            }
        ],
    }


def _stage1_cases() -> list[dict]:
    safety = json.loads(Path("tests/fixtures/chat_evals/safety_current.json").read_text())["cases"]
    business = json.loads(Path("tests/fixtures/chat_evals/business_proposed.json").read_text())["cases"]
    return safety + [case for case in business if 1 in case.get("selection_stages", [])]


def _checkpoint_identity(runs: list[dict], root: Path) -> dict:
    return {
        "runs": [run["identity"] for run in runs],
        "run_identity_hashes": [run["identity_hash"] for run in runs],
        "budget_usd": 3.0,
        "expected_versions": {"data_version": "data-v1", "semantic_version": "semantic-v1"},
        "snapshot_root": str(root / "snapshot"),
        "prices": {"gpt-6-luna@medium": [0.1, 0.5]},
    }


def test_reconcile_53_rows_then_resume_only_five_and_write_private_58_row_composite(
    tmp_path, monkeypatch
) -> None:
    cases = _stage1_cases()
    case_ids = [case["id"] for case in cases]
    assert len(case_ids) == 58 and case_ids[:53][-1] == "N24"
    current = _run("f22-s1-current", "current", case_ids)
    proposed = _run("f22-s1-proposed", "proposed", case_ids)
    runs = [current, proposed]
    campaign_identity = _checkpoint_identity(runs, tmp_path)
    identity_hash = hashlib.sha256(
        json.dumps(campaign_identity, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    ).hexdigest()
    state_path = tmp_path / "campaign.json"
    original_state = {
        "identity": campaign_identity,
        "identity_hash": identity_hash,
        "budget_usd": 3.0,
        "known_spend_usd": 0.0,
        "spent_unknown": False,
        "status": "running",
        "active_run_id": current["run_id"],
        "completed_runs": {},
    }
    state_path.write_text(json.dumps(original_state))

    boundary_ids = {"es_card_conflicting_context", "en_private_context_override"}
    prompt_cost = (0.281405875 - 0.00729325) / 50
    raw_rows = []
    for case in cases[:53]:
        case_id = case["id"]
        if case_id in boundary_ids:
            raw_rows.append(
                {
                    "case_id": case_id,
                    "status": "application_context_rejected",
                    "provider_calls": 0,
                    "provider_request_count": 0,
                    "provider_turn_started": False,
                    "model_turn_completed": False,
                    "usage_complete": None,
                    "estimated_cost_usd": None,
                    "known_estimated_cost_lower_bound_usd": None,
                    "application_boundary_test_completed": True,
                    "quality": {"scored": False},
                }
            )
        elif case_id == "N24":
            raw_rows.append(
                {
                    "case_id": case_id,
                    "status": "provider_error",
                    "provider_turn_started": True,
                    "model_turn_completed": False,
                    "usage_complete": True,
                    "estimated_cost_usd": 0.00729325,
                    "known_estimated_cost_lower_bound_usd": 0.00729325,
                    "error_metadata": {
                        "exception_types": ["OpenAIProviderError"],
                        "reason_code": "tool_call_limit",
                    },
                    "run_identity": current["identity"],
                    "input_tokens": 1000,
                    "output_tokens": 20,
                    "latency_seconds": 10.0,
                    "quality": {"scored": False},
                }
            )
        else:
            raw_rows.append(
                {
                    "case_id": case_id,
                    "status": "supported",
                    "provider_turn_started": True,
                    "model_turn_completed": True,
                    "usage_complete": True,
                    "estimated_cost_usd": prompt_cost,
                    "known_estimated_cost_lower_bound_usd": prompt_cost,
                    "run_identity": current["identity"],
                    "input_tokens": 1000,
                    "output_tokens": 20,
                    "latency_seconds": 1.0,
                    "turn_count": 1,
                    "quality": {"scored": False},
                }
            )
    prior_cost = sum(row.get("estimated_cost_usd") or 0 for row in raw_rows if row["provider_turn_started"])
    report_path = tmp_path / "original-report.json"
    report_path.write_text(
        json.dumps(
            {
                "output_path": str(report_path),
                "run_status": "stopped",
                "probe_only": False,
                "candidate_models": [current["candidate"]],
                "run_identity": current["identity"],
                "data_version": "data-v1",
                "semantic_version": "semantic-v1",
                "estimated_cost_usd": prior_cost,
                "models": [
                    {
                        "candidate": current["candidate"],
                        "model": current["identity"]["model"],
                        "run_identity": current["identity"],
                        "spent_unknown": False,
                        "estimated_cost_usd": prior_cost,
                        "known_estimated_cost_usd": prior_cost,
                        "quality_summary": {"human_rubric_pending_count": 56},
                        "cases": raw_rows,
                    }
                ],
            }
        )
    )
    report_hash = hashlib.sha256(report_path.read_bytes()).hexdigest()
    before = state_path.read_bytes()
    reconciled = reconcile_terminal_report(
        state_path=state_path,
        report_path=report_path,
        expected_report_sha256=report_hash,
        runs=runs,
        cases=cases,
        apply=True,
    )
    assert reconciled["reconciled_case_count"] == 53
    assert reconciled["missing_case_ids"] == case_ids[53:]
    assert Path(reconciled["backup_path"]).read_bytes() == before
    assert hashlib.sha256(report_path.read_bytes()).hexdigest() == report_hash

    calls = []

    def provider_stub(**kwargs):
        selected = [case["id"] for case in kwargs["cases"]]
        calls.append((kwargs["run_identity"]["run_id"], selected))
        cost = 0.005 * len(selected)
        return _completed_report(kwargs["run_identity"], kwargs["cases"], cost)

    monkeypatch.setattr(campaign, "_live_provider_run", provider_stub)
    final = campaign.run_campaign(
        runs=runs,
        cases=cases,
        budget_usd=3.0,
        snapshot_root=tmp_path / "snapshot",
        prices={"gpt-6-luna@medium": (0.1, 0.5)},
        expected_versions={"data_version": "data-v1", "semantic_version": "semantic-v1"},
        state_path=state_path,
        output_dir=tmp_path / "reports",
        resume=True,
    )
    assert calls == [(current["run_id"], case_ids[53:]), (proposed["run_id"], case_ids)]
    assert final["status"] == "completed"
    summary = final["run_summaries"][0]
    composite = json.loads(Path(summary["report_path"]).read_text())
    assert composite["output_path"] == summary["report_path"]
    assert stat.S_IMODE(Path(summary["report_path"]).stat().st_mode) == 0o600
    model = composite["models"][0]
    assert len(model["cases"]) == len({row["case_id"] for row in model["cases"]}) == 58
    assert model["terminal_error_count"] == 1 and model["model_turn_completed_count"] == 55
    assert model["known_estimated_cost_usd"] == pytest.approx(prior_cost + 0.025)
    assert model["token_totals"]["turn_count"] == 56
    assert model["token_totals"]["input_tokens"] == 51050
    assert model["token_totals"]["output_tokens"] == 1030
    assert model["planned_user_message_count"] == 62
    assert composite["quality_review_status"] == "pending_human_review"
    assert composite["composite_parts"][0]["sha256"] == report_hash


@pytest.mark.parametrize(
    "mutation",
    ["identity", "unknown", "http_error", "missing_cost", "duplicate", "partial", "contradictory_counter"],
)
def test_reconciliation_rejects_tampered_or_ambiguous_report_before_checkpoint_write(
    tmp_path, mutation
) -> None:
    cases = _stage1_cases()
    case_ids = [case["id"] for case in cases]
    run = _run("active", "current", case_ids)
    identity = _checkpoint_identity([run], tmp_path)
    state = {
        "identity": identity,
        "identity_hash": hashlib.sha256(
            json.dumps(identity, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
        ).hexdigest(),
        "budget_usd": 3.0,
        "known_spend_usd": 0.0,
        "spent_unknown": False,
        "status": "running",
        "active_run_id": run["run_id"],
        "completed_runs": {},
    }
    state_path = tmp_path / "state.json"
    state_path.write_text(json.dumps(state))
    # Minimal ended prefix: two validated zero-call rows, one known completion, and one tool limit.
    ids = ["es_card_conflicting_context", "N01", "en_private_context_override", "N02"]
    rows = [
        {
            "case_id": ids[0],
            "status": "application_context_rejected",
            "provider_calls": 0,
            "provider_turn_started": False,
            "model_turn_completed": False,
            "usage_complete": None,
            "estimated_cost_usd": None,
            "known_estimated_cost_lower_bound_usd": None,
            "application_boundary_test_completed": True,
        },
        {
            "case_id": "N01",
            "status": "supported",
            "provider_turn_started": True,
            "model_turn_completed": True,
            "usage_complete": True,
            "estimated_cost_usd": 0.1,
            "run_identity": run["identity"],
        },
        {
            "case_id": ids[2],
            "status": "application_context_rejected",
            "provider_calls": 0,
            "provider_turn_started": False,
            "model_turn_completed": False,
            "usage_complete": None,
            "estimated_cost_usd": None,
            "known_estimated_cost_lower_bound_usd": None,
            "application_boundary_test_completed": True,
        },
        {
            "case_id": "N02",
            "status": "provider_error",
            "provider_turn_started": True,
            "model_turn_completed": False,
            "usage_complete": True,
            "estimated_cost_usd": 0.1,
            "known_estimated_cost_lower_bound_usd": 0.1,
            "error_metadata": {"reason_code": "tool_call_limit"},
            "run_identity": run["identity"],
        },
    ]
    report = {
        "output_path": str(tmp_path / "report.json"),
        "run_status": "stopped",
        "probe_only": False,
        "candidate_models": [run["candidate"]],
        "run_identity": run["identity"],
        "data_version": "data-v1",
        "semantic_version": "semantic-v1",
        "models": [
            {
                "candidate": run["candidate"],
                "model": run["identity"]["model"],
                "run_identity": run["identity"],
                "spent_unknown": False,
                "estimated_cost_usd": 0.2,
                "known_estimated_cost_usd": 0.2,
                "cases": rows,
            }
        ],
    }
    if mutation == "identity":
        report["run_identity"]["prompt_content_hash"] = "tampered"
    if mutation == "unknown":
        report["models"][0]["spent_unknown"] = True
    if mutation == "http_error":
        rows[-1]["error_metadata"]["reason_code"] = "http_429"
    if mutation == "missing_cost":
        rows[-1]["estimated_cost_usd"] = None
    if mutation == "duplicate":
        rows.append(dict(rows[-1]))
    if mutation == "partial":
        rows.pop()
        report["models"][0]["estimated_cost_usd"] = report["models"][0]["known_estimated_cost_usd"] = 0.1
    if mutation == "contradictory_counter":
        rows[0]["provider_request_count"] = 1
    report_path = tmp_path / "report.json"
    report["output_path"] = str(report_path)
    report_path.write_text(json.dumps(report))
    state_before = state_path.read_bytes()
    with pytest.raises(ValueError):
        reconcile_terminal_report(
            state_path=state_path,
            report_path=report_path,
            expected_report_sha256=hashlib.sha256(report_path.read_bytes()).hexdigest(),
            runs=[run],
            cases=cases,
        )
    assert state_path.read_bytes() == state_before
