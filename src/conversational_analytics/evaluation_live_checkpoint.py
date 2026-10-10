"""Durable private case checkpoints for live campaign recovery."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .evaluation_live_support import _write_private_json


def initial_report(
    *,
    probe_only: bool,
    data_version: str,
    semantic_version: str,
    models: list[str],
    run_identity: dict[str, Any] | None,
    run_identity_hash: str | None,
    campaign_identity_hash: str | None,
    budget_usd: float,
    max_tool_calls: int,
    max_turn_seconds: int,
    case_count: int,
    output_path: Path,
    progress_path: Path,
    detail_path: Path,
) -> dict[str, Any]:
    return {
        "mode": "live-probe" if probe_only else "live-evaluation",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "data_version": data_version,
        "semantic_version": semantic_version,
        "candidate_models": models,
        "run_identity": run_identity,
        "run_identity_hash": run_identity_hash or identity_sha256(run_identity),
        "campaign_identity_hash": campaign_identity_hash,
        "budget_usd_operational_stop": budget_usd,
        "budget_guaranteed": False,
        "max_tool_calls_per_turn": max_tool_calls,
        "max_turn_seconds_per_turn": max_turn_seconds,
        "probe_only": probe_only,
        "case_count": case_count,
        "models": [],
        "quality_thresholds": {"supported_accuracy_minimum": 0.95, "critical_failures_allowed": 0},
        "note": (
            "Un turno iniciado puede exceder el umbral; uso, costo y caché pueden ser desconocidos. "
            "reasoning_tokens no se expone por separado; forma parte de output_tokens."
        ),
        "output_path": str(output_path),
        "progress_path": str(progress_path),
        "case_checkpoint_path": str(detail_path),
    }


def identity_sha256(identity: dict[str, Any] | None) -> str | None:
    if identity is None:
        return None
    encoded = json.dumps(
        identity, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def write_detailed_case_checkpoint(
    path: Path, report: dict[str, Any], writer: Any = _write_private_json
) -> None:
    """Atomically persist full completed case rows before remote session deletion."""
    writer(path, report)


def finalize_report(
    path: Path,
    report: dict[str, Any],
    progress_state: dict[str, Any],
    spend: float,
    stopped: bool,
    checkpoint: Any,
    writer: Any = _write_private_json,
) -> dict[str, Any]:
    status = "stopped" if stopped else "completed"
    report["known_estimated_cost_usd"] = spend
    report["estimated_cost_usd"] = (
        None if any(model["spent_unknown"] for model in report["models"]) else spend
    )
    report["run_status"] = status
    progress_state.update(
        status="finalizing",
        current_model=None,
        known_estimated_spend_usd=spend,
        active_case_id=None,
        active_session_id=None,
        active_usage_state=None,
    )
    checkpoint()
    writer(path, report)
    progress_state["status"] = status
    checkpoint()
    return report
