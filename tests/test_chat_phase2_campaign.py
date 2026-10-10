"""Offline contract checks for stable F2.2 runs, resume, and spend guards."""

import math
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.conversational_analytics.evaluation import load_cases, phase_cases
from src.conversational_analytics.evaluation_campaign import (
    CAMPAIGN_CANDIDATES,
    STAGE2_AUTHORIZATION_DATE,
    STAGE2_EXPECTED_CASE_IDS,
    STAGE2_RESERVE_USD,
    aggregate_campaign_budget,
    build_campaign_runs,
    checkpoint_key,
    effective_stage2_prompt,
    extract_proposed_prompt,
    prompt_content_hash,
    validate_resume_identity,
    validate_stage2_plan,
)

ROOT = Path(__file__).resolve().parents[1]
BUSINESS = load_cases(ROOT / "tests/fixtures/chat_evals/business_proposed.json")
SAFETY = load_cases(ROOT / "tests/fixtures/chat_evals/safety_current.json")
PROMPTS = {"current": "Instrucciones actuales.", "proposed": "Instrucciones propuestas."}
COMMON = {
    "data_version": "data-v7",
    "semantic_version": "semantic-v3",
    "tool_specs": [{"name": "query_metrics", "parameters": {"type": "object"}}],
    "limits": {"max_tool_calls": 8, "max_turn_seconds": 120},
    "text_verbosity": "medium",
}


def selected(stage: int) -> list[dict]:
    return phase_cases(BUSINESS, SAFETY, stage)


def runs(stage: int, prompts: dict[str, str] = PROMPTS) -> list[dict]:
    return build_campaign_runs(stage, selected(stage), prompts=prompts, **COMMON)


def test_f21_extraction_uses_only_the_proposed_fence() -> None:
    document = """# F2.1 Prompt

## Prompt actual
```text
OLD PROMPT MUST NOT BE USED
```

## Prompt propuesto
```text
NEW TRUSTED PROMPT
```

## Comparación
```text
COMPARISON MUST NOT BE USED
```
"""
    assert extract_proposed_prompt(document) == "NEW TRUSTED PROMPT"
    assert extract_proposed_prompt("Raw trusted prompt") == "Raw trusted prompt"
    with pytest.raises(ValueError, match="sin bloque"):
        extract_proposed_prompt("# F2.1 Prompt\n\n## Comparación\n```\nOLD\n```")


def test_f21_plan_extracts_only_its_prompt_draft_fence() -> None:
    source = (ROOT / "docs/chat/fase-2-agente-analitico.md").read_text(encoding="utf-8")
    prompt = extract_proposed_prompt(source)

    assert prompt.startswith("<rol>")
    assert prompt.endswith("</ejemplos>")
    assert "### Borrador inicial" not in prompt
    assert "Lo que queda pendiente al ajustar el borrador" not in prompt


def test_preflight_prompt_hash_equals_the_provider_instructions_hash() -> None:
    prompt_module = pytest.importorskip("src.conversational_analytics.providers._openai_prompt")
    from src.conversational_analytics.providers.openai import OpenAIProvider

    source = (ROOT / "docs/chat/fase-2-agente-analitico.md").read_text(encoding="utf-8")
    effective = effective_stage2_prompt(source)
    provider = OpenAIProvider(
        SimpleNamespace(
            openai_enabled=True,
            model="gpt-6-luna",
            reasoning_effort="medium",
            text_verbosity="medium",
            max_tool_calls=16,
            max_tool_result_bytes=16_000,
            max_turn_seconds=180,
        ),
        client=object(),
        system_instructions_override=effective,
    )

    assert prompt_module.prompt_sha256(effective) == prompt_content_hash(effective)
    assert provider._instructions() == effective
    assert prompt_module.prompt_sha256(provider._instructions()) == prompt_module.prompt_sha256(effective)


def test_stage_one_schedules_two_luna_runs_with_distinct_prompt_identity() -> None:
    manifest = runs(1)

    assert len(manifest) == 2
    assert {run["candidate"] for run in manifest} == {"gpt-6-luna@medium"}
    assert {run["prompt_variant"] for run in manifest} == {"current", "proposed"}
    assert {run["case_count"] for run in manifest} == {58}
    assert {run["user_message_count"] for run in manifest} == {62}
    assert len({run["run_id"] for run in manifest}) == 2
    assert len({run["prompt_content_hash"] for run in manifest}) == 2
    assert len({run["identity_hash"] for run in manifest}) == 2


def test_stage_three_repetitions_are_distinct_resume_identities() -> None:
    manifest = runs(3)
    luna = [run for run in manifest if run["candidate"] == "gpt-6-luna@medium"]

    assert len(manifest) == 6
    assert len(luna) == 2
    assert {run["repetition"] for run in luna} == {1, 2}
    assert len({run["run_id"] for run in luna}) == 2
    assert len({run["identity_hash"] for run in luna}) == 2
    assert {run["case_count"] for run in manifest} == {70}
    assert {run["user_message_count"] for run in manifest} == {74}
    assert checkpoint_key(luna[0]["run_id"], "N01", 0) != checkpoint_key(luna[1]["run_id"], "N01", 0)


def _stage2_cases() -> list[dict]:
    return [
        {
            "id": case_id,
            "question": f"Pregunta {case_id}",
            "turns": [f"Pregunta {case_id}"],
            "context": {"period": "2026Q2"} if index == 0 else {},
            "expected": {"status": "supported" if index < 5 else "refused"},
            "rubric": {"correctness": "review"},
        }
        for index, case_id in enumerate(STAGE2_EXPECTED_CASE_IDS)
    ]


def _stage2_config() -> dict:
    return {
        "stage": "F2.9-stage-2",
        "status": "ready_offline_preflight_only_no_execution_authorized",
        "owner_decision": {
            "authorized_reserve_usd": STAGE2_RESERVE_USD,
            "stage2_reserve_funded_usd": 8.0,
            "funding_confirmed_date": STAGE2_AUTHORIZATION_DATE,
        },
    }


def test_stage2_preflight_freezes_four_candidates_ids_budget_and_hashes() -> None:
    cases = _stage2_cases()
    fixture = {
        "status": "DERIVED_OFFLINE_REVIEW",
        "expected_versions": {"data_version": "data-v7", "semantic_version": "semantic-v3"},
        "cases": cases,
    }

    plan = validate_stage2_plan(
        config=_stage2_config(),
        fixture=fixture,
        cases=cases,
        candidates=CAMPAIGN_CANDIDATES,
        snapshot_data_version="data-v7",
        snapshot_semantic_version="semantic-v3",
        prompt="Prompt efectivo con regla de periodo.",
        api_key_present=False,
    )

    assert plan["execution_authorized"] is False
    assert plan["authorized_reserve_usd"] == 8.0
    assert plan["additional_funding_required_usd"] == 0.0
    assert plan["planned_responses"] == 60
    assert plan["case_ids"] == list(STAGE2_EXPECTED_CASE_IDS)
    assert plan["cohort_counts"] == {"business": 5, "safety": 10}
    assert len(plan["case_context_sha256"]) == 64
    assert len(plan["prompt_sha256"]) == 64
    assert plan["api_key_present"] is False

    manifest = build_campaign_runs(
        2, cases, data_version="data-v7", semantic_version="semantic-v3",
        prompts={"proposed": "Prompt efectivo con regla de periodo."},
        tool_specs=COMMON["tool_specs"], limits={"max_tool_calls": 16},
        text_verbosity="medium",
    )
    assert len(manifest) == 4
    assert all(run["case_count"] == 15 and run["user_message_count"] == 15 for run in manifest)
    assert len({run["prompt_content_hash"] for run in manifest}) == 1


def test_stage2_preflight_rejects_drifted_case_cohort_or_snapshot() -> None:
    cases = _stage2_cases()
    fixture = {
        "status": "DERIVED_OFFLINE_REVIEW",
        "expected_versions": {"data_version": "data-v7", "semantic_version": "semantic-v3"},
        "cases": cases,
    }
    changed = list(cases)
    changed[0] = dict(changed[0], id="N99")
    with pytest.raises(ValueError, match="15 IDs congelados"):
        validate_stage2_plan(
            config=_stage2_config(), fixture=fixture, cases=changed,
            candidates=CAMPAIGN_CANDIDATES, snapshot_data_version="data-v7",
            snapshot_semantic_version="semantic-v3", prompt="prompt", api_key_present=False,
        )
    with pytest.raises(ValueError, match="versión de datos"):
        validate_stage2_plan(
            config=_stage2_config(), fixture=fixture, cases=cases,
            candidates=CAMPAIGN_CANDIDATES, snapshot_data_version="other",
            snapshot_semantic_version="semantic-v3", prompt="prompt", api_key_present=False,
        )


def test_stage_three_accepts_owner_shortlist_without_changing_default_schedule() -> None:
    manifest = build_campaign_runs(
        3,
        selected(3),
        prompts=PROMPTS,
        candidates=["gpt-6.1-sol@low", "gpt-6-luna@max"],
        **COMMON,
    )

    assert len(manifest) == 3
    assert {run["candidate"] for run in manifest} == {"gpt-6.1-sol@low", "gpt-6-luna@max"}
    assert sum(run["candidate"] == "gpt-6-luna@max" for run in manifest) == 2


def test_resume_fails_closed_on_prompt_or_limit_change() -> None:
    original = runs(1)[0]["identity"]
    validate_resume_identity(original, dict(original))
    changed = dict(original, limits={"max_tool_calls": 9, "max_turn_seconds": 120})
    with pytest.raises(ValueError, match="Resume bloqueado"):
        validate_resume_identity(original, changed)


def test_campaign_budget_sums_stages_and_unknown_error_blocks_more_requests() -> None:
    known = {
        "run_id": "stage1-current",
        "cases": [
            {"case_id": "N01", "provider_turn_started": True, "usage_complete": True, "estimated_cost_usd": 0.25, "model_turn_completed": True},
        ],
    }
    unknown_error = {
        "run_id": "stage2-sol",
        "cases": [
            {"case_id": "N01", "provider_turn_started": True, "usage_complete": False, "estimated_cost_usd": None, "status": "provider_error"},
        ],
    }
    summary = aggregate_campaign_budget([known, unknown_error])

    assert summary["run_count"] == 2
    assert summary["known_spend_usd"] == 0.25
    assert summary["spent_unknown"] is True
    assert summary["total_spend_usd"] is None
    assert summary["error_count"] == 1
    assert summary["admit_new_requests"] is False


@pytest.mark.parametrize("bad_cost", [math.nan, math.inf, -math.inf, True, -0.01])
def test_campaign_budget_rejects_nonfinite_or_invalid_costs(bad_cost: object) -> None:
    run = {"run_id": "bad", "cases": [{"case_id": "N01", "estimated_cost_usd": bad_cost}]}
    with pytest.raises(ValueError, match="Costo"):
        aggregate_campaign_budget([run])


@pytest.mark.parametrize("bad_count", [True, -1, 1.5])
def test_campaign_budget_rejects_invalid_provider_call_counters(bad_count: object) -> None:
    run = {
        "run_id": "bad",
        "cases": [{"case_id": "N01", "provider_calls": bad_count, "estimated_cost_usd": 0.0}],
    }
    with pytest.raises(ValueError, match="provider_calls"):
        aggregate_campaign_budget([run])


@pytest.mark.parametrize("bad_cost", [math.nan, math.inf, -math.inf, True, -0.01])
def test_campaign_budget_rejects_nonfinite_run_summary_costs(bad_cost: object) -> None:
    with pytest.raises(ValueError, match="Costo"):
        aggregate_campaign_budget([{"known_estimated_cost_usd": bad_cost, "spent_unknown": False}])


def test_started_request_without_explicit_complete_usage_fails_closed() -> None:
    summary = aggregate_campaign_budget(
        [{"run_id": "partial", "cases": [{"case_id": "N01", "provider_turn_started": True, "estimated_cost_usd": 0.1}]}]
    )

    assert summary["known_spend_usd"] == 0.1
    assert summary["spent_unknown"] is True
    assert summary["admit_new_requests"] is False


def test_campaign_budget_counts_known_partial_turn_cost_without_double_counting() -> None:
    summary = aggregate_campaign_budget(
        [
            {
                "run_id": "partial",
                "cases": [
                    {
                        "case_id": "N01",
                        "provider_turn_started": True,
                        "usage_complete": False,
                        "estimated_cost_usd": None,
                        "known_estimated_cost_lower_bound_usd": 0.3,
                    },
                    {
                        "case_id": "N02",
                        "provider_turn_started": True,
                        "usage_complete": True,
                        "estimated_cost_usd": 0.5,
                        "known_estimated_cost_lower_bound_usd": 0.2,
                    },
                ],
            }
        ]
    )

    assert summary["known_spend_usd"] == 0.8
    assert summary["spent_unknown"] is True
    assert summary["total_spend_usd"] is None
    assert summary["admit_new_requests"] is False
