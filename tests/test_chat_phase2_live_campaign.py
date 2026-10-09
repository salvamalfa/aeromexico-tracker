"""Integration tests for campaign scheduling, resume, and global spend stops."""

import json
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
        "run_identity": run_identity,
        "run_status": "completed",
        "estimated_cost_usd": cost,
        "known_estimated_cost_usd": cost,
        "models": [
            {
                "candidate": run_identity["candidate"],
                "model": run_identity["model"],
                "run_identity": run_identity,
                "known_estimated_cost_usd": cost,
                "estimated_cost_usd": cost,
                "spent_unknown": False,
                "quality_summary": {"supported_passed": len(cases)},
                "cases": [
                    {
                        "case_id": item["id"],
                        "run_identity": run_identity,
                        "provider_turn_started": True,
                        "usage_complete": True,
                        "estimated_cost_usd": cost / len(cases),
                        "status": "supported",
                        "model_turn_completed": True,
                        "input_tokens": 5,
                        "output_tokens": 2,
                        "latency_seconds": 0.5,
                        "turn_count": 1,
                        "quality": {"scored": False},
                    }
                    for item in cases
                ],
            }
        ],
    }


def _invoke(
    monkeypatch,
    tmp_path: Path,
    runs: list[dict],
    fake,
    *,
    budget: float = 2.0,
    resume: bool = False,
    cases: list[dict] | None = None,
):
    monkeypatch.setattr(campaign, "_live_provider_run", fake)
    return campaign.run_campaign(
        runs=runs,
        cases=cases or [_case("N01"), _case("N02")],
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


def test_campaign_passes_remaining_budget_across_slots(monkeypatch, tmp_path: Path) -> None:
    runs = [_run("slot-1"), _run("slot-2", repetition=2)]
    budgets = []

    def fake(**kwargs):
        budgets.append(kwargs["budget_usd"])
        return _complete_report(kwargs["run_identity"], kwargs["cases"], cost=0.6)

    _invoke(monkeypatch, tmp_path, runs, fake, budget=1.0)

    assert budgets == [1.0, pytest.approx(0.4)]


def test_exact_resume_skips_only_completed_slot_and_continues_partial_slot(
    monkeypatch, tmp_path: Path
) -> None:
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
                "run_identity": kwargs["run_identity"],
                "run_status": "stopped",
                "models": [
                    {
                        "candidate": kwargs["run_identity"]["candidate"],
                        "model": kwargs["run_identity"]["model"],
                        "run_identity": kwargs["run_identity"],
                        "known_estimated_cost_usd": 0.1,
                        "estimated_cost_usd": 0.1,
                        "spent_unknown": False,
                        "quality_summary": {},
                        "cases": [
                            {
                                "case_id": "N01",
                                "run_identity": kwargs["run_identity"],
                                "provider_turn_started": True,
                                "usage_complete": True,
                                "estimated_cost_usd": 0.1,
                                "status": "supported",
                                "model_turn_completed": True,
                            }
                        ],
                    }
                ],
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


def test_unknown_spend_retains_lower_bound_and_blocks_next_slot_and_resume(
    monkeypatch, tmp_path: Path
) -> None:
    runs = [_run("unknown-slot"), _run("must-not-run", repetition=2)]
    calls = []

    def unknown(**kwargs):
        calls.append(kwargs["run_identity"]["run_id"])
        return {
            "output_path": "/private/unknown.json",
            "run_status": "stopped",
            "models": [
                {
                    "known_estimated_cost_usd": 0.25,
                    "spent_unknown": True,
                    "quality_summary": {},
                    "cases": [
                        {
                            "case_id": "N01",
                            "provider_turn_started": True,
                            "usage_complete": False,
                            "estimated_cost_usd": None,
                            "known_estimated_cost_lower_bound_usd": 0.25,
                            "status": "provider_error",
                            "model_turn_completed": False,
                        }
                    ],
                }
            ],
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


def test_partial_budget_response_is_not_completed_and_does_not_start_next_slot(
    monkeypatch, tmp_path: Path
) -> None:
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
            "models": [
                {
                    "known_estimated_cost_usd": 0.1,
                    "spent_unknown": False,
                    "quality_summary": {},
                    "cases": [
                        {
                            "case_id": "N01",
                            "provider_turn_started": True,
                            "usage_complete": True,
                            "estimated_cost_usd": 0.1,
                            "status": "supported",
                            "model_turn_completed": True,
                        }
                    ],
                }
            ],
        }

    result = _invoke(monkeypatch, tmp_path, runs, partial)

    assert calls == ["partial-slot"]
    assert result["status"] == "stopped_campaign_budget"
    assert result["run_summaries"][0]["complete"] is False
    assert result["run_summaries"][0]["case_count"] == 1
    assert result["run_summaries"][0]["expected_case_count"] == 2


def _boundary_case(case_id: str, context: dict) -> dict:
    return {"id": case_id, "question": "Prueba de contexto inválido", "context": context}


def _boundary_rejection(case_id: str) -> dict:
    return {
        "case_id": case_id,
        "status": "application_context_rejected",
        "provider_calls": 0,
        "provider_request_count": 0,
        "provider_turn_started": False,
        "model_turn_completed": False,
        "application_boundary_test_completed": True,
        "usage_complete": None,
        "estimated_cost_usd": None,
        "known_estimated_cost_lower_bound_usd": None,
        "quality": {"scored": False, "not_scored_reason": "application_context_rejected"},
    }


def test_two_stage_one_prompt_slots_complete_with_ungraded_boundary_rows(monkeypatch, tmp_path: Path) -> None:
    fixture = json.loads(Path("tests/fixtures/chat_evals/safety_current.json").read_text(encoding="utf-8"))
    safety = fixture["cases"]
    business_fixture = json.loads(
        Path("tests/fixtures/chat_evals/business_proposed.json").read_text(encoding="utf-8")
    )
    business = [case for case in business_fixture["cases"] if 1 in case.get("selection_stages", [])]
    cases = safety + business
    ids = [case["id"] for case in cases]
    boundary_ids = {"es_card_conflicting_context", "en_private_context_override"}
    runs = [_run("current", case_ids=ids), _run("proposed", prompt_variant="proposed", case_ids=ids)]
    calls = []

    def complete_with_boundaries(**kwargs):
        calls.append(kwargs["run_identity"]["run_id"])
        model_cases = []
        for case in kwargs["cases"]:
            if case["id"] in boundary_ids:
                model_cases.append(
                    {**_boundary_rejection(case["id"]), "run_identity": kwargs["run_identity"]}
                )
            else:
                model_cases.append(
                    {
                        "case_id": case["id"],
                        "run_identity": kwargs["run_identity"],
                        "status": "supported",
                        "provider_turn_started": True,
                        "usage_complete": True,
                        "estimated_cost_usd": 0.001,
                        "known_estimated_cost_lower_bound_usd": 0.001,
                        "model_turn_completed": True,
                    }
                )
        return {
            "output_path": f"/private/{kwargs['run_identity']['run_id']}.json",
            "run_identity": kwargs["run_identity"],
            "run_status": "completed",
            "estimated_cost_usd": 0.056,
            "models": [
                {
                    "candidate": kwargs["run_identity"]["candidate"],
                    "run_identity": kwargs["run_identity"],
                    "known_estimated_cost_usd": 0.056,
                    "estimated_cost_usd": 0.056,
                    "spent_unknown": False,
                    "quality_summary": {"human_review_pending_case_count": 56},
                    "cases": model_cases,
                }
            ],
        }

    result = _invoke(monkeypatch, tmp_path, runs, complete_with_boundaries, budget=1.0, cases=cases)

    assert result["status"] == "completed"
    assert calls == ["current", "proposed"]
    assert all(row["complete"] is True and row["case_count"] == 58 for row in result["run_summaries"])
    saved = json.loads((tmp_path / "campaign.json").read_text(encoding="utf-8"))
    for run in saved["completed_runs"].values():
        boundary_rows = [row for row in run["cases"] if row["case_id"] in boundary_ids]
        assert len(boundary_rows) == 2
        assert all(row["model_turn_completed"] is False for row in boundary_rows)
        assert all(row["provider_turn_started"] is False for row in boundary_rows)
        assert all(row["estimated_cost_usd"] is None for row in boundary_rows)


def test_legacy_completed_report_migrates_and_resumes_only_next_slot(monkeypatch, tmp_path: Path) -> None:
    cases = [
        _boundary_case(
            "es_card_conflicting_context",
            {"tab": "economy", "period": "2026Q2", "entity": "AEROMEXICO", "card_id": "rask"},
        ),
        _boundary_case(
            "en_private_context_override",
            {"tab": "flights", "period": "2026Q2", "entity": "AEROMEXICO", "card_id": "network"},
        ),
        _case("N01"),
    ]
    ids = [case["id"] for case in cases]
    runs = [_run("old-current", case_ids=ids), _run("new-proposed", prompt_variant="proposed", case_ids=ids)]
    state_path = tmp_path / "campaign.json"
    first = _run("old-current", case_ids=ids)
    legacy_cases = [
        {
            "case_id": "es_card_conflicting_context",
            "status": "application_context_rejected",
            "provider_turn_started": False,
            "model_turn_completed": False,
        },
        {
            "case_id": "en_private_context_override",
            "status": "application_context_rejected",
            "provider_turn_started": False,
            "model_turn_completed": False,
        },
        {
            "case_id": "N01",
            "status": "supported",
            "provider_turn_started": True,
            "usage_complete": True,
            "estimated_cost_usd": 0.1,
            "model_turn_completed": True,
        },
    ]
    old_report_path = tmp_path / "old-run.json"
    old_report_path.write_text(
        json.dumps(
            {
                "run_identity": first["identity"],
                "run_status": "completed",
                "models": [
                    {
                        "candidate": first["candidate"],
                        "spent_unknown": False,
                        "cases": [
                            _boundary_rejection("es_card_conflicting_context"),
                            _boundary_rejection("en_private_context_override"),
                            {
                                "case_id": "N01",
                                "status": "supported",
                                "provider_turn_started": True,
                                "usage_complete": True,
                                "estimated_cost_usd": 0.1,
                                "model_turn_completed": True,
                            },
                        ],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    identity = {
        "runs": [run["identity"] for run in runs],
        "run_identity_hashes": [run["identity_hash"] for run in runs],
        "budget_usd": 2.0,
        "expected_versions": {"data_version": "data-v1", "semantic_version": "semantic-v1"},
        "snapshot_root": str(tmp_path / "snapshot"),
        "prices": {"gpt-6-luna@medium": [0.1, 0.5]},
    }
    old_slot = {
        "run_id": first["run_id"],
        "identity": first["identity"],
        "known_estimated_cost_usd": 0.1,
        "spent_unknown": False,
        "cases": legacy_cases,
        "complete": False,
        "stopped_reason": "campaign_budget",
        "summary": {
            "run_id": first["run_id"],
            "report_path": str(old_report_path),
            "run_status": "completed",
            "case_count": 3,
            "expected_case_count": 3,
            "complete": False,
            "stopped_reason": "campaign_budget",
            "known_estimated_cost_usd": 0.1,
            "spent_unknown": False,
            "quality_summary": {},
        },
    }
    state_path.write_text(
        json.dumps(
            {
                "identity": identity,
                "status": "stopped_campaign_budget",
                "budget_usd": 2.0,
                "known_spend_usd": 0.1,
                "spent_unknown": False,
                "active_run_id": None,
                "completed_runs": {first["run_id"]: old_slot},
            }
        ),
        encoding="utf-8",
    )
    calls = []

    def complete(**kwargs):
        calls.append(kwargs["run_identity"]["run_id"])
        return _complete_report(kwargs["run_identity"], kwargs["cases"], cost=0.1)

    result = _invoke(monkeypatch, tmp_path, runs, complete, budget=2.0, resume=True, cases=cases)

    assert result["status"] == "completed"
    assert calls == ["new-proposed"]
    migrated = json.loads(state_path.read_text(encoding="utf-8"))["completed_runs"]["old-current"]
    assert migrated["complete"] is True
    assert migrated["known_estimated_cost_usd"] == 0.1
    assert migrated["cases"][:2] == [
        {
            **legacy_cases[0],
            "quality": {"scored": False, "not_scored_reason": "application_context_rejected"},
            "provider_calls": 0,
            "provider_request_count": 0,
        },
        {
            **legacy_cases[1],
            "quality": {"scored": False, "not_scored_reason": "application_context_rejected"},
            "provider_calls": 0,
            "provider_request_count": 0,
        },
    ]


@pytest.mark.parametrize(
    "bad_row",
    [
        {
            "status": "application_context_rejected",
            "provider_calls": 0,
            "provider_turn_started": False,
            "model_turn_completed": False,
            "application_boundary_test_completed": True,
        },
        {
            "status": "application_context_rejected",
            "provider_calls": 1,
            "provider_turn_started": True,
            "model_turn_completed": False,
            "application_boundary_test_completed": True,
        },
    ],
)
def test_unexpected_or_provider_started_rejection_does_not_complete_slot(
    monkeypatch, tmp_path: Path, bad_row: dict
) -> None:
    fixture_case = _boundary_case("unexpected", {"unknown": "key"})
    runs = [_run("bad-boundary", case_ids=["unexpected"]), _run("must-not-run", repetition=2)]

    def reject(**kwargs):
        row = {"case_id": "unexpected", "usage_complete": None, "estimated_cost_usd": None, **bad_row}
        return {
            "output_path": "/private/bad.json",
            "run_status": "completed",
            "models": [
                {
                    "known_estimated_cost_usd": 0,
                    "spent_unknown": False,
                    "quality_summary": {},
                    "cases": [row],
                }
            ],
        }

    result = _invoke(monkeypatch, tmp_path, runs, reject, cases=[fixture_case])
    assert result["status"] == "stopped_campaign_budget"
    assert result["run_summaries"][0]["complete"] is False
