"""Explicit live evaluation bridge over the production provider boundary."""

from __future__ import annotations

import json
import math
import threading
import time
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .data.snapshot import Snapshot
from .evaluation import load_fixture, verify_observation


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

    if len(models) not in (1, 2, 3):
        raise ValueError("se permite una sonda con 1 modelo o una comparación de 2–3 modelos")
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
    }
    estimated_total_usd = 0.0
    stop_all = False
    for model in models:
        input_rate, output_rate = prices[model]
        config = replace(
            ChatConfig.from_env(),
            provider="openai",
            model=model,
            openai_enabled=True,
            max_tool_calls=5,
            max_tool_result_bytes=16_000,
        )
        provider = OpenAIProvider(config)
        model_report: dict[str, Any] = {
            "model": model,
            "input_price_usd_per_million": input_rate,
            "output_price_usd_per_million": output_rate,
            "cached_input_price": "unknown/not applied",
            "cache_write_price": "unknown/not applied",
            "cases": [],
            "estimated_cost_usd": 0.0,
            "spent_unknown": False,
            "reservation_assumption": {
                "input_tokens_per_turn": config.max_tool_calls
                * (config.max_message_chars // 4 + config.max_tool_result_bytes // 4),
                "output_tokens_per_turn": config.max_tool_calls * 2_000,
                "note": (
                    "reserva operativa aproximada para admitir o frenar casos; no limita los tokens "
                    "de una solicitud y no garantiza el cargo"
                ),
            },
        }
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
                        "quality": "not_scored",
                    }
                )
                continue

            def call_tool(
                provider_turn_id: str, call_id: str, name: str, args: dict[str, Any]
            ) -> dict[str, Any]:
                result = registry.invoke(name, args, context=context)
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
                result = provider.run_turn(
                    session_id=None,
                    messages=[{"role": "user", "content": case["question"]}],
                    context=context,
                    tool_specs=registry.tool_specs(),
                    call_tool=call_tool,
                    emit=lambda event, payload: emitted.append({"event": event, "payload": payload}),
                    persist_session=lambda session_id: session.append(session_id),
                    cancel_event=threading.Event(),
                )
                tool_calls = [item for item in called_tools if item["name"] == "query_metrics"]
                actual_plan = None
                rows: list[dict[str, Any]] = []
                if tool_calls:
                    tool_call = tool_calls[-1]
                    args = tool_call["arguments"]
                    actual_plan = {
                        "metric_ids": args.get("metric_ids"),
                        "entity_ids": args.get("entity_ids"),
                        "periods": args.get("periods"),
                        "operation": "query",
                    }
                    if "segment" in args:
                        actual_plan.update(
                            {"dimensions": ["segment"], "filters": {"segment": args["segment"]}}
                        )
                    rows = tool_call["result"].get("rows", [])
                observation = {
                    "status": "supported" if tool_calls else "ungraded",
                    "plan": actual_plan,
                    "rows": rows,
                    "response": result.content,
                }
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
                    "quality": grade,
                }
                if result.usage_complete:
                    cost = (result.input_tokens * input_rate + result.output_tokens * output_rate) / 1_000_000
                    case_record["estimated_cost_usd"] = cost
                    model_report["estimated_cost_usd"] += cost
                    estimated_total_usd += cost
                else:
                    case_record["estimated_cost_usd"] = None
                    model_report["spent_unknown"] = True
                model_report["cases"].append(case_record)
                # Deleting local test sessions reduces retained provider state;
                # remote deletion is a best-effort provider capability, not a
                # claim that all provider logs or telemetry have been erased.
                if session:
                    try:
                        provider.delete(session[-1])
                        case_record["provider_session_delete"] = "requested"
                    except Exception:
                        case_record["provider_session_delete"] = "failed"
                        case_record["remote_retention_state"] = "unknown"
                if model_report["spent_unknown"]:
                    model_report["stopped_reason"] = "usage_unknown; no further cases admitted"
                    stop_all = True
                    break
                if estimated_total_usd >= budget_usd:
                    model_report["stopped_reason"] = "operational_budget_reached_after_current_case"
                    stop_all = True
                    break
            except Exception as exc:
                model_report["cases"].append(
                    {
                        "case_id": case["id"],
                        "status": "provider_error",
                        "error_type": type(exc).__name__,
                        "tool_calls": called_tools,
                        "session_id": session[-1] if session else None,
                        "input_tokens": None,
                        "output_tokens": None,
                        "cached_tokens": "unknown",
                        "latency_seconds": time.perf_counter() - started,
                        "model_turn_completed": False,
                        "quality": "not_scored",
                    }
                )
                model_report["spent_unknown"] = True
                model_report["stopped_reason"] = "provider_error_or_usage_unknown; no further cases admitted"
                stop_all = True
                if session:
                    try:
                        provider.delete(session[-1])
                    except Exception:
                        pass
                break
        model_report["quality_summary"] = {
            "supported_scored": sum(bool(c.get("quality", {}).get("scored")) for c in model_report["cases"]),
            "supported_passed": sum(bool(c.get("quality", {}).get("passed")) for c in model_report["cases"]),
            "safety_and_ambiguity_pending_human_review": sum(
                bool(c.get("quality", {}).get("requires_blinded_human_rubric")) for c in model_report["cases"]
            ),
            "critical_failure_gate": "pending blinded review of safety/ambiguity cases",
        }
        completed = [case for case in model_report["cases"] if case.get("model_turn_completed")]
        latencies = [float(case["latency_seconds"]) for case in completed]
        token_rows = [case for case in completed if case.get("usage_complete")]
        model_report["latency_seconds"] = {
            "completed_turn_count": len(completed),
            "p50": _nearest_rank_percentile(latencies, 0.50),
            "p95": _nearest_rank_percentile(latencies, 0.95),
        }
        model_report["token_totals"] = {
            "input_tokens": sum(case["input_tokens"] for case in token_rows)
            if len(token_rows) == len(completed)
            else None,
            "output_tokens": sum(case["output_tokens"] for case in token_rows)
            if len(token_rows) == len(completed)
            else None,
            "usage_complete_case_count": len(token_rows),
            "turn_count": len(completed),
            "cached_tokens": "unknown",
        }
        report["models"].append(model_report)
    output_dir.mkdir(parents=True, exist_ok=True)
    out = output_dir / f"chat-eval-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.json"
    report["output_path"] = str(out)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=list) + "\n", encoding="utf-8")
    return report
