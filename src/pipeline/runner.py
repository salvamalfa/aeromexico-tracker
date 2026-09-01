"""Execution engine for the central pipeline registry."""

from __future__ import annotations

from contextlib import nullcontext
from datetime import UTC, datetime
import importlib
import json
from pathlib import Path
import time
from typing import Any, Iterable
from uuid import uuid4

from src.pipeline.model import (
    InputRequirement,
    PipelinePhase,
    PipelineReport,
    PipelineRunError,
    PipelineStatus,
    PipelineStep,
    RequirementLevel,
    StepResult,
)
from src.pipeline.offline import block_network
from src.pipeline.registry import PIPELINE_STEPS


def _bronze_sources(root: Path) -> set[str]:
    manifest = root / "data" / "bronze" / "_manifest.jsonl"
    if not manifest.is_file():
        return set()
    sources: set[str] = set()
    for line_number, line in enumerate(manifest.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid Bronze manifest JSON at line {line_number}") from exc
        source = str(payload.get("source_system", "")).strip()
        source_file = root / "data" / "bronze" / str(payload.get("source_file", ""))
        if source and source_file.is_file():
            sources.add(source)
    return sources


def _matches(root: Path, pattern: str) -> list[Path]:
    return [path for path in root.glob(pattern) if path.exists()]


def _missing_input(root: Path, requirement: InputRequirement, sources: set[str]) -> str | None:
    if requirement.path_patterns:
        matched = [bool(_matches(root, pattern)) for pattern in requirement.path_patterns]
        satisfied = all(matched) if requirement.require_all_paths else any(matched)
        if not satisfied:
            absent = [pattern for pattern, found in zip(requirement.path_patterns, matched, strict=True) if not found]
            return f"{requirement.description}: missing paths {absent}"
    if requirement.bronze_source_systems and not (sources & set(requirement.bronze_source_systems)):
        return (
            f"{requirement.description}: none of Bronze source systems "
            f"{list(requirement.bronze_source_systems)} is available"
        )
    return None


def _resolve(callable_ref: str):
    module_name, attribute = callable_ref.split(":", 1)
    return getattr(importlib.import_module(module_name), attribute)


def _details(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, dict):
        return json.loads(json.dumps(value, default=str))
    if isinstance(value, int):
        return {"return_code": value}
    rows = getattr(value, "height", None)
    if rows is None:
        try:
            rows = len(value)
        except TypeError:
            rows = None
    return {"result_type": type(value).__name__, **({"rows": int(rows)} if rows is not None else {})}


def _write_report(report: PipelineReport, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(report.to_dict(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    temporary.replace(path)


def _selected_with_dependencies(
    steps: tuple[PipelineStep, ...], phases: Iterable[PipelinePhase | str] | None
) -> tuple[PipelineStep, ...]:
    if phases is None:
        return steps
    selected_phases = {PipelinePhase(phase) for phase in phases}
    selected = {step.step_id for step in steps if step.phase in selected_phases}
    changed = True
    while changed:
        changed = False
        for step in steps:
            if step.step_id in selected:
                for dependency in step.depends_on:
                    if dependency not in selected:
                        selected.add(dependency)
                        changed = True
    return tuple(step for step in steps if step.step_id in selected)


def run_pipeline(
    *,
    root: Path,
    phases: Iterable[PipelinePhase | str] | None = None,
    steps: Iterable[PipelineStep] = PIPELINE_STEPS,
    offline: bool = False,
    report_path: Path | None = None,
    run_id: str | None = None,
    include_dependencies: bool = True,
) -> PipelineReport:
    """Run selected registry phases and always emit one status per selected step."""

    root = root.resolve()
    registered = tuple(steps)
    selected = (
        _selected_with_dependencies(registered, phases)
        if include_dependencies
        else tuple(
            step
            for step in registered
            if phases is None
            or step.phase in {PipelinePhase(phase) for phase in phases}
        )
    )
    identifier = run_id or f"{datetime.now(UTC):%Y%m%dT%H%M%SZ}-{uuid4().hex[:8]}"
    receipt = report_path or root / "data" / "quality" / "pipeline_runs" / f"{identifier}.json"
    report = PipelineReport(identifier, str(root), offline, datetime.now(UTC).isoformat())
    results: dict[str, StepResult] = {}
    sources: set[str] | None = None

    guard = block_network() if offline else nullcontext()
    with guard:
        for step in selected:
            started = datetime.now(UTC)
            timer = time.perf_counter()
            status = PipelineStatus.COMPLETED
            reason = "completed"
            details: dict[str, Any] = {}

            blocked = [
                dependency
                for dependency in step.depends_on
                if dependency in results
                and results[dependency].status != PipelineStatus.COMPLETED.value
            ]
            if blocked:
                status = (
                    PipelineStatus.FAILED
                    if step.requirement == RequirementLevel.REQUIRED
                    else PipelineStatus.NOT_AVAILABLE
                )
                reason = f"blocked by dependencies: {blocked}"
            elif offline and step.network_required:
                status = (
                    PipelineStatus.FAILED
                    if step.requirement == RequirementLevel.REQUIRED
                    else PipelineStatus.NOT_AVAILABLE
                )
                reason = "network-required step selected in offline mode"
            else:
                if sources is None and step.inputs:
                    sources = _bronze_sources(root)
                missing = [
                    message
                    for requirement in step.inputs
                    if (message := _missing_input(root, requirement, sources or set()))
                ]
                if missing:
                    status = (
                        PipelineStatus.FAILED
                        if step.requirement == RequirementLevel.REQUIRED
                        else PipelineStatus.NOT_AVAILABLE
                    )
                    reason = "; ".join(missing)
                else:
                    try:
                        outcome = _resolve(step.callable_ref)()
                        details = _details(outcome)
                        if isinstance(outcome, int) and outcome != 0:
                            raise RuntimeError(f"entry point returned {outcome}")
                        if step.validate_outputs:
                            missing_outputs = [
                                pattern for pattern in step.outputs if not _matches(root, pattern)
                            ]
                            if missing_outputs:
                                raise FileNotFoundError(
                                    f"declared outputs were not produced: {missing_outputs}"
                                )
                    except Exception as exc:  # receipt captures source exception without hiding it
                        status = PipelineStatus.FAILED
                        reason = f"{type(exc).__name__}: {exc}"

            finished = datetime.now(UTC)
            result = StepResult(
                step.step_id,
                step.phase.value,
                step.requirement.value,
                status.value,
                started.isoformat(),
                finished.isoformat(),
                round((time.perf_counter() - timer) * 1000, 3),
                reason,
                details,
            )
            report.steps.append(result)
            results[step.step_id] = result
            _write_report(report, receipt)

    report.finish()
    _write_report(report, receipt)
    if report.required_failures:
        raise PipelineRunError(report, receipt)
    return report
