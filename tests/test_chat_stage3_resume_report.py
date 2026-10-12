"""Detailed report persistence and F2.9 campaign resume integration."""

from __future__ import annotations

import hashlib
import json
import stat
from pathlib import Path

import pytest

from scripts.chat.export_stage3_review import build_dataset
from src.conversational_analytics import evaluation_live_campaign as campaign
from src.conversational_analytics.evaluation_live_campaign_reports import _canonical_hash


def test_stage3_resume_consolidates_private_details_for_all_cases_and_exports(
    monkeypatch, tmp_path: Path
) -> None:
    fixture_path = Path(__file__).resolve().parents[1] / "tests/fixtures/chat_evals/business_proposed.json"
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
    fixture_sha = hashlib.sha256(fixture_path.read_bytes()).hexdigest()
    case_ids = [case["id"] for case in fixture["cases"]]
    coverage_sha = "c" * 64
    coverage_identity = {
        "stage": "F2.9-stage-3",
        "candidate": "gpt-6.1-sol@low",
        "model": "gpt-6.1-sol",
        "reasoning_effort": "low",
        "text_verbosity": "medium",
        "case_fixture_sha256": fixture_sha,
        "profile_sha256": "a" * 64,
        "snapshot_data_version": "data-v1",
        "snapshot_semantic_version": "semantic-v1",
        "coverage_campaign_sha256": coverage_sha,
    }
    identity = dict(coverage_identity)
    run = {
        "run_id": "stage3-resume",
        "candidate": "gpt-6.1-sol@low",
        "model": "gpt-6.1-sol",
        "reasoning_effort": "low",
        "text_verbosity": "medium",
        "prompt": "frozen prompt",
        "limits": {"max_tool_calls": 16, "max_message_chars": 8000},
        "identity": identity,
        "identity_hash": _canonical_hash(identity),
        "case_ids": case_ids,
    }
    reservation = {
        "basis": "f2_9_stage3_projected_usage_not_hard_cap",
        "planned_request_count": 34,
        "input_tokens_per_turn": 83_528,
        "output_tokens_per_turn": 375,
        "planned_batch_estimated_reservation_usd": 7.22738,
        "campaign_sha256": coverage_sha,
    }
    expected_versions = {"data_version": "data-v1", "semantic_version": "semantic-v1"}
    report_paths: list[Path] = []
    detail_paths: list[Path] = []
    calls: list[list[str]] = []

    def fake_provider(**kwargs):
        selected = kwargs["cases"]
        ids = [case["id"] for case in selected]
        calls.append(ids)
        if len(calls) == 1:
            selected = selected[:23]
            status = "stopped"
            ids = [case["id"] for case in selected]
        else:
            status = "completed"
        model_cases = []
        for case in selected:
            turns = case["turns"]
            model_cases.append({
                "case_id": case["id"],
                "turn_responses": [
                    f"synthetic answer {case['id']} turn {index}"
                    for index, _ in enumerate(turns, 1)
                ],
                "model_turn_completed": True,
                "provider_turn_started": True,
                "usage_complete": True,
                "input_tokens": 100 * len(turns),
                "output_tokens": 10 * len(turns),
                "turns": len(turns),
                "turn_usage": [
                    {"input_tokens": 100, "output_tokens": 10, "usage_complete": True}
                    for _ in turns
                ],
                "estimated_cost_usd": 0.1,
                "known_estimated_cost_lower_bound_usd": 0.1,
                "status": "supported",
                "latency_seconds": 0.2,
                "quality": {"scored": False, "requires_blinded_human_rubric": True},
            })
        run_dir = kwargs["output_dir"]
        run_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        report_path = run_dir / f"fragment-{len(calls)}.json"
        detail_path = run_dir / f"fragment-{len(calls)}.cases.json"
        model = {
            "candidate_id": "gpt-6.1-sol@low@medium",
            "model": "gpt-6.1-sol",
            "reasoning_effort": "low",
            "text_verbosity": "medium",
            "cases": model_cases,
            "known_estimated_cost_usd": 0.1 * len(model_cases),
            "estimated_cost_usd": 0.1 * len(model_cases),
            "spent_unknown": False,
            "quality_summary": {},
        }
        report = {
            "mode": "live-evaluation",
            "probe_only": False,
            "run_status": status,
            "case_count": len(model_cases),
            "run_identity": identity,
            "run_identity_hash": run["identity_hash"],
            "campaign_identity_hash": kwargs["campaign_identity_hash"],
            "data_version": "data-v1",
            "semantic_version": "semantic-v1",
            "output_path": str(report_path),
            "case_checkpoint_path": str(detail_path),
            "models": [model],
        }
        campaign._write_private_json(report_path, report)
        campaign._write_private_json(detail_path, report)
        report_paths.append(report_path)
        detail_paths.append(detail_path)
        return report

    monkeypatch.setattr(campaign, "_live_provider_run", fake_provider)
    args = {
        "runs": [run],
        "cases": fixture["cases"],
        "budget_usd": 8.0,
        "snapshot_root": tmp_path / "snapshot",
        "prices": {"gpt-6.1-sol@low": (2.0, 10.0)},
        "expected_versions": expected_versions,
        "state_path": tmp_path / "campaign.json",
        "output_dir": tmp_path / "private-runs",
        "reservation_assumption_override": reservation,
    }
    first = campaign.run_campaign(**args)
    assert first["status"] == "stopped_campaign_budget"
    original_report_hash = hashlib.sha256(report_paths[0].read_bytes()).hexdigest()
    original_detail_hash = hashlib.sha256(detail_paths[0].read_bytes()).hexdigest()

    final = campaign.run_campaign(**args, resume=True)
    assert final["status"] == "completed"
    assert calls == [case_ids, case_ids[23:]]
    assert report_paths[0].read_bytes() and detail_paths[0].read_bytes()
    assert hashlib.sha256(report_paths[0].read_bytes()).hexdigest() == original_report_hash
    assert hashlib.sha256(detail_paths[0].read_bytes()).hexdigest() == original_detail_hash

    summary = final["run_summaries"][0]
    consolidated_path = Path(summary["report_path"])
    consolidated = json.loads(consolidated_path.read_text(encoding="utf-8"))
    assert hashlib.sha256(consolidated_path.read_bytes()).hexdigest() == summary["report_sha256"]
    assert [case["case_id"] for case in consolidated["models"][0]["cases"]] == case_ids
    assert consolidated["models"][0]["candidate_id"] == "gpt-6.1-sol@low@medium"
    assert "candidate" not in consolidated["models"][0]
    assert sum(case["input_tokens"] for case in consolidated["models"][0]["cases"]) == 3_400
    assert consolidated["models"][0]["known_estimated_cost_usd"] == pytest.approx(3.0)
    assert stat.S_IMODE(consolidated_path.stat().st_mode) == 0o600
    assert len(consolidated["source_report_fragments"]) == 2
    assert consolidated["mode"] == "live-evaluation"
    assert consolidated["probe_only"] is False
    assert consolidated["run_identity"] == coverage_identity
    assert consolidated["run_identity_hash"] == _canonical_hash(coverage_identity)
    assert consolidated["campaign_identity_hash"] == final["identity_hash"]
    assert consolidated["data_version"] == "data-v1"
    assert consolidated["semantic_version"] == "semantic-v1"
    for row, original in zip(consolidated["models"][0]["cases"], fixture["cases"], strict=True):
        assert len(row["turn_responses"]) == len(original["turns"])
    assert len(consolidated["models"][0]["cases"][23]["turn_responses"]) == 3

    coverage = {
        "kind": "f2_9_stage3_derived_coverage",
        "provider_calls": 0,
        "campaign_sha256": coverage_sha,
        "campaign_identity": coverage_identity,
        "pins": {"data_version": "data-v1", "semantic_version": "semantic-v1"},
        "cases": [
            {
                "case_id": case_id,
                "status": "supported",
                "derived_expectations": [],
                "derived_calculations": [],
            }
            for case_id in case_ids
        ],
    }
    dataset, _ = build_dataset(coverage, consolidated, fixture, fixture_sha)
    assert len(dataset["questions"]) == 30
    assert dataset["available_count"] == 30

    before_replay = consolidated_path.read_bytes()
    replay = campaign.run_campaign(**args, resume=True)
    assert replay["run_summaries"][0]["report_path"] == str(consolidated_path)
    assert consolidated_path.read_bytes() == before_replay
    assert len(calls) == 2

    changed = dict(run)
    changed["identity"] = {**identity, "profile_sha256": "b" * 64}
    changed["identity_hash"] = _canonical_hash(changed["identity"])
    changed_args = {**args, "runs": [changed]}
    with pytest.raises(ValueError, match="identidad"):
        campaign.run_campaign(**changed_args, resume=True)
    assert consolidated_path.read_bytes() == before_replay
    assert len(calls) == 2
