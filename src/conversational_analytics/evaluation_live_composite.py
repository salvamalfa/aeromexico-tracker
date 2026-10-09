"""Private report composition with exact case rows and nonduplicated totals."""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any, Mapping, Sequence

from .evaluation_live_reconciliation import _finite_cost, _tool_limit_terminal
from .evaluation_live_support import _numeric_gold_summary, _quality_dict


def _merge_private_reports(
    *,
    report_paths: Sequence[str],
    expected_identity: Mapping[str, Any],
    expected_case_ids: Sequence[str],
    cases: Sequence[Mapping[str, Any]],
    output_path: Path,
) -> tuple[str, list[str]]:
    """Create one owner-only report from immutable run parts, retaining rows verbatim."""
    rows: list[dict[str, Any]] = []
    part_hashes: list[str] = []
    header: dict[str, Any] | None = None
    for name in report_paths:
        source = Path(name)
        raw = source.read_bytes()
        report = json.loads(raw)
        if report.get("run_identity") != expected_identity:
            raise ValueError("Composite bloqueado: identidad de parte distinta")
        models = report.get("models")
        if (
            not isinstance(models, list)
            or len(models) != 1
            or models[0].get("run_identity") != expected_identity
        ):
            raise ValueError("Composite bloqueado: candidato de parte distinto")
        if header is None:
            header = report
        part_hashes.append(hashlib.sha256(raw).hexdigest())
        rows.extend(models[0].get("cases", []))
    ids = [str(row.get("case_id")) for row in rows]
    if ids != list(map(str, expected_case_ids)) or len(ids) != len(set(ids)):
        raise ValueError("Composite bloqueado: cobertura o unicidad de casos no coincide")
    assert header is not None
    model = dict(header["models"][0])
    model["cases"] = rows
    attempted = [row for row in rows if row.get("provider_turn_started") is True]
    costs = [_finite_cost(row.get("estimated_cost_usd")) for row in attempted]
    if any(value is None for value in costs):
        raise ValueError("Composite bloqueado: costo iniciado desconocido")
    total = sum(value for value in costs if value is not None)
    completed = [row for row in rows if row.get("model_turn_completed") is True]
    latencies = [
        float(row["latency_seconds"])
        for row in completed
        if isinstance(row.get("latency_seconds"), (int, float))
        and not isinstance(row.get("latency_seconds"), bool)
    ]
    usage_rows = [row for row in attempted if row.get("usage_complete") is True]
    input_tokens = [row.get("input_tokens") for row in usage_rows]
    output_tokens = [row.get("output_tokens") for row in usage_rows]
    all_usage_known = len(usage_rows) == len(attempted)
    token_totals = dict(model.get("token_totals", {}))
    token_totals.update(
        input_tokens=sum(v for v in input_tokens if isinstance(v, int) and not isinstance(v, bool))
        if all_usage_known
        and input_tokens
        and all(isinstance(v, int) and not isinstance(v, bool) for v in input_tokens)
        else None,
        output_tokens=sum(v for v in output_tokens if isinstance(v, int) and not isinstance(v, bool))
        if all_usage_known
        and output_tokens
        and all(isinstance(v, int) and not isinstance(v, bool) for v in output_tokens)
        else None,
        known_input_tokens_lower_bound=sum(
            v
            for v in (row.get("input_tokens") for row in attempted)
            if isinstance(v, int) and not isinstance(v, bool)
        ),
        known_output_tokens_lower_bound=sum(
            v
            for v in (row.get("output_tokens") for row in attempted)
            if isinstance(v, int) and not isinstance(v, bool)
        ),
        usage_complete_case_count=sum(row.get("usage_complete") is True for row in attempted),
        turn_count=len(attempted),
        cached_tokens="unknown",
        reasoning_tokens="unknown; included in output_tokens",
    )
    model.update(
        known_estimated_cost_usd=total,
        estimated_cost_usd=total,
        spent_unknown=False,
        token_totals=token_totals,
        latency_seconds={
            "completed_turn_count": len(completed),
            "p50": _percentile(latencies, 0.5),
            "p90": _percentile(latencies, 0.9),
            "p95": _percentile(latencies, 0.95),
            "percentile_method": "nearest rank",
        },
        technical_case_count=len(rows),
        model_turn_completed_count=len(completed),
        terminal_error_count=sum(_tool_limit_terminal(row) for row in rows),
        human_rubric_pending_count=sum(
            bool(_quality_dict(row).get("requires_blinded_human_rubric")) for row in rows
        ),
        quality_review_status="pending_human_review",
        planned_user_message_count=sum(len(case.get("turns", [case.get("question")])) for case in cases),
    )
    numeric = _numeric_gold_summary([dict(case) for case in cases], rows)
    tripwires = [
        row
        for row in rows
        if _quality_dict(row).get("automatic_grade_type") in {"tripwire", "multi_turn_tripwires"}
        and _quality_dict(row).get("scored")
    ]
    model["quality_summary"] = {
        **numeric,
        "tripwire_case_count": len(tripwires),
        "tripwire_case_passed": sum(bool(_quality_dict(row).get("passed")) for row in tripwires),
        "human_rubric_pending_count": sum(
            bool(_quality_dict(row).get("requires_blinded_human_rubric")) for row in rows
        ),
        "review_status": "pending_human_review",
    }
    composite = dict(header)
    composite.update(
        run_status="technically_closed_with_terminal_case_errors"
        if model["terminal_error_count"]
        else "completed",
        output_path=str(output_path),
        progress_path=None,
        case_count=len(rows),
        estimated_cost_usd=total,
        known_estimated_cost_usd=total,
        composite_parts=[{"path": path, "sha256": digest} for path, digest in zip(report_paths, part_hashes)],
        composite_cost_basis="sum of each unique provider-started case exactly once",
        technical_completion="closed",
        provider_invoice_status="not_reconciled",
        models=[model],
        quality_review_status="pending_human_review",
    )
    from .evaluation_live import _write_private_json

    _write_private_json(output_path, composite)
    return hashlib.sha256(output_path.read_bytes()).hexdigest(), part_hashes


def _percentile(values: Sequence[float], percentile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    return float(ordered[max(0, math.ceil(len(ordered) * percentile) - 1)])
