"""Integration tests for campaign scheduling, resume, and global spend stops."""

import json
import stat
from pathlib import Path

import pytest

from src.conversational_analytics import evaluation_live
from src.conversational_analytics import evaluation_live_campaign as campaign
from src.conversational_analytics.config import ChatConfig
from src.conversational_analytics.evaluation_live_reservation import (
    case_reservation_cost,
    reservation_assumption,
)


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


def test_campaign_passes_identity_text_verbosity_to_runtime_override(monkeypatch, tmp_path: Path) -> None:
    run = _run("verbosity-slot")
    run["text_verbosity"] = "high"
    run["identity"]["text_verbosity"] = "high"
    seen = []

    def fake(**kwargs):
        seen.append(kwargs)
        return _complete_report(kwargs["run_identity"], kwargs["cases"])

    _invoke(monkeypatch, tmp_path, [run], fake)

    assert seen[0]["text_verbosity_override"] == "high"
    assert seen[0]["text_verbosity_override"] == seen[0]["run_identity"]["text_verbosity"]


def test_empirical_campaign_rejects_wrong_total_slots_before_state_or_provider(monkeypatch, tmp_path: Path) -> None:
    run = _run("wrong-reservation-slot-count")
    run["case_ids"] = ["N01"]
    reservation = {"planned_request_count": 29}
    calls = []
    monkeypatch.setattr(campaign, "_live_provider_run", lambda **kwargs: calls.append(kwargs))

    with pytest.raises(ValueError, match="total de turnos planificados"):
        campaign.run_campaign(
            runs=[run], cases=[_case()], budget_usd=1.0,
            snapshot_root=tmp_path / "snapshot",
            prices={"gpt-6-luna@medium": (0.1, 0.5)},
            expected_versions={"data_version": "data-v1", "semantic_version": "semantic-v1"},
            state_path=tmp_path / "campaign.json", output_dir=tmp_path / "runs",
            reservation_assumption_override=reservation,
        )
    assert calls == []
    assert not (tmp_path / "campaign.json").exists()


@pytest.mark.parametrize("estimate_index", [0, 1], ids=["approved-low", "approved-upper"])
def test_scheduler_completes_all_29_slots_within_remaining_budget(
    monkeypatch, tmp_path: Path, estimate_index: int
) -> None:
    remaining = 5.725855625
    low_range, medium_range = (2.045324, 2.345324), (2.345324, 3.095324)
    low_spend = low_range[estimate_index] * 14 / 15
    medium_spend = medium_range[estimate_index]
    low_ids = [f"L{index:02}" for index in range(14)]
    medium_ids = [f"M{index:02}" for index in range(15)]
    low, medium = _run("final-low", case_ids=low_ids), _run("final-medium", case_ids=medium_ids)
    for run, candidate, model, effort in (
        (low, "gpt-6.1-sol@low", "gpt-6.1-sol", "low"),
        (medium, "gpt-6.1-sol@medium", "gpt-6.1-sol", "medium"),
    ):
        run["candidate"] = run["identity"]["candidate"] = candidate
        run["model"] = run["identity"]["model"] = model
        run["reasoning_effort"] = run["identity"]["reasoning_effort"] = effort
    reservation = {
        "basis": "f2_9_empirical_pilot_estimate_not_hard_cap",
        "input_tokens_per_turn": 68_570,
        "output_tokens_per_turn": 2_073,
        "historical_sample_count": 30,
        "historical_candidate_counts": {
            "gpt-6-luna@medium": 14, "gpt-6-luna@max": 15, "gpt-6.1-sol@low": 1,
        },
        "planned_request_count": 29,
        "safety_margin_fraction": 0.35,
        "per_case_estimated_reservation_usd": 0.192155,
        "planned_batch_estimated_reservation_usd": 5.572495,
        "budget_guaranteed": False,
    }
    calls = []
    observed = []

    def fake_live(**kwargs):
        calls.append(kwargs)
        candidate = kwargs["models"][0]
        config = ChatConfig(
            provider="openai", model="gpt-6.1-sol",
            estimated_input_cost_per_million=2.0,
            estimated_output_cost_per_million=10.0,
            cache_write_input_multiplier=1.25,
            long_context_threshold_input_tokens=272_000,
            long_context_input_multiplier=2.0,
            long_context_output_multiplier=1.5,
        )
        assumption = reservation_assumption(config, kwargs["reservation_assumption_override"])
        total_reservation = sum(
            case_reservation_cost(config, assumption, 1) for _ in kwargs["cases"]
        )
        observed.append((candidate, len(kwargs["cases"]), kwargs["budget_usd"], total_reservation))
        actual_total = low_spend if candidate.endswith("@low") else medium_spend
        per_case = actual_total / len(kwargs["cases"])
        return {
            "output_path": f"/private/{candidate}.json", "run_status": "completed",
            "models": [{
                "known_estimated_cost_usd": actual_total, "spent_unknown": False,
                "quality_summary": {},
                "cases": [{
                    "case_id": case["id"], "provider_turn_started": True,
                    "usage_complete": True, "estimated_cost_usd": per_case,
                    "status": "supported", "model_turn_completed": True,
                } for case in kwargs["cases"]],
            }],
        }

    monkeypatch.setattr(campaign, "_live_provider_run", fake_live)
    result = campaign.run_campaign(
        runs=[low, medium],
        cases=[_case(case_id) for case_id in low_ids + medium_ids],
        budget_usd=remaining,
        snapshot_root=tmp_path / "snapshot",
        prices={"gpt-6.1-sol@low": (2.0, 10.0), "gpt-6.1-sol@medium": (2.0, 10.0)},
        expected_versions={"data_version": "data-v1", "semantic_version": "semantic-v1"},
        state_path=tmp_path / f"scenario-{estimate_index}.json",
        output_dir=tmp_path / f"runs-{estimate_index}",
        reservation_assumption_override=reservation,
    )

    assert result["status"] == "completed"
    assert [row[1] for row in observed] == [14, 15]
    assert observed[0][3] + observed[1][3] == pytest.approx(5.572495)
    assert result["known_spend_usd"] == pytest.approx(low_spend + medium_spend)
    assert result["known_spend_usd"] <= remaining
    state = json.loads((tmp_path / f"scenario-{estimate_index}.json").read_text())
    assert state["identity"]["reservation_assumption_override"] == reservation
    assert all(call["reservation_assumption_override"] == reservation for call in calls)


def test_live_runner_applies_identity_verbosity_to_runtime_config(monkeypatch, tmp_path: Path) -> None:
    seen = []
    replace_config = evaluation_live.replace

    def capture_replace(config, **changes):
        if "text_verbosity" in changes:
            seen.append((config.text_verbosity, changes["text_verbosity"]))
        return replace_config(config, **changes)

    class StopAfterConfig(Exception):
        pass

    def stop_before_snapshot(_path):
        raise StopAfterConfig

    monkeypatch.setattr(evaluation_live, "replace", capture_replace)
    monkeypatch.setattr(evaluation_live, "Snapshot", stop_before_snapshot)
    monkeypatch.setattr(ChatConfig, "from_env", classmethod(lambda cls: cls(text_verbosity="low")))

    with pytest.raises(StopAfterConfig):
        evaluation_live._live_provider_run(
            cases=[_case()],
            models=["gpt-6-luna@medium"],
            budget_usd=1.0,
            snapshot_root=tmp_path / "unused-snapshot",
            prices={"gpt-6-luna@medium": (0.1, 0.5)},
            probe_only=False,
            output_dir=tmp_path / "unused-output",
            expected_versions={"data_version": "data-v1", "semantic_version": "semantic-v1"},
            run_identity={"text_verbosity": "high"},
            text_verbosity_override="high",
        )

    assert seen == [("low", "high")]


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
