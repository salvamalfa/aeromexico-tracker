"""Explicit live evaluation bridge over the production provider boundary."""

from __future__ import annotations

import json
import math
import os
import tempfile
import threading
import time
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .data.snapshot import Snapshot
from .evaluation import load_fixture, verify_observation
from .evaluation_observation import observation_from_tool_calls
from .providers._openai_helpers import reconcile_case_usage_after_cancel
from .semantic.plan import PlanValidationError

_SAFE_EXCEPTION_TYPES = frozenset(
    {
        "APIConnectionError",
        "APITimeoutError",
        "APIStatusError",
        "AuthenticationError",
        "BadRequestError",
        "ConflictError",
        "InternalServerError",
        "NotFoundError",
        "OpenAIProviderError",
        "PermissionDeniedError",
        "RateLimitError",
        "TimeoutError",
        "UnprocessableEntityError",
        "ConnectionError",
        "OSError",
    }
)
_SAFE_HTTP_STATUSES = frozenset({400, 401, 403, 404, 408, 409, 413, 422, 425, 429, 500, 502, 503, 504})
_SAFE_REASON_CODES = frozenset({"tool_call_limit", "turn_timeout", "tool_result_limit"})
_RESERVATION_INPUT_TOKENS_PER_CASE_FLOOR = 140_000
_RESERVATION_OUTPUT_TOKENS_PER_CASE_FLOOR = 10_000


class _CheckpointWriteError(RuntimeError):
    """A private checkpoint failure must not be reclassified as provider failure."""


def _error_metadata(exc: BaseException) -> dict[str, Any]:
    """Keep only allowlisted exception class names and HTTP status metadata."""
    names: list[str] = []
    status: int | None = None
    reason_code: str | None = None
    current: BaseException | None = exc
    visited: set[int] = set()
    while current is not None and id(current) not in visited and len(visited) < 6:
        visited.add(id(current))
        name = type(current).__name__
        if name in _SAFE_EXCEPTION_TYPES and name not in names:
            names.append(name)
        candidate = getattr(current, "status_code", None)
        if (
            isinstance(candidate, int)
            and not isinstance(candidate, bool)
            and candidate in _SAFE_HTTP_STATUSES
        ):
            status = candidate
        candidate_reason = getattr(current, "reason_code", None)
        if candidate_reason in _SAFE_REASON_CODES:
            reason_code = candidate_reason
        current = current.__cause__ or current.__context__
    result: dict[str, Any] = {"exception_types": names or ["unknown"]}
    result.update({"http_status": status} if status is not None else {})
    result.update({"reason_code": reason_code} if reason_code is not None else {})
    return result


def _quality_dict(case_record: dict[str, Any]) -> dict[str, Any]:
    quality = case_record.get("quality")
    return quality if isinstance(quality, dict) else {}


def _failure_usage(exc: BaseException) -> tuple[int, int] | None:
    usage = getattr(exc, "usage", None)
    if (
        isinstance(usage, tuple)
        and len(usage) == 2
        and all(isinstance(value, int) and not isinstance(value, bool) and value >= 0 for value in usage)
    ):
        return usage
    return None


def _write_private_json(path: Path, payload: dict[str, Any]) -> None:
    """Atomically persist sensitive evaluation files with owner-only access."""
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(path.parent, 0o700)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=path.parent, prefix=f".{path.name}.", suffix=".tmp", delete=False
        ) as handle:
            temporary_path = Path(handle.name)
            os.chmod(temporary_path, 0o600)
            json.dump(payload, handle, ensure_ascii=False, indent=2, default=list)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, path)
        os.chmod(path, 0o600)
    finally:
        if temporary_path and temporary_path.exists():
            temporary_path.unlink()


def _progress_payload(report: dict[str, Any], state: dict[str, Any]) -> dict[str, Any]:
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
                "model": model["model"],
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
        "current_model": state.get("current_model"),
        "active_case_id": state.get("active_case_id"),
        "active_session_id": state.get("active_session_id"),
        "session_to_reconcile": state.get("session_to_reconcile"),
        "active_usage_state": state.get("active_usage_state"),
        "last_error_metadata": state.get("last_error_metadata"),
        "models": models,
        "note": "Resumen de progreso sin preguntas, respuestas, argumentos ni filas del proveedor.",
    }


def _nearest_rank_percentile(values: list[float], percentile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    return ordered[max(0, math.ceil(len(ordered) * percentile) - 1)]


def _live_provider_run(
    *,
    cases: list[dict[str, Any]],
    models: list[str],
    budget_usd: float,
    snapshot_root: Path,
    prices: dict[str, tuple[float, float]],
    probe_only: bool,
    output_dir: Path,
) -> dict[str, Any]:
    """Run gated holdout cases through the production provider/tool boundary.

    Quality scoring is intentionally limited to plans and supported numeric
    answers. Clarification/refusal cases are captured for a blinded human
    rubric; this runner never assigns the fixture's expected outcome to a
    model response. Unknown usage stops that candidate before the next case.
    """
    from .config import ChatConfig
    from .providers.openai import OpenAIProvider
    from .tools.registry import ToolRegistry

    if not math.isfinite(budget_usd) or budget_usd <= 0 or budget_usd > 10:
        raise ValueError("el presupuesto debe ser finito, positivo y no superar US$10")
    if len(models) not in (1, 2, 3):
        raise ValueError("se permite una sonda con 1 modelo o una comparación de 2–3 modelos")
    if set(prices) != set(models) or any(
        not math.isfinite(amount) or amount <= 0 for pair in prices.values() for amount in pair
    ):
        raise ValueError("cada candidato requiere precios finitos y positivos de entrada/salida")
    snapshot = Snapshot(snapshot_root)
    expected_versions = load_fixture()["expected_versions"]
    if (
        snapshot.version != expected_versions["data_version"]
        or snapshot.semantic_version != expected_versions["semantic_version"]
    ):
        raise ValueError(
            "El snapshot o catálogo semántico no coincide con las versiones fijadas en el holdout"
        )
    registry = ToolRegistry(snapshot)
    selected = [next(case for case in cases if case["id"] == "es_am_lf_q2")] if probe_only else cases
    output_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(output_dir, 0o700)
    run_stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    out = output_dir / f"chat-eval-{run_stamp}.json"
    progress_out = output_dir / f"chat-eval-{run_stamp}.progress.json"
    report: dict[str, Any] = {
        "mode": "live-probe" if probe_only else "live-evaluation",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "data_version": snapshot.version,
        "semantic_version": snapshot.semantic_version,
        "candidate_models": models,
        "budget_usd_operational_stop": budget_usd,
        "budget_guaranteed": False,
        "max_tool_calls_per_turn": 5,
        "probe_only": probe_only,
        "case_count": len(selected),
        "models": [],
        "quality_thresholds": {"supported_accuracy_minimum": 0.95, "critical_failures_allowed": 0},
        "note": (
            "Un turno ya iniciado puede exceder el umbral; uso/costo reportado y caché "
            "pueden ser desconocidos."
        ),
        "output_path": str(out),
        "progress_path": str(progress_out),
    }
    progress_state: dict[str, Any] = {
        "status": "starting",
        "known_estimated_spend_usd": 0.0,
        "current_model": None,
        "active_case_id": None,
        "active_session_id": None,
        "session_to_reconcile": None,
        "active_usage_state": None,
        "last_error_metadata": None,
    }

    def checkpoint() -> None:
        try:
            _write_private_json(progress_out, _progress_payload(report, progress_state))
        except Exception as exc:
            raise _CheckpointWriteError("No se pudo escribir el checkpoint privado.") from exc

    estimated_total_usd = 0.0
    stop_all = False
    for model in models:
        if stop_all:
            break
        progress_state.update(status="running", current_model=model)
        input_rate, output_rate = prices[model]
        config = replace(
            ChatConfig.from_env(),
            provider="openai",
            model=model,
            openai_enabled=True,
            max_tool_calls=5,
            max_tool_result_bytes=16_000,
        )
        provider = None
        model_report: dict[str, Any] = {
            "model": model,
            "input_price_usd_per_million": input_rate,
            "output_price_usd_per_million": output_rate,
            "cached_input_price": "unknown/not applied",
            "cache_write_price": "unknown/not applied",
            "cases": [],
            "estimated_cost_usd": 0.0,
            "known_estimated_cost_usd": 0.0,
            "spent_unknown": False,
            "reservation_assumption": {
                "input_tokens_per_turn": max(
                    _RESERVATION_INPUT_TOKENS_PER_CASE_FLOOR,
                    config.max_tool_calls
                    * (config.max_message_chars // 4 + config.max_tool_result_bytes // 4),
                ),
                "output_tokens_per_turn": max(
                    _RESERVATION_OUTPUT_TOKENS_PER_CASE_FLOOR, config.max_tool_calls * 2_000
                ),
                "note": (
                    "reserva operativa por caso con piso calibrado a 140k tokens de entrada y 10k de salida "
                    "tras reconciliar uso observado; no limita una solicitud y no garantiza el cargo"
                ),
            },
        }
        report["models"].append(model_report)
        checkpoint()
        for case in selected:
            if stop_all:
                model_report["stopped_reason"] = "previous_model_usage_unknown; comparison stopped"
                break
            reserve_input = model_report["reservation_assumption"]["input_tokens_per_turn"]
            reserve_output = model_report["reservation_assumption"]["output_tokens_per_turn"]
            case_reserve = (reserve_input * input_rate + reserve_output * output_rate) / 1_000_000
            if estimated_total_usd + case_reserve > budget_usd:
                model_report["stopped_reason"] = "remaining_budget_below_estimated_next_case_reservation"
                model_report["remaining_budget_usd_before_stop"] = max(0.0, budget_usd - estimated_total_usd)
                break
            started = time.perf_counter()
            called_tools: list[dict[str, Any]] = []
            emitted: list[dict[str, Any]] = []
            session: list[str] = []
            case_context = case.get("context", {})
            # Invalid/untrusted UI context is tested as an application-boundary
            # rejection. Never forward unknown context keys to the provider.
            try:
                from .service import validate_context

                context = validate_context(case_context)
            except ValueError as exc:
                model_report["cases"].append(
                    {
                        "case_id": case["id"],
                        "status": "application_context_rejected",
                        "error": str(exc),
                        "provider_calls": 0,
                        "latency_seconds": time.perf_counter() - started,
                        "quality": {"scored": False, "not_scored_reason": "application_context_rejected"},
                    }
                )
                continue
            progress_state.update(
                status="running",
                current_model=model,
                active_case_id=case["id"],
                active_session_id=None,
                active_usage_state="unknown_in_flight",
            )
            checkpoint()

            def persist_session(session_id: str) -> None:
                session[:] = [session_id]
                progress_state["active_session_id"] = session_id
                checkpoint()

            def call_tool(
                provider_turn_id: str, call_id: str, name: str, args: dict[str, Any]
            ) -> dict[str, Any]:
                try:
                    result = registry.invoke(name, args, context=context)
                except (PlanValidationError, ValueError, KeyError, TypeError) as exc:
                    message = (
                        str(exc)[:300]
                        if isinstance(exc, PlanValidationError)
                        else "La consulta no pasó la validación semántica."
                    )
                    result = {"error": {"code": "tool_rejected", "message": message}}
                called_tools.append(
                    {
                        "provider_turn_id": provider_turn_id,
                        "call_id": call_id,
                        "name": name,
                        "arguments": args,
                        "result": result,
                    }
                )
                return result

            try:
                if provider is None:
                    provider = OpenAIProvider(config)
                result = provider.run_turn(
                    session_id=None,
                    messages=[{"role": "user", "content": case["question"]}],
                    context=context,
                    tool_specs=registry.tool_specs(),
                    call_tool=call_tool,
                    emit=lambda event, payload: emitted.append({"event": event, "payload": payload}),
                    persist_session=persist_session,
                    cancel_event=threading.Event(),
                )
                observation = observation_from_tool_calls(called_tools, result.content)
                actual_plan = observation["plan"]
                if case["expected"]["status"] == "supported":
                    scored = verify_observation(case, observation)
                    grade = {
                        "scored": True,
                        "passed": scored.passed,
                        "checks": scored.checks,
                        "failures": scored.failures,
                    }
                else:
                    grade = {
                        "scored": False,
                        "requires_blinded_human_rubric": True,
                        "expected_outcome_for_grader": case["expected"]["status"],
                    }
                case_record = {
                    "case_id": case["id"],
                    "status": observation["status"],
                    "response": result.content,
                    "plan": actual_plan,
                    "tool_calls": called_tools,
                    "references": result.references,
                    "session_id": session[-1] if session else None,
                    "provider_turn_ids": sorted(
                        {
                            str(event["payload"]["turn_id"])
                            for event in emitted
                            if isinstance(event.get("payload"), dict) and event["payload"].get("turn_id")
                        }
                        | {
                            str(tool["provider_turn_id"])
                            for tool in called_tools
                            if tool.get("provider_turn_id")
                        }
                    ),
                    "provider_event_ids": sorted(
                        {
                            str(event["payload"]["provider_event_id"])
                            for event in emitted
                            if isinstance(event.get("payload"), dict)
                            and event["payload"].get("provider_event_id")
                        }
                    ),
                    "provider_events": emitted,
                    "provider_tool_call_count": len(called_tools),
                    "provider_request_count": "unknown",
                    "input_tokens": result.input_tokens if result.usage_complete else None,
                    "output_tokens": result.output_tokens if result.usage_complete else None,
                    "usage_complete": result.usage_complete,
                    "cached_tokens": "unknown",
                    "latency_seconds": time.perf_counter() - started,
                    "model_turn_completed": True,
                    "provider_turn_started": provider is not None,
                    "quality": grade,
                }
                if result.usage_complete:
                    cost = (result.input_tokens * input_rate + result.output_tokens * output_rate) / 1_000_000
                    case_record["estimated_cost_usd"] = cost
                    model_report["known_estimated_cost_usd"] += cost
                    estimated_total_usd += cost
                else:
                    case_record["estimated_cost_usd"] = None
                    model_report["spent_unknown"] = True
                model_report["estimated_cost_usd"] = (
                    None if model_report["spent_unknown"] else model_report["known_estimated_cost_usd"]
                )
                model_report["cases"].append(case_record)
                progress_state.update(
                    known_estimated_spend_usd=estimated_total_usd,
                    active_case_id=None,
                    active_session_id=session[-1] if session else None,
                    active_usage_state="complete" if result.usage_complete else "unknown",
                    last_error_metadata=None,
                )
                if not result.usage_complete and session:
                    progress_state["session_to_reconcile"] = session[-1]
                checkpoint()
                # Deleting local test sessions reduces retained provider state;
                # remote deletion is a best-effort provider capability, not a
                # claim that all provider logs or telemetry have been erased.
                if session and provider is not None:
                    if result.usage_complete:
                        try:
                            provider.delete(session[-1])
                            case_record["provider_session_delete"] = "requested"
                        except Exception:
                            case_record["provider_session_delete"] = "failed"
                            case_record["remote_retention_state"] = "unknown"
                    else:
                        case_record["provider_session_delete"] = "deferred_usage_unknown"
                if model_report["spent_unknown"]:
                    model_report["stopped_reason"] = "usage_unknown; no further cases admitted"
                    stop_all = True
                    break
                if estimated_total_usd >= budget_usd:
                    model_report["stopped_reason"] = "operational_budget_reached_after_current_case"
                    stop_all = True
                    break
            except _CheckpointWriteError:
                raise
            except Exception as exc:
                failure_usage = _failure_usage(exc)
                error_metadata = _error_metadata(exc)
                case_record = {
                    "case_id": case["id"],
                    "status": "provider_error",
                    "tool_calls": called_tools,
                    "session_id": session[-1] if session else None,
                    "input_tokens": failure_usage[0] if failure_usage else None,
                    "output_tokens": failure_usage[1] if failure_usage else None,
                    "usage_complete": failure_usage is not None,
                    "cached_tokens": "unknown",
                    "estimated_cost_usd": None,
                    "latency_seconds": time.perf_counter() - started,
                    "model_turn_completed": False,
                    "provider_turn_started": provider is not None,
                    "quality": {"scored": False, "not_scored_reason": "provider_error"},
                    "error_metadata": error_metadata,
                }
                cancel_provider = getattr(provider, "cancel", None)
                if session and provider is not None and callable(cancel_provider):
                    try:
                        cancel_provider(session[-1])
                        case_record["provider_cancel"] = "attempted"
                    except Exception:
                        case_record["provider_cancel"] = "failed"
                else:
                    case_record["provider_cancel"] = "not_available"
                failure_usage = reconcile_case_usage_after_cancel(
                    case_record, failure_usage, provider, exc, session[-1] if session else None
                )
                if failure_usage is not None:
                    cost = (failure_usage[0] * input_rate + failure_usage[1] * output_rate) / 1_000_000
                    case_record["estimated_cost_usd"] = cost
                    model_report["known_estimated_cost_usd"] += cost
                    estimated_total_usd += cost
                model_report["spent_unknown"] = failure_usage is None and provider is not None
                model_report["estimated_cost_usd"] = (
                    None if model_report["spent_unknown"] else model_report["known_estimated_cost_usd"]
                )
                model_report["cases"].append(case_record)
                model_report["stopped_reason"] = "provider_error_or_usage_unknown; no further cases admitted"
                stop_all = True
                progress_state.update(
                    status="stopped_provider_error",
                    known_estimated_spend_usd=estimated_total_usd,
                    active_case_id=case["id"],
                    active_session_id=session[-1] if session else None,
                    active_usage_state=(
                        "complete"
                        if failure_usage is not None
                        else "unknown"
                        if provider is not None
                        else "no_request_started"
                    ),
                    last_error_metadata=error_metadata,
                )
                if session and failure_usage is None:
                    progress_state["session_to_reconcile"] = session[-1]
                checkpoint()
                if session and provider is not None:
                    case_record["provider_session_delete"] = "deferred_provider_error"
                break
        model_report["quality_summary"] = {
            "supported_scored": sum(bool(_quality_dict(c).get("scored")) for c in model_report["cases"]),
            "supported_passed": sum(bool(_quality_dict(c).get("passed")) for c in model_report["cases"]),
            "safety_and_ambiguity_pending_human_review": sum(
                bool(_quality_dict(c).get("requires_blinded_human_rubric")) for c in model_report["cases"]
            ),
            "critical_failure_gate": "pending blinded review of safety/ambiguity cases",
        }
        completed = [case for case in model_report["cases"] if case.get("model_turn_completed")]
        latencies = [float(case["latency_seconds"]) for case in completed]
        attempted = [case for case in model_report["cases"] if case.get("provider_turn_started")]
        token_rows = [case for case in attempted if case.get("usage_complete")]
        model_report["latency_seconds"] = {
            "completed_turn_count": len(completed),
            "p50": _nearest_rank_percentile(latencies, 0.50),
            "p95": _nearest_rank_percentile(latencies, 0.95),
        }
        model_report["token_totals"] = {
            "input_tokens": sum(case["input_tokens"] for case in token_rows)
            if len(token_rows) == len(attempted)
            else None,
            "output_tokens": sum(case["output_tokens"] for case in token_rows)
            if len(token_rows) == len(attempted)
            else None,
            "usage_complete_case_count": len(token_rows),
            "turn_count": len(attempted),
            "cached_tokens": "unknown",
        }
        progress_state.update(
            status="stopped" if stop_all else "running",
            current_model=None if stop_all else model,
            known_estimated_spend_usd=estimated_total_usd,
            active_case_id=None,
            active_session_id=None,
            active_usage_state=None,
        )
        checkpoint()
    final_status = "stopped" if stop_all else "completed"
    report["known_estimated_cost_usd"] = estimated_total_usd
    report["estimated_cost_usd"] = (
        None if any(model["spent_unknown"] for model in report["models"]) else estimated_total_usd
    )
    report["run_status"] = final_status
    progress_state.update(
        status="finalizing",
        current_model=None,
        known_estimated_spend_usd=estimated_total_usd,
        active_case_id=None,
        active_session_id=None,
        active_usage_state=None,
    )
    checkpoint()
    _write_private_json(out, report)
    progress_state["status"] = final_status
    checkpoint()
    return report
