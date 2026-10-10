"""Integration tests for campaign scheduling, resume, and global spend stops."""

import json
import stat
from pathlib import Path

import pytest

from src.conversational_analytics import evaluation_live_campaign as campaign


def _run(
    run_id: str,
    *,
    prompt_variant: str = "proposed",
    repetition: int = 1,
    case_ids: list[str] | None = None,
) -> dict:
    identity = {
        "run_id": run_id,
        "candidate": "gpt-6-luna@medium",
        "model": "gpt-6-luna",
        "reasoning_effort": "medium",
        "text_verbosity": "medium",
        "prompt_variant": prompt_variant,
        "prompt_content_hash": f"hash-{prompt_variant}",
        "repetition": repetition,
        "data_version": "data-v1",
        "semantic_version": "semantic-v1",
        "tool_spec_hash": "tools-v1",
        "limits": {"max_tool_calls": 8},
    }
    return {
        **identity,
        "run_id": run_id,
        "candidate": "gpt-6-luna@medium",
        "prompt": f"prompt {prompt_variant} rep {repetition}",
        "identity": identity,
        "identity_hash": f"identity-{run_id}-{prompt_variant}-{repetition}",
        "case_ids": list(case_ids or ["N01"]),
    }


def _case(case_id: str = "N01") -> dict:
    return {"id": case_id, "question": f"Pregunta {case_id}"}


def _complete_report(run_identity: dict, cases: list[dict], cost: float = 0.1) -> dict:
    return {
        "output_path": f"/private/{run_identity['run_id']}.json",
        "run_status": "completed",
        "models": [
            {
                "known_estimated_cost_usd": cost,
                "spent_unknown": False,
                "quality_summary": {"supported_passed": len(cases)},
                "cases": [
                    {
                        "case_id": item["id"],
                        "provider_turn_started": True,
                        "usage_complete": True,
                        "estimated_cost_usd": cost / len(cases),
                        "status": "supported",
                        "model_turn_completed": True,
                    }
                    for item in cases
                ],
            }
        ],
    }


def _invoke(monkeypatch, tmp_path: Path, runs: list[dict], fake, *, budget: float = 2.0, resume: bool = False):
    monkeypatch.setattr(campaign, "_live_provider_run", fake)
    return campaign.run_campaign(
        runs=runs,
        cases=[_case("N01"), _case("N02")],
        budget_usd=budget,
        snapshot_root=tmp_path / "snapshot",
        prices={"gpt-6-luna@medium": (0.1, 0.5)},
        expected_versions={"data_version": "data-v1", "semantic_version": "semantic-v1"},
        state_path=tmp_path / "campaign.json",
        output_dir=tmp_path / "runs",
        resume=resume,
    )


def test_distinct_prompt_and_luna_repetition_slots_each_reach_provider(monkeypatch, tmp_path: Path) -> None:
    runs = [
        _run("s1-current", prompt_variant="current"),
        _run("s1-proposed", prompt_variant="proposed"),
        _run("s3-luna-r1", repetition=1),
        _run("s3-luna-r2", repetition=2),
    ]
    seen = []

    def fake(**kwargs):
        seen.append(kwargs)
        return _complete_report(kwargs["run_identity"], kwargs["cases"])

    result = _invoke(monkeypatch, tmp_path, runs, fake)

    assert result["status"] == "completed"
    assert [call["run_identity"]["run_id"] for call in seen] == [run["run_id"] for run in runs]
    assert [call["run_identity"]["prompt_variant"] for call in seen[:2]] == ["current", "proposed"]
    assert [call["run_identity"]["repetition"] for call in seen[2:]] == [1, 2]
    assert len({call["run_identity"]["run_id"] for call in seen}) == 4


def test_campaign_stamps_exact_identity_on_private_source_report(monkeypatch, tmp_path: Path) -> None:
    run = _run("source-report-slot")
    source_report = tmp_path / "runs" / "provider-report.json"

    def fake(**kwargs):
        report = _complete_report(kwargs["run_identity"], kwargs["cases"])
        report["output_path"] = str(source_report)
        campaign._write_private_json(source_report, report)
        return report

    result = _invoke(monkeypatch, tmp_path, [run], fake)
    persisted = json.loads(source_report.read_text(encoding="utf-8"))

    assert result["status"] == "completed"
    assert persisted["run_identity_hash"] == run["identity_hash"]
    assert persisted["campaign_identity_hash"] == result["identity_hash"]
    assert stat.S_IMODE(source_report.stat().st_mode) == 0o600
    assert stat.S_IMODE(source_report.parent.stat().st_mode) == 0o700


def test_campaign_passes_remaining_budget_across_slots(monkeypatch, tmp_path: Path) -> None:
    runs = [_run("slot-1"), _run("slot-2", repetition=2)]
    budgets = []

    def fake(**kwargs):
        budgets.append(kwargs["budget_usd"])
        return _complete_report(kwargs["run_identity"], kwargs["cases"], cost=0.6)

    _invoke(monkeypatch, tmp_path, runs, fake, budget=1.0)

    assert budgets == [1.0, pytest.approx(0.4)]


def test_exact_resume_skips_only_completed_slot_and_continues_partial_slot(monkeypatch, tmp_path: Path) -> None:
    runs = [
        _run("completed-slot"),
        _run("partial-slot", repetition=2, case_ids=["N01", "N02"]),
    ]
    calls = []

    def first_attempt(**kwargs):
        run_id = kwargs["run_identity"]["run_id"]
        case_ids = [case["id"] for case in kwargs["cases"]]
        calls.append((run_id, case_ids))
        if run_id == "partial-slot":
            return {
                "output_path": "/private/partial.json",
                "run_status": "stopped",
                "models": [{
                    "known_estimated_cost_usd": 0.1,
                    "spent_unknown": False,
                    "quality_summary": {},
                    "cases": [{
                        "case_id": "N01", "provider_turn_started": True,
                        "usage_complete": True, "estimated_cost_usd": 0.1,
                        "status": "supported", "model_turn_completed": True,
                    }],
                }],
            }
        return _complete_report(kwargs["run_identity"], kwargs["cases"], cost=0.1)

    first_result = _invoke(monkeypatch, tmp_path, runs, first_attempt)
    assert first_result["status"] == "stopped_campaign_budget"

    def resumed(**kwargs):
        calls.append((kwargs["run_identity"]["run_id"], [case["id"] for case in kwargs["cases"]]))
        return _complete_report(kwargs["run_identity"], kwargs["cases"], cost=0.1)

    result = _invoke(monkeypatch, tmp_path, runs, resumed, resume=True)

    assert result["status"] == "completed"
    assert calls[0][0] == "completed-slot"
    assert calls[1] == ("partial-slot", ["N01", "N02"])
    assert calls[2] == ("partial-slot", ["N02"])


def test_identity_change_blocks_resume_without_provider_call(monkeypatch, tmp_path: Path) -> None:
    original = [_run("stable-slot")]
    calls = []

    def complete(**kwargs):
        calls.append(kwargs)
        return _complete_report(kwargs["run_identity"], kwargs["cases"])

    _invoke(monkeypatch, tmp_path, original, complete)
    changed = [_run("stable-slot")]
    changed[0]["prompt_content_hash"] = "changed-hash"
    changed[0]["identity"]["prompt_content_hash"] = "changed-hash"

    with pytest.raises(ValueError, match="identidad"):
        _invoke(monkeypatch, tmp_path, changed, complete, resume=True)

    assert len(calls) == 1


def test_interrupted_active_slot_blocks_resume_without_replay(monkeypatch, tmp_path: Path) -> None:
    runs = [_run("interrupted-slot")]
    calls = []

    def interrupt(**kwargs):
        calls.append(kwargs)
        raise RuntimeError("fake interruption")

    with pytest.raises(RuntimeError, match="fake interruption"):
        _invoke(monkeypatch, tmp_path, runs, interrupt)

    with pytest.raises(ValueError, match="interrumpida"):
        _invoke(monkeypatch, tmp_path, runs, interrupt, resume=True)

    assert len(calls) == 1
    saved = json.loads((tmp_path / "campaign.json").read_text(encoding="utf-8"))
    assert saved["spent_unknown"] is True


def test_unknown_spend_retains_lower_bound_and_blocks_next_slot_and_resume(monkeypatch, tmp_path: Path) -> None:
    runs = [_run("unknown-slot"), _run("must-not-run", repetition=2)]
    calls = []

    def unknown(**kwargs):
        calls.append(kwargs["run_identity"]["run_id"])
        return {
            "output_path": "/private/unknown.json",
            "run_status": "stopped",
            "models": [{
                "known_estimated_cost_usd": 0.25,
                "spent_unknown": True,
                "quality_summary": {},
                "cases": [{
                    "case_id": "N01", "provider_turn_started": True,
                    "usage_complete": False, "estimated_cost_usd": None,
                    "known_estimated_cost_lower_bound_usd": 0.25,
                    "status": "provider_error", "model_turn_completed": False,
                }],
            }],
        }

    result = _invoke(monkeypatch, tmp_path, runs, unknown)

    assert calls == ["unknown-slot"]
    assert result["known_spend_usd"] == 0.25
    assert result["spent_unknown"] is True
    assert result["total_spend_usd"] is None
    assert result["status"] == "stopped_unknown_spend"
    with pytest.raises(ValueError, match="desconocido"):
        _invoke(monkeypatch, tmp_path, runs, unknown, resume=True)
    assert calls == ["unknown-slot"]


def test_partial_budget_response_is_not_completed_and_does_not_start_next_slot(monkeypatch, tmp_path: Path) -> None:
    runs = [
        _run("partial-slot", case_ids=["N01", "N02"]),
        _run("must-not-run", repetition=2),
    ]
    calls = []

    def partial(**kwargs):
        calls.append(kwargs["run_identity"]["run_id"])
        return {
            "output_path": "/private/partial.json",
            "run_status": "stopped",
            "models": [{
                "known_estimated_cost_usd": 0.1,
                "spent_unknown": False,
                "quality_summary": {},
                "cases": [{
                    "case_id": "N01", "provider_turn_started": True,
                    "usage_complete": True, "estimated_cost_usd": 0.1,
                    "status": "supported", "model_turn_completed": True,
                }],
            }],
        }

    result = _invoke(monkeypatch, tmp_path, runs, partial)

    assert calls == ["partial-slot"]
    assert result["status"] == "stopped_campaign_budget"
    assert result["run_summaries"][0]["complete"] is False
    assert result["run_summaries"][0]["case_count"] == 1
    assert result["run_summaries"][0]["expected_case_count"] == 2
