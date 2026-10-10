"""Private live-evaluation report and checkpoint helpers."""

from __future__ import annotations

import json
import math
import os
import tempfile
from pathlib import Path
from typing import Any

from .providers._openai_error_metadata import upstream_error_metadata

_SAFE_EXCEPTION_TYPES = frozenset(
    {
        "APIConnectionError",
        "APIError",
        "APIStatusError",
        "APITimeoutError",
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
_SAFE_REASON_CODES = frozenset(
    {
        "provider_terminal_failed",
        "provider_stream_incomplete",
        "provider_completion_without_text",
        "provider_request_failed",
        "tool_call_limit",
        "turn_timeout",
        "tool_result_limit",
    }
)
_RESERVATION_INPUT_TOKENS_PER_CASE_FLOOR = 140_000
_RESERVATION_OUTPUT_TOKENS_PER_CASE_FLOOR = 10_000


class _CheckpointWriteError(RuntimeError):
    """A private checkpoint failure must not be reclassified as provider failure."""


def _error_metadata(exc: BaseException) -> dict[str, Any]:
    """Keep only allowlisted exception class names and HTTP status metadata."""
    names: list[str] = []
    status: int | None = None
    reason_code: str | None = None
    provider_turn_id: str | None = None
    upstream: dict[str, str | int] = {}
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
        if isinstance(candidate_reason, str) and candidate_reason in _SAFE_REASON_CODES:
            reason_code = candidate_reason
        candidate_turn_id = getattr(current, "turn_id", None)
        if provider_turn_id is None and isinstance(candidate_turn_id, str) and candidate_turn_id:
            provider_turn_id = candidate_turn_id
        upstream.update(upstream_error_metadata(current))
        current = current.__cause__ or current.__context__
    result: dict[str, Any] = {"exception_types": names or ["unknown"]}
    result.update({"http_status": status} if status is not None else {})
    result.update({"reason_code": reason_code} if reason_code is not None else {})
    result.update({"provider_turn_id": provider_turn_id} if provider_turn_id is not None else {})
    result.update(upstream)
    return result


def _quality_dict(case_record: dict[str, Any]) -> dict[str, Any]:
    quality = case_record.get("quality")
    return quality if isinstance(quality, dict) else {}


def _numeric_gold_summary(
    selected: list[dict[str, Any]], case_records: list[dict[str, Any]]
) -> dict[str, Any]:
    """Keep missing, failed, and unattempted gold cases in the accuracy denominator."""
    expected = [
        case
        for case in selected
        if case.get("expected", {}).get("status") == "supported"
        and case.get("expected", {}).get("plan")
        and case.get("expected", {}).get("rows")
    ]
    reports = {str(case.get("case_id")): case for case in case_records}
    completed = sum(bool(reports.get(case["id"], {}).get("model_turn_completed")) for case in expected)
    passed = sum(
        bool(_quality_dict(reports.get(case["id"], {})).get("passed"))
        and bool(reports.get(case["id"], {}).get("model_turn_completed"))
        for case in expected
    )
    total = len(expected)
    return {
        "numeric_gold_case_count": total,
        "numeric_gold_case_completed_count": completed,
        "numeric_gold_case_passed": passed,
        "numeric_gold_accuracy": passed / total if total else None,
        "numeric_gold_coverage": completed / total if total else None,
    }


def _failure_usage(exc: BaseException) -> tuple[int, int] | None:
    usage = getattr(exc, "usage", None)
    if (
        isinstance(usage, tuple)
        and len(usage) == 2
        and all(isinstance(value, int) and not isinstance(value, bool) and value >= 0 for value in usage)
    ):
        return usage
    return None


def _apply_provider_cancel_outcome(
    case_record: dict[str, Any],
    progress_state: dict[str, Any],
    error: BaseException,
    provider: Any,
    session_id: str | None,
) -> str:
    """Persist cancellation certainty and retain sessions without replay."""
    if getattr(error, "deadline_watchdog_fired", False):
        snapshot = getattr(error, "cancel_outcome", None)
        try:
            outcome = snapshot() if callable(snapshot) else {}
        except Exception as exc:
            outcome = {"status": "unknown_manual_reconciliation", "error": exc}
        if not isinstance(outcome, dict):
            outcome = {}
        status = outcome.get("status")
        if not isinstance(status, str):
            status = "unknown_manual_reconciliation"
        cancel_error = outcome.get("error")
        if isinstance(cancel_error, BaseException):
            case_record["provider_cancel_error_metadata"] = _error_metadata(cancel_error)
        elif isinstance(outcome.get("error_metadata"), dict):
            case_record["provider_cancel_error_metadata"] = outcome["error_metadata"]
    elif session_id and callable(getattr(provider, "cancel", None)):
        try:
            outcome = provider.cancel(session_id)
            if isinstance(outcome, dict) and isinstance(outcome.get("status"), str):
                status = outcome["status"]
                if isinstance(outcome.get("error_metadata"), dict):
                    case_record["provider_cancel_error_metadata"] = outcome["error_metadata"]
            elif outcome is False:
                status = "failed_manual_reconciliation"
            else:
                status = "cancelled"
        except Exception as exc:
            status = "failed_manual_reconciliation"
            case_record["provider_cancel_error_metadata"] = _error_metadata(exc)
    else:
        status = "unavailable_manual_reconciliation"
    case_record["provider_cancel"] = status
    progress_state["provider_cancel_state"] = status
    if session_id and status != "cancelled":
        progress_state["session_to_reconcile"] = session_id
        progress_state["manual_cancel_required"] = True
    return status


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
        "provider_cancel_state": state.get("provider_cancel_state"),
        "manual_cancel_required": bool(state.get("manual_cancel_required")),
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
