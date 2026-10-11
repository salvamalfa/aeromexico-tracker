"""Candidate identity, settings, and safe progress contracts for live evals."""

from __future__ import annotations

import math
from dataclasses import replace
from typing import Any

_LIVE_CANDIDATE_ALIASES = {
    "Luna-M": ("gpt-6-luna", "medium", "medium"),
    "Luna-X": ("gpt-6-luna", "max", "medium"),
    "Sol-B": ("gpt-6.1-sol", "low", "medium"),
    "Sol-M": ("gpt-6.1-sol", "medium", "medium"),
}


def resolve_live_candidates(
    requested: list[Any], default_effort: str, default_verbosity: str
) -> list[dict[str, str]]:
    """Resolve legacy model strings and explicit candidate IDs to fixed settings."""
    from .config import model_catalog

    catalog = model_catalog()
    resolved: list[dict[str, str]] = []
    seen_ids: set[str] = set()
    for item in requested:
        explicit_id: str | None = None
        if isinstance(item, str):
            price_key = item
            if item in _LIVE_CANDIDATE_ALIASES:
                model, effort, verbosity = _LIVE_CANDIDATE_ALIASES[item]
                explicit_id = item
            else:
                parts = item.split("@")
                if len(parts) > 3 or not parts[0]:
                    raise ValueError(f"candidato inválido: {item!r}")
                model = parts[0]
                effort = parts[1] if len(parts) > 1 and parts[1] else default_effort
                verbosity = parts[2] if len(parts) > 2 and parts[2] else default_verbosity
        elif isinstance(item, dict):
            model = item.get("model")
            effort = item.get("reasoning_effort")
            verbosity = item.get("text_verbosity")
            explicit_id = item.get("candidate_id")
            if not all(isinstance(value, str) and value for value in (model, effort, verbosity)):
                raise ValueError(
                    "cada candidato requiere model, reasoning_effort y text_verbosity explícitos"
                )
            if explicit_id is not None and (
                not isinstance(explicit_id, str) or not explicit_id.strip()
            ):
                raise ValueError("candidate_id debe ser una cadena no vacía")
            price_key = explicit_id or f"{model}@{effort}@{verbosity}"
        else:
            raise ValueError("los candidatos deben ser IDs de modelo o objetos de configuración")

        if not all(isinstance(value, str) for value in (model, effort, verbosity)):
            raise ValueError("cada candidato requiere modelo, esfuerzo y verbosidad explícitos")
        entry = catalog.get(model)
        if entry is None:
            raise ValueError(f"modelo no versionado para candidato: {model}")
        if effort not in entry.get("reasoning_efforts", []):
            raise ValueError(f"esfuerzo {effort!r} no permitido para {model}")
        if verbosity not in entry.get("text_verbosity", []):
            raise ValueError(f"verbosidad {verbosity!r} no permitida para {model}")

        candidate_id = explicit_id or f"{model}@{effort}@{verbosity}"
        if candidate_id in seen_ids:
            raise ValueError(f"candidate_id duplicado: {candidate_id}")
        seen_ids.add(candidate_id)
        resolved.append(
            {
                "candidate_id": candidate_id,
                "price_key": price_key,
                "model": model,
                "reasoning_effort": effort,
                "text_verbosity": verbosity,
            }
        )
    return resolved


def validate_live_candidates(
    *,
    models: list[Any],
    prices: dict[str, tuple[float, float]],
    budget_usd: float,
    default_effort: str,
    default_verbosity: str,
) -> list[dict[str, str]]:
    """Validate the campaign envelope and bind every candidate to one price key."""
    if not math.isfinite(budget_usd) or budget_usd <= 0 or budget_usd > 10:
        raise ValueError("el presupuesto debe ser finito, positivo y no superar US$10")
    if len(models) not in (1, 2, 3, 4):
        raise ValueError("se permite una sonda con 1 modelo o una comparación de 2–4 candidatos")
    if any(
        not isinstance(pair, tuple)
        or len(pair) != 2
        or any(not math.isfinite(amount) or amount <= 0 for amount in pair)
        for pair in prices.values()
    ):
        raise ValueError("cada candidato requiere precios finitos y positivos de entrada/salida")

    candidates = resolve_live_candidates(models, default_effort, default_verbosity)
    price_keys = [candidate["price_key"] for candidate in candidates]
    if len(price_keys) != len(set(price_keys)) or set(prices) != set(price_keys):
        raise ValueError("cada candidato único requiere una tarifa ligada a su ID")
    return candidates


def candidate_configs(candidates: list[dict[str, str]]) -> list[dict[str, str]]:
    """Return the public candidate settings contract used in each report."""
    return [
        {
            "candidate_id": candidate["candidate_id"],
            "model": candidate["model"],
            "reasoning_effort": candidate["reasoning_effort"],
            "text_verbosity": candidate["text_verbosity"],
        }
        for candidate in candidates
    ]


def candidate_config(runtime_config: Any, candidate: dict[str, str]) -> Any:
    """Build an isolated provider config pinned to one candidate's three settings."""
    return replace(
        runtime_config,
        provider="openai",
        model=candidate["model"],
        reasoning_effort=candidate["reasoning_effort"],
        text_verbosity=candidate["text_verbosity"],
        openai_enabled=True,
    )


def progress_payload(report: dict[str, Any], state: dict[str, Any]) -> dict[str, Any]:
    """Build a safe progress summary; never copy prompts or model responses."""
    usage_unknown = state.get("active_usage_state") in {"unknown", "unknown_in_flight"} or any(
        model["spent_unknown"] for model in report["models"]
    )
    known_spend = state["known_estimated_spend_usd"]
    models = []
    for model in report["models"]:
        cases = model["cases"]
        models.append(
            {
                "candidate_id": model["candidate_id"],
                "model": model["model"],
                "reasoning_effort": model["reasoning_effort"],
                "text_verbosity": model["text_verbosity"],
                "case_count": len(cases),
                "completed_turn_count": sum(bool(case.get("model_turn_completed")) for case in cases),
                "provider_error_count": sum(case.get("status") == "provider_error" for case in cases),
                "estimated_cost_usd": None if model["spent_unknown"] else model["known_estimated_cost_usd"],
                "known_estimated_cost_usd": model["known_estimated_cost_usd"],
                "spent_unknown": model["spent_unknown"],
                "stopped_reason": model.get("stopped_reason"),
            }
        )
    return {
        "mode": report["mode"],
        "created_at_utc": report["created_at_utc"],
        "data_version": report["data_version"],
        "semantic_version": report["semantic_version"],
        "candidate_models": report["candidate_models"],
        "output_path": report["output_path"],
        "progress_path": report["progress_path"],
        "budget_usd_operational_stop": report["budget_usd_operational_stop"],
        "estimated_spend_usd": None if usage_unknown else known_spend,
        "known_estimated_spend_usd": known_spend,
        "remaining_estimated_budget_usd": (
            None if usage_unknown else max(0.0, report["budget_usd_operational_stop"] - known_spend)
        ),
        "status": state["status"],
        "current_candidate_id": state.get("current_candidate_id"),
        "current_model": state.get("current_model"),
        "current_reasoning_effort": state.get("current_reasoning_effort"),
        "current_text_verbosity": state.get("current_text_verbosity"),
        "active_case_id": state.get("active_case_id"),
        "active_session_id": state.get("active_session_id"),
        "session_to_reconcile": state.get("session_to_reconcile"),
        "active_usage_state": state.get("active_usage_state"),
        "last_error_metadata": state.get("last_error_metadata"),
        "models": models,
        "note": "Resumen de progreso sin preguntas, respuestas, argumentos ni filas del proveedor.",
    }
