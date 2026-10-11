"""Offline planning helpers for chat evaluation campaigns."""

from __future__ import annotations

import math
from typing import Any


def render_dry_run(
    cases: list[dict[str, Any]],
    *,
    models: list[str] | None = None,
    prices: dict[str, tuple[float, float]] | None = None,
    input_tokens_per_question: int = 40_000,
    output_tokens_per_question: int = 4_000,
    window_questions: int = 10,
    expected_versions: dict[str, str] | None = None,
    prompt_runs: int = 1,
) -> dict[str, Any]:
    """Describe planned candidate runs, token windows, cost estimates and writes."""
    candidates = models or []
    windows = math.ceil(len(cases) / window_questions) if cases else 0
    rows = []
    for candidate in candidates:
        model, separator, effort = candidate.partition("@")
        input_tokens = sum(input_tokens_per_question * len(case.get("turns", [case["question"]])) for case in cases) * prompt_runs
        output_tokens = sum(output_tokens_per_question * len(case.get("turns", [case["question"]])) for case in cases) * prompt_runs
        # Usage is billed by provider calls, not tool calls. Historical base is
        # already measured across all internal calls for one user question.
        planned_calls = sum(len(case.get("turns", [case["question"]])) for case in cases) * prompt_runs
        input_price, output_price = (prices or {}).get(candidate, (prices or {}).get(model, (None, None)))
        estimated_cost = None
        if input_price is not None and output_price is not None:
            estimated_cost = input_tokens * input_price / 1_000_000 + output_tokens * output_price / 1_000_000
        rows.append(
            {
                "candidate": candidate,
                "model": model,
                "reasoning_effort": effort or None,
                "text_verbosity": None,
                "questions": len(cases),
                "prompt_runs": prompt_runs,
                "windows": windows,
                "planned_provider_calls": planned_calls,
                "estimated_input_tokens": input_tokens,
                "estimated_output_tokens": output_tokens,
                "input_price_usd_per_million": input_price,
                "output_price_usd_per_million": output_price,
                "estimated_cost_usd": estimated_cost,
                "estimate_note": (
                    "estimación modelada desde el promedio histórico recuperado (≈40k input por pregunta, "
                    "incluidas llamadas internas) y tokens de salida ingresados; no es medición live. "
                    "Los turnos explícitos adicionales escalan ambos totales. Caché no descontada."
                ),
            }
        )
    return {
        "mode": "dry-run",
        "expected_versions": expected_versions or {},
        "provider_calls": 0,
        "question_count": len(cases),
        "window_questions": window_questions,
        "planned_provider_calls_total": sum(row["planned_provider_calls"] for row in rows),
        "candidate_runs": rows,
        "destinations": {
            "provider": "ninguno (sin llamadas)",
            "dry_run_report": "stdout (no se persiste)",
            "live_report_if_authorized": ".state/outputs/chat-evaluations/chat-eval-<UTC timestamp>.json",
            "writes_now": [],
        },
    }


def render_campaign_dry_run(
    report: dict[str, Any], *, args: Any, fixture: dict[str, Any],
    cases: list[dict[str, Any]], is_business: bool,
) -> dict[str, Any]:
    """Attach stable F2.2 identities to a no-provider campaign plan."""
    if not is_business or args.stage != 1 or not args.prompt_proposed:
        return report
    if not args.prompt_proposed.is_file():
        raise ValueError("--prompt-proposed no existe")
    if args.models and args.models != ["gpt-6-luna@medium"]:
        raise ValueError("El dry-run F2.2 de etapa 1 requiere solo gpt-6-luna@medium")
    from .evaluation_campaign import build_campaign_runs, extract_proposed_prompt
    from .data.snapshot import Snapshot
    from .providers._openai_helpers import SYSTEM_INSTRUCTIONS
    from .tools.registry import ToolRegistry

    proposed = extract_proposed_prompt(args.prompt_proposed.read_text(encoding="utf-8"))
    registry = ToolRegistry(Snapshot(args.snapshot))
    runs = build_campaign_runs(
        1,
        cases,
        data_version=fixture["expected_versions"]["data_version"],
        semantic_version=fixture["expected_versions"]["semantic_version"],
        prompts={"current": SYSTEM_INSTRUCTIONS, "proposed": proposed},
        tool_specs=registry.tool_specs(),
        limits={
            "max_tool_calls": 16,
            "max_message_chars": 8_000,
            "max_tool_result_bytes": 16_000,
            "max_turn_seconds": 180,
        },
        text_verbosity="medium",
        candidates=["gpt-6-luna@medium"],
    )
    report["campaign_plan"] = {
        "mode": "offline_identity_plan; no provider client or API calls",
        "candidate": "gpt-6-luna@medium",
        "shared_operational_budget_usd_if_authorized": 3.0,
        "limits": runs[0]["limits"],
        "run_ids": [run["run_id"] for run in runs],
        "runs": [
            {
                "run_id": run["run_id"],
                "prompt_variant": run["prompt_variant"],
                "prompt_content_hash": run["prompt_content_hash"],
                "identity_hash": run["identity_hash"],
                "case_count": run["case_count"],
                "user_message_count": run["user_message_count"],
            }
            for run in runs
        ],
        "output_and_checkpoint_paths": {
            "reports": str(args.output_dir),
            "checkpoint": str(args.campaign_state or args.output_dir / "f2-2-stage-1-campaign.json"),
        },
    }
    return report
