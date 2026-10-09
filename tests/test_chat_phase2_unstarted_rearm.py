"""Offline recovery proof for a single startup failure with no provider request."""

from __future__ import annotations

import hashlib
import json
import stat
from pathlib import Path

import pytest

from src.conversational_analytics import evaluation_live_campaign as campaign
from src.conversational_analytics.evaluation_live_rearm import rearm_unstarted_case

_TARGET = "f22-s1-gpt-6-luna-medium-current-r1"
_FAILURE_SHA = "12067cc4c428d2df5c74404d844d0a08f929b7578fbae5233b9e204f86da36a6"
_KNOWN_SOURCE_COST = 0.281405875
_MISSING = ["N25", "N26", "N27", "N28", "N30"]


def _stage1_cases() -> list[dict]:
    safety = json.loads(Path("tests/fixtures/chat_evals/safety_current.json").read_text())["cases"]
    fixture = json.loads(Path("tests/fixtures/chat_evals/business_proposed.json").read_text())
    return safety + [case for case in fixture["cases"] if 1 in case.get("selection_stages", [])]


def _runs(cases: list[dict]) -> list[dict]:
    case_ids = [case["id"] for case in cases]
    result = []
    for variant in ("current", "proposed"):
        run_id = f"f22-s1-gpt-6-luna-medium-{variant}-r1"
        identity = {
            "stage": 1,
            "run_id": run_id,
            "candidate": "gpt-6-luna@medium",
            "model": "gpt-6-luna",
            "reasoning_effort": "medium",
            "text_verbosity": "medium",
            "prompt_variant": variant,
            "prompt_content_hash": f"prompt-{variant}",
            "tool_spec_hash": "tools-v1",
            "data_version": "data-v1",
            "semantic_version": "semantic-v1",
            "limits": {
                "max_tool_calls": 16,
                "max_message_chars": 8000,
                "max_tool_result_bytes": 16000,
                "max_turn_seconds": 180,
            },
            "repetition": 1,
        }
        result.append(
            {
                "run_id": run_id,
                "candidate": identity["candidate"],
                "prompt": f"approved {variant} prompt",
                "identity": identity,
                "identity_hash": hashlib.sha256(run_id.encode()).hexdigest(),
                "limits": identity["limits"],
                "case_ids": case_ids,
            }
        )
    return result


def _identity(runs: list[dict], root: Path) -> dict:
    return {
        "runs": [run["identity"] for run in runs],
        "run_identity_hashes": [run["identity_hash"] for run in runs],
        "budget_usd": 3.0,
        "expected_versions": {"data_version": "data-v1", "semantic_version": "semantic-v1"},
        "snapshot_root": str(root),
        "prices": {"gpt-6-luna@medium": [0.1, 0.5]},
    }


def _boundary(case_id: str, identity: dict) -> dict:
    return {
        "case_id": case_id,
        "status": "application_context_rejected",
        "provider_calls": 0,
        "provider_request_count": 0,
        "provider_turn_started": False,
        "model_turn_completed": False,
        "usage_complete": None,
        "estimated_cost_usd": None,
        "known_estimated_cost_lower_bound_usd": None,
        "quality": {"scored": False, "not_scored_reason": "application_context_rejected"},
    }


def _completed_row(case: dict, identity: dict, cost: float) -> dict:
    expected = case.get("expected", {})
    status = "multi_turn" if isinstance(expected.get("turns"), list) else expected.get("status", "supported")
    return {
        "case_id": case["id"],
        "run_identity": identity,
        "candidate": identity["candidate"],
        "model": identity["model"],
        "status": status,
        "provider_turn_started": True,
        "model_turn_completed": True,
        "usage_complete": True,
        "estimated_cost_usd": cost,
        "known_estimated_cost_lower_bound_usd": cost,
        "input_tokens": 1000,
        "output_tokens": 20,
        "latency_seconds": 1.0,
        "turn_count": 1,
        "quality": {"scored": False, "requires_blinded_human_rubric": True},
    }


def _source_report(path: Path, run: dict, cases: list[dict]) -> dict:
    identity = run["identity"]
    boundary_ids = {"es_card_conflicting_context", "en_private_context_override"}
    started_count = len(cases) - len(boundary_ids)
    per_case = (_KNOWN_SOURCE_COST - 0.00729325) / 50
    rows = []
    for case in cases:
        if case["id"] in boundary_ids:
            rows.append(_boundary(case["id"], identity))
        elif case["id"] == "N24":
            rows.append(
                {
                    "case_id": "N24",
                    "run_identity": identity,
                    "status": "provider_error",
                    "provider_turn_started": True,
                    "model_turn_completed": False,
                    "usage_complete": True,
                    "estimated_cost_usd": 0.00729325,
                    "known_estimated_cost_lower_bound_usd": 0.00729325,
                    "input_tokens": 1000,
                    "output_tokens": 20,
                    "error_metadata": {"reason_code": "tool_call_limit"},
                }
            )
        else:
            rows.append(_completed_row(case, identity, per_case))
    actual_started = sum(row.get("provider_turn_started") is True for row in rows)
    assert actual_started == started_count == 51
    total = sum(row.get("estimated_cost_usd") or 0 for row in rows)
    report = {
        "output_path": str(path),
        "run_status": "stopped",
        "probe_only": False,
        "candidate_models": [run["candidate"]],
        "run_identity": identity,
        "data_version": identity["data_version"],
        "semantic_version": identity["semantic_version"],
        "estimated_cost_usd": total,
        "known_estimated_cost_usd": total,
        "models": [
            {
                "candidate": run["candidate"],
                "model": identity["model"],
                "run_identity": identity,
                "spent_unknown": False,
                "estimated_cost_usd": total,
                "known_estimated_cost_usd": total,
                "cases": rows,
            }
        ],
    }
    _write_private(path, report)
    return report


def _failed_attempt(path: Path, run: dict, case_id: str = "N25") -> dict:
    identity = run["identity"]
    row = {
        "case_id": case_id,
        "run_identity": identity,
        "candidate": identity["candidate"],
        "model": identity["model"],
        "status": "provider_error",
        "provider_turn_started": False,
        "model_turn_completed": False,
        "usage_complete": False,
        "estimated_cost_usd": None,
        "known_estimated_cost_lower_bound_usd": 0,
        "input_tokens": None,
        "output_tokens": None,
        "cached_tokens": "unknown",
        "reasoning_tokens": "unknown; included in output_tokens",
        "session_id": None,
        "tool_calls": [],
        "turn_usage": [],
        "provider_cancel": "not_available",
        "post_cancel_usage_reconciliation": "not_attempted",
        "quality": {"scored": False, "not_scored_reason": "provider_error"},
        "error_metadata": {"exception_types": ["OpenAIProviderError"]},
    }
    report = {
        "output_path": str(path),
        "run_status": "stopped",
        "probe_only": False,
        "candidate_models": [run["candidate"]],
        "run_identity": identity,
        "data_version": identity["data_version"],
        "semantic_version": identity["semantic_version"],
        "estimated_cost_usd": 0,
        "known_estimated_cost_usd": 0,
        "models": [
            {
                "candidate": run["candidate"],
                "model": identity["model"],
                "run_identity": identity,
                "spent_unknown": False,
                "estimated_cost_usd": 0,
                "known_estimated_cost_usd": 0,
                "stopped_reason": "provider_error_or_usage_unknown; no further cases admitted",
                "token_totals": {
                    "input_tokens": 0,
                    "output_tokens": 0,
                    "known_input_tokens_lower_bound": 0,
                    "known_output_tokens_lower_bound": 0,
                    "usage_complete_case_count": 0,
                    "turn_count": 0,
                    "cached_tokens": "unknown",
                    "reasoning_tokens": "unknown; included in output_tokens",
                },
                "cases": [row],
            }
        ],
    }
    _write_private(path, report)
    return report


def _compact(row: dict) -> dict:
    keys = (
        "case_id",
        "status",
        "provider_turn_started",
        "model_turn_completed",
        "usage_complete",
        "estimated_cost_usd",
        "known_estimated_cost_lower_bound_usd",
        "provider_calls",
        "quality",
        "error_metadata",
    )
    return {key: row[key] for key in keys if key in row}


def _write_private(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
    path.chmod(0o600)


def _campaign(tmp_path: Path) -> tuple[dict, list[dict], list[dict], Path, Path, Path]:
    all_cases = _stage1_cases()
    runs = _runs(all_cases)
    current = runs[0]
    ids = current["case_ids"]
    assert len(ids) == 58 and ids[53:] == _MISSING and ids.index("N24") < 53
    first_path = tmp_path / "source-53.json"
    source = _source_report(first_path, current, all_cases[:53])
    first_hash = hashlib.sha256(first_path.read_bytes()).hexdigest()
    failure_path = tmp_path / "failed-n25.json"
    failed = _failed_attempt(failure_path, current)
    failed_hash = hashlib.sha256(failure_path.read_bytes()).hexdigest()
    before_cases = [_compact(row) for row in source["models"][0]["cases"]]
    before_cases.append(_compact(failed["models"][0]["cases"][0]))
    total = source["models"][0]["known_estimated_cost_usd"]
    report_parts = [
        {"path": str(first_path), "sha256": first_hash},
        {"path": str(failure_path), "sha256": failed_hash},
    ]
    identity = _identity(runs, tmp_path / "snapshot")
    encoded_identity = json.dumps(
        identity, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode()
    state = {
        "identity": identity,
        "identity_hash": hashlib.sha256(encoded_identity).hexdigest(),
        "budget_usd": 3.0,
        "known_spend_usd": total,
        "spent_unknown": False,
        "status": "stopped_provider_error",
        "active_run_id": None,
        "completed_runs": {
            current["run_id"]: {
                "run_id": current["run_id"],
                "identity": current["identity"],
                "known_estimated_cost_usd": total,
                "spent_unknown": False,
                "cases": before_cases,
                "complete": False,
                "stopped_reason": "provider_error",
                "summary": {
                    "run_id": current["run_id"],
                    "report_path": str(failure_path),
                    "report_sha256": failed_hash,
                    "report_parts": report_parts,
                    "run_status": "stopped",
                    "case_count": 54,
                    "expected_case_count": 58,
                    "complete": False,
                    "stopped_reason": "provider_error",
                    "known_estimated_cost_usd": total,
                    "spent_unknown": False,
                },
            }
        },
    }
    state_path = tmp_path / "campaign.json"
    _write_private(state_path, state)
    return state, runs, all_cases, state_path, first_path, failure_path


def _invoke(runs: list[dict], cases: list[dict], state_path: Path, failed: Path, *, apply: bool):
    return rearm_unstarted_case(
        state_path=state_path,
        failed_report_path=failed,
        expected_state_sha256=hashlib.sha256(state_path.read_bytes()).hexdigest(),
        expected_report_sha256=hashlib.sha256(failed.read_bytes()).hexdigest(),
        runs=runs,
        cases=cases,
        apply=apply,
    )


def test_rearm_archives_zero_start_n25_then_stub_resumes_five_and_58(tmp_path, monkeypatch) -> None:
    state, runs, cases, state_path, first, failed = _campaign(tmp_path)
    before_state = state_path.read_bytes()
    before_first = hashlib.sha256(first.read_bytes()).hexdigest()
    before_failed = hashlib.sha256(failed.read_bytes()).hexdigest()
    preview = _invoke(runs, cases, state_path, failed, apply=False)
    assert preview["remaining_case_ids"] == _MISSING
    assert state_path.read_bytes() == before_state and not Path(preview["backup_path"]).exists()
    applied = _invoke(runs, cases, state_path, failed, apply=True)
    assert (
        hashlib.sha256(Path(applied["backup_path"]).read_bytes()).hexdigest()
        == applied["source_checkpoint_sha256"]
    )
    assert stat.S_IMODE(Path(applied["backup_path"]).stat().st_mode) == 0o600
    updated = json.loads(state_path.read_text())
    slot = updated["completed_runs"][runs[0]["run_id"]]
    assert len(slot["cases"]) == 53 and slot["cases"][-1]["case_id"] == "N24"
    assert slot["known_estimated_cost_usd"] == pytest.approx(_KNOWN_SOURCE_COST)
    assert slot["summary"]["report_parts"] == [{"path": str(first), "sha256": before_first}]
    assert slot["archived_unstarted_attempts"][0]["attempt_report_sha256"] == before_failed
    assert hashlib.sha256(first.read_bytes()).hexdigest() == before_first
    assert hashlib.sha256(failed.read_bytes()).hexdigest() == before_failed

    calls = []

    def provider_stub(**kwargs):
        selected = kwargs["cases"]
        run_identity = kwargs["run_identity"]
        calls.append((run_identity["run_id"], [case["id"] for case in selected]))
        boundary_ids = {"es_card_conflicting_context", "en_private_context_override"}
        rows = []
        unit_cost = 0.001
        for case in selected:
            if case["id"] in boundary_ids:
                rows.append(_boundary(case["id"], run_identity))
            else:
                rows.append(_completed_row(case, run_identity, unit_cost))
        total = sum(row.get("estimated_cost_usd") or 0 for row in rows)
        return {
            "output_path": str(tmp_path / f"{run_identity['run_id']}-not-written.json"),
            "run_status": "completed",
            "run_identity": run_identity,
            "data_version": run_identity["data_version"],
            "semantic_version": run_identity["semantic_version"],
            "candidate_models": [run_identity["candidate"]],
            "probe_only": False,
            "estimated_cost_usd": total,
            "models": [
                {
                    "candidate": run_identity["candidate"],
                    "model": run_identity["model"],
                    "run_identity": run_identity,
                    "spent_unknown": False,
                    "estimated_cost_usd": total,
                    "known_estimated_cost_usd": total,
                    "quality_summary": {
                        "human_review_pending_case_count": sum(
                            row.get("quality", {}).get("requires_blinded_human_rubric") is True
                            for row in rows
                        ),
                        "critical_failure_gate": "pending blinded owner review of every rubric item",
                    },
                    "cases": rows,
                }
            ],
        }

    monkeypatch.setattr(campaign, "_live_provider_run", provider_stub)
    identity = updated["identity"]
    resumed = campaign.run_campaign(
        runs=runs,
        cases=cases,
        budget_usd=3.0,
        snapshot_root=Path(identity["snapshot_root"]),
        prices={key: tuple(value) for key, value in identity["prices"].items()},
        expected_versions=identity["expected_versions"],
        state_path=state_path,
        output_dir=tmp_path / "reports",
        resume=True,
    )
    assert [len(ids) for _, ids in calls] == [5, 58]
    assert calls[0][1] == _MISSING and "N24" not in calls[0][1]
    assert calls[1][1] == [case["id"] for case in cases]
    assert resumed["status"] == "completed"
    completed = json.loads(state_path.read_text())["completed_runs"][runs[0]["run_id"]]
    assert completed["archived_unstarted_attempts"][0]["attempt_report_sha256"] == before_failed
    composite = json.loads(Path(completed["summary"]["report_path"]).read_text())
    rows = composite["models"][0]["cases"]
    assert len(rows) == len({row["case_id"] for row in rows}) == 58
    assert sum(row["case_id"] == "N24" for row in rows) == 1
    assert composite["models"][0]["terminal_error_count"] == 1
    assert composite["models"][0]["stopped_reason"] is None
    assert composite["models"][0]["quality_summary"]["critical_failure_gate"] == (
        "pending blinded owner review of every rubric item"
    )
    assert completed["summary"]["quality_summary"] == composite["models"][0]["quality_summary"]
    assert completed["summary"]["quality_summary_scope"] == "full_case_set"
    assert completed["summary"]["quality_summary_case_count"] == 58
    latest_part = json.loads(Path(completed["summary"]["report_parts"][-1]["path"]).read_text())
    assert completed["summary"]["quality_summary"]["human_review_pending_case_count"] == 55
    assert (
        completed["summary"]["quality_summary"]["human_review_pending_case_count"]
        > latest_part["models"][0]["quality_summary"]["human_review_pending_case_count"]
    )


def test_partial_campaign_summary_labels_latest_part_scope_and_count(tmp_path, monkeypatch) -> None:
    cases = _stage1_cases()[:3]
    run = _runs(cases)[0]
    calls = []

    def provider_stub(**kwargs):
        selected = kwargs["cases"]
        identity = kwargs["run_identity"]
        calls.append([case["id"] for case in selected])
        row = _completed_row(selected[0], identity, 0.001)
        return {
            "output_path": str(tmp_path / f"not-written-{len(calls)}.json"),
            "run_status": "stopped",
            "run_identity": identity,
            "data_version": identity["data_version"],
            "semantic_version": identity["semantic_version"],
            "candidate_models": [identity["candidate"]],
            "probe_only": False,
            "estimated_cost_usd": 0.001,
            "models": [
                {
                    "candidate": identity["candidate"],
                    "model": identity["model"],
                    "run_identity": identity,
                    "spent_unknown": False,
                    "estimated_cost_usd": 0.001,
                    "known_estimated_cost_usd": 0.001,
                    "quality_summary": {
                        "human_review_pending_case_count": 1,
                        "critical_failure_gate": "pending blinded owner review of every rubric item",
                    },
                    "cases": [row],
                }
            ],
        }

    monkeypatch.setattr(campaign, "_live_provider_run", provider_stub)
    state_path = tmp_path / "campaign.json"
    output_dir = tmp_path / "reports"
    kwargs = {
        "runs": [run],
        "cases": cases,
        "budget_usd": 3.0,
        "snapshot_root": tmp_path / "snapshot",
        "prices": {run["candidate"]: (0.1, 0.5)},
        "expected_versions": {
            "data_version": run["identity"]["data_version"],
            "semantic_version": run["identity"]["semantic_version"],
        },
        "state_path": state_path,
        "output_dir": output_dir,
    }
    campaign.run_campaign(**kwargs)
    resumed = campaign.run_campaign(**kwargs, resume=True)
    summary = resumed["run_summaries"][0]
    assert calls == [[case["id"] for case in cases], [case["id"] for case in cases[1:]]]
    assert summary["case_count"] == 2
    assert summary["quality_summary_scope"] == "latest_report_part"
    assert summary["quality_summary_case_count"] == 1
    assert summary["quality_summary"]["human_review_pending_case_count"] == 1
    assert summary["quality_summary"]["critical_failure_gate"] == (
        "pending blinded owner review of every rubric item"
    )


@pytest.mark.parametrize(
    "mutation",
    [
        "provider_started",
        "positive_counter",
        "provider_events",
        "provider_event_count",
        "tool_events",
        "tool_event_count",
        "positive_turn_count",
        "positive_token_total",
        "positive_cost",
        "http",
        "request_id",
        "scored",
        "unknown_usage",
        "active",
        "stale_state_hash",
        "identity",
        "wrong_case",
        "duplicate",
        "source_hash",
    ],
)
def test_rearm_blocks_ambiguous_or_changed_evidence_without_writing(tmp_path, mutation) -> None:
    state, runs, cases, state_path, first, failed = _campaign(tmp_path)
    state_obj = json.loads(state_path.read_text())
    report = json.loads(failed.read_text())
    row = report["models"][0]["cases"][0]
    if mutation == "provider_started":
        row["provider_turn_started"] = True
    elif mutation == "positive_counter":
        row["provider_calls"] = 1
    elif mutation == "provider_events":
        row["provider_events"] = [{"type": "request_started"}]
    elif mutation == "provider_event_count":
        row["provider_event_count"] = 1
    elif mutation == "tool_events":
        row["tool_events"] = [{"type": "tool_started"}]
    elif mutation == "tool_event_count":
        row["tool_event_count"] = 1
    elif mutation == "positive_turn_count":
        row["turn_count"] = 1
    elif mutation == "positive_token_total":
        report["models"][0]["token_totals"]["input_tokens"] = 1
    elif mutation == "positive_cost":
        row["estimated_cost_usd"] = 0.001
    elif mutation == "http":
        row["error_metadata"]["http_status"] = 503
    elif mutation == "request_id":
        row["request_id"] = "request-known"
    elif mutation == "scored":
        row["quality"]["scored"] = True
    elif mutation == "unknown_usage":
        state_obj["spent_unknown"] = True
    elif mutation == "active":
        state_obj["active_run_id"] = runs[0]["run_id"]
    elif mutation == "identity":
        report["run_identity"]["prompt_content_hash"] = "tampered"
    elif mutation == "wrong_case":
        row["case_id"] = "N24"
    elif mutation == "duplicate":
        report["models"][0]["cases"].append(dict(row))
    else:
        first_report = json.loads(first.read_text())
        first_report["models"][0]["cases"].pop()
        _write_private(first, first_report)
    if mutation not in {"unknown_usage", "active"}:
        _write_private(failed, report)
        report_hash = hashlib.sha256(failed.read_bytes()).hexdigest()
        slot_summary = state_obj["completed_runs"][_TARGET]["summary"]
        slot_summary["report_sha256"] = report_hash
        slot_summary["report_parts"][1]["sha256"] = report_hash
    _write_private(state_path, state_obj)
    before_state = state_path.read_bytes()
    before_failed = failed.read_bytes()
    with pytest.raises(ValueError):
        if mutation == "stale_state_hash":
            rearm_unstarted_case(
                state_path=state_path,
                failed_report_path=failed,
                expected_state_sha256="0" * 64,
                expected_report_sha256=hashlib.sha256(failed.read_bytes()).hexdigest(),
                runs=runs,
                cases=cases,
                apply=True,
            )
        else:
            _invoke(runs, cases, state_path, failed, apply=True)
    assert state_path.read_bytes() == before_state
    assert failed.read_bytes() == before_failed
    assert not list(tmp_path.glob("campaign.json.before-unstarted-rearm-*"))
