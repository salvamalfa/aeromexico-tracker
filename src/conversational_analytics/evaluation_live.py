"""Explicit live evaluation bridge over the production provider boundary."""

from __future__ import annotations

import math
import os
import time
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .data.snapshot import Snapshot
from .evaluation import load_fixture
from .evaluation_live_scoring import score_live_case
from .evaluation_live_support import (
    _CheckpointWriteError,
    _RESERVATION_INPUT_TOKENS_PER_CASE_FLOOR,
    _RESERVATION_OUTPUT_TOKENS_PER_CASE_FLOOR,
    _error_metadata,
    _failure_usage,
    _nearest_rank_percentile,
    _numeric_gold_summary,
    _progress_payload,
    _quality_dict,
    _write_private_json,
)
from .evaluation_live_turns import ConversationRunError, run_conversation
from .providers._openai_helpers import reconcile_case_usage_after_cancel
from .semantic.plan import PlanValidationError

def _live_provider_run(
    *,
    cases: list[dict[str, Any]],
    models: list[str],
    budget_usd: float,
    snapshot_root: Path,
    prices: dict[str, tuple[float, float]],
    probe_only: bool,
    output_dir: Path,
    expected_versions: dict[str, str] | None = None,
    system_instructions: str | None = None,
    run_identity: dict[str, Any] | None = None,
    limits_override: dict[str, int] | None = None,
    text_verbosity_override: str | None = None,
) -> dict[str, Any]:
    """Run gated holdout cases through the production provider/tool boundary.

    Quality scoring is intentionally limited to plans and supported numeric
    answers. Clarification/refusal cases are captured for a blinded human
    rubric; this runner never assigns the fixture's expected outcome to a
    model response. Unknown usage stops that candidate before the next case.
    """
    from .config import ChatConfig, model_catalog
    from .providers.openai import OpenAIProvider
    from .tools.registry import ToolRegistry

    if not math.isfinite(budget_usd) or budget_usd <= 0:
        raise ValueError("el presupuesto operativo por corrida debe ser finito y positivo")
    if len(models) not in (1, 2, 3, 4):
        raise ValueError("se permite una sonda o comparación de 2–4 candidatos modelo@esfuerzo")
    if set(prices) != set(models) or any(
        not math.isfinite(amount) or amount <= 0 for pair in prices.values() for amount in pair
    ):
        raise ValueError("cada candidato requiere precios finitos y positivos de entrada/salida")
    runtime_config = ChatConfig.from_env()
    if text_verbosity_override is not None:
        if text_verbosity_override not in {"low", "medium", "high"}:
            raise ValueError("La verbosidad de texto de la campaña no es válida")
        if run_identity and run_identity.get("text_verbosity") != text_verbosity_override:
            raise ValueError("La verbosidad no coincide con la identidad de corrida")
        runtime_config = replace(runtime_config, text_verbosity=text_verbosity_override)
    if limits_override:
        allowed_limits = {
            "max_tool_calls": "max_tool_calls",
            "max_message_chars": "max_message_chars",
            "max_tool_result_bytes": "max_tool_result_bytes",
            "max_turn_seconds": "max_turn_seconds",
        }
        if set(limits_override) - set(allowed_limits):
            raise ValueError("La campaña contiene límites de runtime desconocidos")
        validated_limits = {}
        for key, value in limits_override.items():
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise ValueError(f"El límite {key} debe ser entero positivo")
            validated_limits[allowed_limits[key]] = value
        runtime_config = replace(runtime_config, **validated_limits)
    snapshot = Snapshot(snapshot_root)
    expected_versions = expected_versions or load_fixture()["expected_versions"]
    if (
        snapshot.version != expected_versions["data_version"]
        or snapshot.semantic_version != expected_versions["semantic_version"]
    ):
        raise ValueError(
            "El snapshot o catálogo semántico no coincide con las versiones fijadas en el holdout"
        )
    registry = ToolRegistry(snapshot)
    metric_dimensions = {
        metric["id"]: metric["dimensions"] for metric in registry.catalog()["metrics"]
    }
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
        "run_identity": run_identity,
        "budget_usd_operational_stop": budget_usd,
        "budget_guaranteed": False,
        "max_tool_calls_per_turn": runtime_config.max_tool_calls,
        "max_turn_seconds_per_turn": runtime_config.max_turn_seconds,
        "probe_only": probe_only,
        "case_count": len(selected),
        "models": [],
        "quality_thresholds": {"supported_accuracy_minimum": 0.95, "critical_failures_allowed": 0},
        "note": (
            "Un turno ya iniciado puede exceder el umbral; uso/costo reportado y caché "
            "pueden ser desconocidos. reasoning_tokens no se expone por separado; forma parte de output_tokens."
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
    for candidate in models:
        if stop_all:
            break
        model, sep, effort = candidate.partition("@")
        effort = effort or getattr(runtime_config, "reasoning_effort", "medium")
        verbosity = getattr(runtime_config, "text_verbosity", None)
        progress_state.update(status="running", current_model=model)
        input_rate, output_rate = prices.get(candidate, prices.get(model, (None, None)))
        if input_rate is None or output_rate is None:
            raise ValueError(f"Falta tarifa para candidato {candidate}")
        changes = {"provider": "openai", "model": model, "openai_enabled": True}
        model_rates = model_catalog().get(model)
        if model_rates is None:
            raise ValueError(f"El catálogo de modelos no contiene {model}")
        changes.update(
            estimated_input_cost_per_million=float(model_rates["input_usd_per_million"]),
            estimated_output_cost_per_million=float(model_rates["output_usd_per_million"]),
            long_context_threshold_input_tokens=int(model_rates["long_context_threshold_input_tokens"]),
            long_context_input_multiplier=float(model_rates["long_context_input_multiplier"]),
            long_context_output_multiplier=float(model_rates["long_context_output_multiplier"]),
            cache_write_input_multiplier=float(model_rates["cache_write_input_multiplier"]),
        )
        if hasattr(runtime_config, "reasoning_effort"):
            changes["reasoning_effort"] = effort
        if hasattr(runtime_config, "text_verbosity"):
            changes["text_verbosity"] = verbosity
        config = replace(runtime_config, **changes)
        provider = None
        model_report: dict[str, Any] = {
            "candidate": candidate,
            "model": model,
            "reasoning_effort": effort,
            "text_verbosity": verbosity,
            "input_price_usd_per_million": input_rate,
            "output_price_usd_per_million": output_rate,
            "cached_input_price_usd_per_million": model_rates["cached_input_usd_per_million"],
            "cache_write_price_usd_per_million": model_rates["cache_write_usd_per_million"],
            "cache_write_usage": "unknown; operational guard prices all input at cache-write rate",
            "long_context_threshold_input_tokens": config.long_context_threshold_input_tokens,
            "long_context_input_multiplier": config.long_context_input_multiplier,
            "long_context_output_multiplier": config.long_context_output_multiplier,
            "pricing_as_of": model_rates.get("pricing_as_of"),
            "cases": [],
            "estimated_cost_usd": 0.0,
            "known_estimated_cost_usd": 0.0,
            "spent_unknown": False,
            "run_identity": run_identity,
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
                    "reserva operativa por mensaje con piso de 140k input y 10k output, valorados con tarifa "
                    "conservadora de cache-write/salida y multiplicadores long-context. Una solicitud puede "
                    "excederla; gasto desconocido detiene la campaña y bloquea replay"
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
            turn_count = len(case.get("turns", [case["question"]]))
            case_reserve = turn_count * config.reservation_cost_usd(reserve_input + reserve_output)
            if estimated_total_usd + case_reserve > budget_usd:
                model_report["stopped_reason"] = "remaining_budget_below_estimated_next_case_reservation"
                model_report["remaining_budget_usd_before_stop"] = max(0.0, budget_usd - estimated_total_usd)
                break
            started = time.perf_counter()
            called_tools: list[dict[str, Any]] = []
            turn_tool_calls: list[list[dict[str, Any]]] = []
            current_turn_index = [0]
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
                        "conversation_turn_index": current_turn_index[0],
                        "provider_turn_id": provider_turn_id,
                        "call_id": call_id,
                        "name": name,
                        "arguments": args,
                        "scope": context,
                        "result": result,
                    }
                )
                if current_turn_index[0] < len(turn_tool_calls):
                    turn_tool_calls[current_turn_index[0]].append(called_tools[-1])
                return result

            turn_results: list[Any] = []
            try:
                if provider is None:
                    provider = (
                        OpenAIProvider(config)
                        if system_instructions is None
                        else OpenAIProvider(config, system_instructions_override=system_instructions)
                    )
                turn_results, result, turn_tool_calls = run_conversation(
                    provider,
                    case,
                    context=context,
                    tool_specs=registry.tool_specs(),
                    call_tool=call_tool,
                    emit=lambda event, payload: emitted.append({"event": event, "payload": payload}),
                    persist_session=persist_session,
                    session=session,
                    current_turn_index=current_turn_index,
                    calls_by_turn=turn_tool_calls,
                )
                observation, grade = score_live_case(
                    case,
                    called_tools,
                    result.content,
                    expected_versions={
                        "data_version": snapshot.version,
                        "semantic_version": snapshot.semantic_version,
                    },
                    scope=context,
                    metric_dimensions=metric_dimensions,
                    turn_responses=[item.content for item in turn_results],
                    turn_tool_calls=turn_tool_calls,
                )
                actual_plan = observation["plan"]
                case_record = {
                    "case_id": case["id"],
                    "expected_status": case.get("expected", {}).get("status"),
                    "candidate": candidate,
                    "model": model,
                    "reasoning_effort": effort,
                    "text_verbosity": verbosity,
                    "status": observation["status"],
                    "response": result.content,
                    "turn_responses": [item.content for item in turn_results],
                    "turn_count": len(turn_results),
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
                    "input_tokens": result.input_tokens,
                    "output_tokens": result.output_tokens,
                    "token_totals_complete": result.usage_complete,
                    "reasoning_tokens": "unknown; included in output_tokens",
                    "turns": len(turn_results),
                    "usage_complete": result.usage_complete,
                    "cached_tokens": "unknown",
                    "latency_seconds": time.perf_counter() - started,
                    "model_turn_completed": True,
                    "provider_turn_started": provider is not None,
                    "quality": grade,
                    "run_identity": run_identity,
                    "turn_usage": [
                        {
                            "input_tokens": item.input_tokens if item.usage_complete else None,
                            "output_tokens": item.output_tokens if item.usage_complete else None,
                            "usage_complete": item.usage_complete,
                        }
                        for item in turn_results
                    ],
                }
                known_turn_results = [item for item in turn_results if item.usage_complete]
                known_cost = sum(
                    config.usage_cost_usd(item.input_tokens, item.output_tokens)
                    for item in known_turn_results
                )
                case_record["known_estimated_cost_lower_bound_usd"] = known_cost
                model_report["known_estimated_cost_usd"] += known_cost
                estimated_total_usd += known_cost
                if result.usage_complete:
                    case_record["estimated_cost_usd"] = known_cost
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
                completed_turns = exc.completed_turns if isinstance(exc, ConversationRunError) else []
                provider_error = exc.original_error if isinstance(exc, ConversationRunError) else exc
                failure_usage = _failure_usage(provider_error)
                known_turns = [result for result in completed_turns if result.usage_complete]
                known_input = sum(result.input_tokens for result in known_turns) if known_turns else None
                known_output = sum(result.output_tokens for result in known_turns) if known_turns else None
                input_parts = [
                    value for value in (known_input, failure_usage[0] if failure_usage else None)
                    if value is not None
                ]
                output_parts = [
                    value for value in (known_output, failure_usage[1] if failure_usage else None)
                    if value is not None
                ]
                error_metadata = _error_metadata(provider_error)
                case_record = {
                    "case_id": case["id"],
                    "expected_status": case.get("expected", {}).get("status"),
                    "candidate": candidate,
                    "model": model,
                    "reasoning_effort": effort,
                    "text_verbosity": verbosity,
                    "status": "provider_error",
                    "tool_calls": called_tools,
                    "session_id": session[-1] if session else None,
                    "input_tokens": sum(input_parts) if input_parts else None,
                    "output_tokens": sum(output_parts) if output_parts else None,
                    "usage_complete": len(known_turns) == len(completed_turns) and failure_usage is not None,
                    "turn_usage": [
                        {
                            "input_tokens": result.input_tokens if result.usage_complete else None,
                            "output_tokens": result.output_tokens if result.usage_complete else None,
                            "usage_complete": result.usage_complete,
                        }
                        for result in completed_turns
                    ],
                    "cached_tokens": "unknown",
                    "reasoning_tokens": "unknown; included in output_tokens",
                    "estimated_cost_usd": None,
                    "latency_seconds": time.perf_counter() - started,
                    "model_turn_completed": False,
                    "provider_turn_started": provider is not None,
                    "quality": {"scored": False, "not_scored_reason": "provider_error"},
                    "error_metadata": error_metadata,
                    "run_identity": run_identity,
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
                    case_record, failure_usage, provider, provider_error, session[-1] if session else None
                )
                known_cost = sum(config.usage_cost_usd(result.input_tokens, result.output_tokens) for result in known_turns)
                if failure_usage is not None:
                    known_cost += config.usage_cost_usd(failure_usage[0], failure_usage[1])
                case_usage_complete = bool(case_record["usage_complete"] or (
                    len(known_turns) == len(completed_turns) and failure_usage is not None
                ))
                case_record["known_estimated_cost_lower_bound_usd"] = known_cost
                case_record["estimated_cost_usd"] = known_cost if case_usage_complete else None
                model_report["known_estimated_cost_usd"] += known_cost
                estimated_total_usd += known_cost
                model_report["spent_unknown"] = not case_usage_complete and provider is not None
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
                        if case_usage_complete
                        else "unknown"
                        if provider is not None
                        else "no_request_started"
                    ),
                    last_error_metadata=error_metadata,
                )
                if session and not case_usage_complete:
                    progress_state["session_to_reconcile"] = session[-1]
                checkpoint()
                if session and provider is not None:
                    case_record["provider_session_delete"] = "deferred_provider_error"
                break
        numeric_gold_summary = _numeric_gold_summary(selected, model_report["cases"])
        tripwires = [
            c for c in model_report["cases"]
            if _quality_dict(c).get("automatic_grade_type") in {"tripwire", "multi_turn_tripwires"}
            and _quality_dict(c).get("scored")
        ]
        model_report["quality_summary"] = {
            **numeric_gold_summary,
            "tripwire_case_count": len(tripwires),
            "tripwire_case_passed": sum(bool(_quality_dict(c).get("passed")) for c in tripwires),
            "human_review_pending_case_count": sum(
                bool(_quality_dict(c).get("requires_blinded_human_rubric")) for c in model_report["cases"]
            ),
            "critical_failure_gate": "pending blinded owner review of every rubric item",
        }
        completed = [case for case in model_report["cases"] if case.get("model_turn_completed")]
        latencies = [float(case["latency_seconds"]) for case in completed]
        attempted = [case for case in model_report["cases"] if case.get("provider_turn_started")]
        token_rows = [case for case in attempted if case.get("usage_complete")]
        model_report["latency_seconds"] = {
            "completed_turn_count": len(completed),
            "p50": _nearest_rank_percentile(latencies, 0.50),
            "p90": _nearest_rank_percentile(latencies, 0.90),
            "p95": _nearest_rank_percentile(latencies, 0.95),
            "percentile_method": "nearest rank; p95 retained for compatibility, p90 is the proposed decision metric",
        }
        model_report["token_totals"] = {
            "input_tokens": sum(case["input_tokens"] for case in token_rows)
            if len(token_rows) == len(attempted)
            else None,
            "output_tokens": sum(case["output_tokens"] for case in token_rows)
            if len(token_rows) == len(attempted)
            else None,
            "known_input_tokens_lower_bound": sum(
                case.get("input_tokens", 0) for case in attempted if isinstance(case.get("input_tokens"), int)
            ),
            "known_output_tokens_lower_bound": sum(
                case.get("output_tokens", 0) for case in attempted if isinstance(case.get("output_tokens"), int)
            ),
            "usage_complete_case_count": len(token_rows),
            "turn_count": len(attempted),
            "cached_tokens": "unknown",
            "reasoning_tokens": "unknown; included in output_tokens",
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
