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
