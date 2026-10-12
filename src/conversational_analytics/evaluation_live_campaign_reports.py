"""Private immutable report-fragment validation and consolidation for campaigns."""

from __future__ import annotations

import hashlib
import json
import stat
from pathlib import Path
from typing import Any, Mapping, Sequence

from .evaluation_live import _write_private_json


def _canonical_hash(value: Any) -> str:
    encoded = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _model_candidate_id(run: Mapping[str, Any]) -> str:
    model = str(run.get("model", ""))
    effort = str(run.get("reasoning_effort", ""))
    verbosity = str(run.get("text_verbosity", ""))
    return f"{model}@{effort}@{verbosity}"


def _private_fragment_path(path_value: Any, run_dir: Path) -> tuple[Path, str]:
    path = Path(str(path_value)).resolve(strict=True)
    root = run_dir.resolve(strict=True)
    if root not in path.parents or not path.is_file():
        raise ValueError("Resume bloqueado: fragmento fuera del directorio privado de corrida")
    if stat.S_IMODE(path.stat().st_mode) & 0o077:
        raise ValueError("Resume bloqueado: fragmento detallado sin permisos privados")
    return path, hashlib.sha256(path.read_bytes()).hexdigest()


def _fragment_record(
    report: Mapping[str, Any],
    run_dir: Path,
    run: Mapping[str, Any],
    campaign_identity_hash: str,
) -> dict[str, Any] | None:
    """Pin an immutable detailed report fragment produced by the live runner."""
    report_path_value = report.get("output_path")
    if not report_path_value or not Path(str(report_path_value)).is_file():
        return None
    source_path = Path(str(report_path_value)).resolve()
    if run_dir.resolve() not in source_path.parents:
        return None
    report_path, report_sha = _private_fragment_path(report_path_value, run_dir)
    detail_path_value = report.get("case_checkpoint_path")
    detail_path: Path | None = None
    detail_sha: str | None = None
    if detail_path_value:
        detail_path, detail_sha = _private_fragment_path(detail_path_value, run_dir)
    else:
        raise ValueError("El reporte live no incluye checkpoint detallado")
    identity = dict(run["identity"])
    persisted_report = json.loads(report_path.read_text(encoding="utf-8"))
    model_rows = persisted_report.get("models")
    if (
        persisted_report.get("mode") != "live-evaluation"
        or persisted_report.get("probe_only") is not False
        or persisted_report.get("run_identity") != identity
        or persisted_report.get("run_identity_hash") != run.get("identity_hash")
        or persisted_report.get("campaign_identity_hash") != campaign_identity_hash
        or _canonical_hash(identity) != run.get("identity_hash")
        or not isinstance(model_rows, list)
        or len(model_rows) != 1
    ):
        raise ValueError("El fragmento detallado no conserva la identidad de ejecución")
    expected_data = identity.get("snapshot_data_version", identity.get("data_version"))
    expected_semantic = identity.get("snapshot_semantic_version", identity.get("semantic_version"))
    if (
        (expected_data is not None and persisted_report.get("data_version") != expected_data)
        or (expected_semantic is not None and persisted_report.get("semantic_version") != expected_semantic)
    ):
        raise ValueError("El fragmento detallado no conserva las versiones fijadas")
    model = model_rows[0]
    if model.get("candidate_id") not in (None, _model_candidate_id(run)):
        raise ValueError("El fragmento detallado contiene otro candidato")
    case_rows = model.get("cases")
    if not isinstance(case_rows, list):
        raise ValueError("El fragmento detallado no contiene casos")
    case_ids = [str(case.get("case_id")) for case in case_rows]
    if len(case_ids) != len(set(case_ids)) or not set(case_ids) <= set(run["case_ids"]):
        raise ValueError("El fragmento detallado repite o altera IDs de caso")
    if detail_path:
        detail = json.loads(detail_path.read_text(encoding="utf-8"))
        detail_models = detail.get("models")
        if (
            detail.get("run_identity") != identity
            or detail.get("run_identity_hash") != run.get("identity_hash")
            or detail.get("campaign_identity_hash") != campaign_identity_hash
            or not isinstance(detail_models, list)
            or len(detail_models) != 1
            or _canonical_hash(detail_models[0].get("cases", [])) != _canonical_hash(case_rows)
        ):
            raise ValueError("El checkpoint detallado no conserva identidad y filas del reporte")
    return {
        "report_path": report_path.name,
        "report_sha256": report_sha,
        "detail_path": detail_path.name if detail_path else None,
        "detail_sha256": detail_sha,
        "case_ids": case_ids,
    }


def _load_fragment_cases(
    fragments: Sequence[Mapping[str, Any]],
    *,
    run_dir: Path,
    run: Mapping[str, Any],
    campaign_identity_hash: str,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    expected_identity = dict(run["identity"])
    for fragment in fragments:
        report_path, report_sha = _private_fragment_path(
            run_dir / str(fragment.get("report_path", "")), run_dir
        )
        if report_sha != fragment.get("report_sha256"):
            raise ValueError("Resume bloqueado: cambió el hash del fragmento detallado")
        report = json.loads(report_path.read_text(encoding="utf-8"))
        if (
            report.get("run_identity") != expected_identity
            or report.get("run_identity_hash") != run.get("identity_hash")
            or report.get("campaign_identity_hash") != campaign_identity_hash
            or _canonical_hash(expected_identity) != run.get("identity_hash")
        ):
            raise ValueError("Resume bloqueado: fragmento detallado con identidad distinta")
        detail_name = fragment.get("detail_path")
        if detail_name:
            detail_path, detail_sha = _private_fragment_path(run_dir / str(detail_name), run_dir)
            if detail_sha != fragment.get("detail_sha256"):
                raise ValueError("Resume bloqueado: cambió el hash del checkpoint detallado")
            detail = json.loads(detail_path.read_text(encoding="utf-8"))
            if (
                detail.get("run_identity") != expected_identity
                or detail.get("run_identity_hash") != run.get("identity_hash")
                or detail.get("campaign_identity_hash") != campaign_identity_hash
            ):
                raise ValueError("Resume bloqueado: checkpoint detallado con identidad distinta")
        model_rows = report.get("models")
        if not isinstance(model_rows, list) or len(model_rows) != 1:
            raise ValueError("Resume bloqueado: fragmento sin candidato único")
        if model_rows[0].get("candidate_id") not in (None, _model_candidate_id(run)):
            raise ValueError("Resume bloqueado: fragmento de otro candidato")
        cases = model_rows[0].get("cases")
        if not isinstance(cases, list):
            raise ValueError("Resume bloqueado: fragmento sin filas detalladas")
        if detail_name:
            detail_cases = detail["models"][0].get("cases")
            if _canonical_hash(detail_cases) != _canonical_hash(cases):
                raise ValueError("Resume bloqueado: report y checkpoint contienen detalles distintos")
        ids = [str(case.get("case_id")) for case in cases]
        if ids != fragment.get("case_ids"):
            raise ValueError("Resume bloqueado: cambió el contenido del fragmento detallado")
        rows.extend(cases)
    ids = [str(case.get("case_id")) for case in rows]
    if len(ids) != len(set(ids)):
        raise ValueError("Resume bloqueado: fragmentos detallados se solapan")
    planned_order = [case_id for case_id in run["case_ids"] if case_id in set(ids)]
    if ids != planned_order:
        raise ValueError("Resume bloqueado: el orden de casos detallados no coincide con el plan")
    return rows


def _consolidate_report(
    *,
    report: Mapping[str, Any],
    detailed_cases: list[dict[str, Any]],
    all_cases: list[dict[str, Any]],
    run: Mapping[str, Any],
    complete: bool,
    run_dir: Path,
    fragments: Sequence[Mapping[str, Any]],
    fixture_cases: Sequence[Mapping[str, Any]],
) -> tuple[str, str]:
    """Write a content-addressed consolidated report without changing fragments."""
    consolidated = json.loads(json.dumps(report, ensure_ascii=False, default=list))
    model = consolidated["models"][0]
    detailed_by_id = {str(case["case_id"]): case for case in detailed_cases}
    ordered_ids = [case_id for case_id in run["case_ids"] if case_id in detailed_by_id]
    model["cases"] = [detailed_by_id[case_id] for case_id in ordered_ids]
    model["case_count"] = len(ordered_ids)
    model["known_estimated_cost_usd"] = sum(
        float(
            case.get("estimated_cost_usd")
            if case.get("estimated_cost_usd") is not None
            else case.get("known_estimated_cost_lower_bound_usd", 0.0)
        )
        for case in all_cases
    )
    model["spent_unknown"] = any(
        case.get("usage_complete") is not True
        for case in all_cases
        if case.get("provider_turn_started")
    )
    model["estimated_cost_usd"] = (
        None if model["spent_unknown"] else model["known_estimated_cost_usd"]
    )
    from .evaluation_live_support import _nearest_rank_percentile, _numeric_gold_summary

    fixture_by_id = {str(case["id"]): case for case in fixture_cases}
    selected = [fixture_by_id[case_id] for case_id in ordered_ids]
    numeric = _numeric_gold_summary(selected, model["cases"])
    tripwires = [
        case for case in model["cases"]
        if case.get("quality", {}).get("automatic_grade_type") in {"tripwire", "multi_turn_tripwires"}
        and case.get("quality", {}).get("scored")
    ]
    model["quality_summary"] = {
        **numeric,
        "tripwire_case_count": len(tripwires),
        "tripwire_case_passed": sum(bool(case.get("quality", {}).get("passed")) for case in tripwires),
        "human_review_pending_case_count": sum(
            bool(case.get("quality", {}).get("requires_blinded_human_rubric"))
            for case in model["cases"]
        ),
        "critical_failure_gate": "pending blinded owner review of every rubric item",
    }
    attempted = [case for case in model["cases"] if case.get("provider_turn_started")]
    token_rows = [case for case in attempted if case.get("usage_complete")]
    model["token_totals"] = {
        "input_tokens": sum(case["input_tokens"] for case in token_rows)
        if len(token_rows) == len(attempted) else None,
        "output_tokens": sum(case["output_tokens"] for case in token_rows)
        if len(token_rows) == len(attempted) else None,
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
    completed = [case for case in model["cases"] if case.get("model_turn_completed")]
    latencies = [
        float(case["latency_seconds"])
        for case in completed
        if isinstance(case.get("latency_seconds"), (int, float))
    ]
    model["latency_seconds"] = {
        "completed_turn_count": len(completed),
        "p50": _nearest_rank_percentile(latencies, 0.50),
        "p90": _nearest_rank_percentile(latencies, 0.90),
        "p95": _nearest_rank_percentile(latencies, 0.95),
        "percentile_method": (
            "nearest rank; p95 retained for compatibility, p90 is the proposed decision metric"
        ),
    }
    if complete:
        model.pop("stopped_reason", None)
    consolidated["case_count"] = len(ordered_ids)
    consolidated["run_status"] = "completed" if complete else "stopped"
    consolidated["known_estimated_cost_usd"] = model["known_estimated_cost_usd"]
    consolidated["estimated_cost_usd"] = model["estimated_cost_usd"]
    consolidated["source_report_fragments"] = [dict(item) for item in fragments]
    encoded = (json.dumps(consolidated, ensure_ascii=False, indent=2, default=list) + "\n").encode("utf-8")
    report_sha = hashlib.sha256(encoded).hexdigest()
    path = run_dir / f"{run['run_id']}.consolidated-{report_sha}.json"
    if path.exists():
        if path.read_bytes() != encoded:
            raise ValueError("El reporte consolidado existente no coincide con su hash")
    else:
        _write_private_json(path, consolidated)
    return str(path), hashlib.sha256(path.read_bytes()).hexdigest()
