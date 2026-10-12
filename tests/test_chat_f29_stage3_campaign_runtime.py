from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from src.conversational_analytics import evaluation_live_campaign as campaign

ROOT = Path(__file__).resolve().parents[1]


def _stage3_plan():
    fixture = json.loads((ROOT / "tests/fixtures/chat_evals/business_proposed.json").read_text())
    cases = fixture["cases"]
    case_ids = [case["id"] for case in cases]
    identity = {
        "run_id": "stage3-fake",
        "case_ids": case_ids,
        "scope": "30-cases-34-messages",
        "coverage_campaign_sha256": "a" * 64,
    }
    digest = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()
    override = {
        "basis": "f2_9_stage3_projected_usage_not_hard_cap",
        "planned_request_count": 34,
        "planned_message_count": 34,
        "input_tokens_per_turn": 83_500,
        "output_tokens_per_turn": 375,
        "planned_batch_estimated_reservation_usd": 7.2,
        "campaign_sha256": "a" * 64,
    }
    run = {
        "run_id": "stage3-fake",
        "candidate": "gpt-6.1-sol@low",
        "case_ids": case_ids,
        "identity": identity,
        "identity_hash": digest,
        "prompt": "fake approved-content pin",
        "limits": {"max_tool_calls": 16},
        "text_verbosity": "medium",
    }
    return cases, run, override


def _fake_report(kwargs, case_ids, *, unknown=False, run_status="completed"):
    rows = [
        {
            "case_id": case_id,
            "provider_turn_started": True,
            "usage_complete": not unknown,
            "estimated_cost_usd": None if unknown else 0.01,
            "known_estimated_cost_lower_bound_usd": 0.01 if unknown else None,
            "status": "provider_error" if unknown else "supported",
            "model_turn_completed": False if unknown else True,
        }
        for case_id in case_ids
    ]
    return {
        "output_path": "",
        "run_status": "stopped" if unknown else run_status,
        "models": [
            {
                "known_estimated_cost_usd": 0.01 * len(rows),
                "spent_unknown": unknown,
                "quality_summary": {},
                "cases": rows,
            }
        ],
    }


def _invoke(tmp_path, monkeypatch, fake, *, resume=False):
    cases, run, override = _stage3_plan()
    monkeypatch.setattr(campaign, "_live_provider_run", fake)
    return campaign.run_campaign(
        runs=[run],
        cases=cases,
        budget_usd=8.0,
        snapshot_root=tmp_path / "snapshot",
        prices={"gpt-6.1-sol@low": (2.5, 10.0)},
        expected_versions={"data_version": "d1", "semantic_version": "s1"},
        state_path=tmp_path / "campaign.json",
        output_dir=tmp_path / "runs",
        reservation_assumption_override=override,
        resume=resume,
    )


def test_stage3_30_cases_34_messages_resumes_at_n24_with_exact_identity(tmp_path, monkeypatch):
    calls = []

    def first(**kwargs):
        ids = [case["id"] for case in kwargs["cases"]]
        calls.append(ids)
        return _fake_report(kwargs, ids[:23], run_status="stopped")

    first_result = _invoke(tmp_path, monkeypatch, first)
    assert first_result["status"] == "stopped_campaign_budget"

    def resumed(**kwargs):
        ids = [case["id"] for case in kwargs["cases"]]
        calls.append(ids)
        return _fake_report(kwargs, ids)

    result = _invoke(tmp_path, monkeypatch, resumed, resume=True)
    assert result["status"] == "completed"
    assert len(calls[0]) == 30 and len(calls[1]) == 7
    assert calls[1][0] == "N24"
    assert result["known_spend_usd"] < 8.0


def test_stage3_unknown_prior_spend_stops_and_cannot_resume(tmp_path, monkeypatch):
    calls = []

    def unknown(**kwargs):
        ids = [case["id"] for case in kwargs["cases"]]
        calls.append(ids)
        return _fake_report(kwargs, ids[:1], unknown=True)

    result = _invoke(tmp_path, monkeypatch, unknown)
    assert result["status"] == "stopped_unknown_spend"
    with pytest.raises(ValueError, match="desconocido"):
        _invoke(tmp_path, monkeypatch, unknown, resume=True)
    assert len(calls) == 1
