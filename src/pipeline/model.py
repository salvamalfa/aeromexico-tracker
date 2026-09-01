"""Typed public model for pipeline registration and execution receipts."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any


class PipelinePhase(StrEnum):
    INGEST = "ingest"
    PARSE = "parse"
    TRANSFORM = "transform"
    ANALYTICS = "analytics"
    DASHBOARD = "dashboard"


class RequirementLevel(StrEnum):
    REQUIRED = "required"
    OPTIONAL = "optional"


class PipelineStatus(StrEnum):
    COMPLETED = "completed"
    FAILED = "failed"
    NOT_AVAILABLE = "not_available"


@dataclass(frozen=True, slots=True)
class InputRequirement:
    """One logical input, satisfied by paths and/or Bronze source systems."""

    description: str
    path_patterns: tuple[str, ...] = ()
    bronze_source_systems: tuple[str, ...] = ()
    require_all_paths: bool = False

    def __post_init__(self) -> None:
        if not self.path_patterns and not self.bronze_source_systems:
            raise ValueError(f"Input requirement has no checks: {self.description}")


@dataclass(frozen=True, slots=True)
class PipelineStep:
    step_id: str
    phase: PipelinePhase
    description: str
    callable_ref: str
    requirement: RequirementLevel
    inputs: tuple[InputRequirement, ...]
    outputs: tuple[str, ...]
    depends_on: tuple[str, ...] = ()
    network_required: bool = False
    validate_outputs: bool = True

    def __post_init__(self) -> None:
        if ":" not in self.callable_ref:
            raise ValueError(f"Invalid callable reference for {self.step_id}")
        if not isinstance(self.inputs, tuple) or not all(
            isinstance(item, InputRequirement) for item in self.inputs
        ):
            raise TypeError(
                f"Pipeline step inputs must be a tuple of InputRequirement: {self.step_id}"
            )
        if not self.outputs:
            raise ValueError(f"Pipeline step must declare outputs: {self.step_id}")


@dataclass(frozen=True, slots=True)
class StepResult:
    step_id: str
    phase: str
    requirement: str
    status: str
    started_at: str
    finished_at: str
    duration_ms: float
    reason: str
    details: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class PipelineReport:
    run_id: str
    root: str
    offline: bool
    started_at: str
    finished_at: str | None = None
    status: str = PipelineStatus.COMPLETED.value
    steps: list[StepResult] = field(default_factory=list)

    @property
    def required_failures(self) -> list[StepResult]:
        return [
            result
            for result in self.steps
            if result.requirement == RequirementLevel.REQUIRED.value
            and result.status != PipelineStatus.COMPLETED.value
        ]

    def finish(self) -> None:
        self.finished_at = datetime.now(UTC).isoformat()
        if self.required_failures:
            self.status = PipelineStatus.FAILED.value

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class PipelineRunError(RuntimeError):
    """Raised after a complete receipt is written for required-step failures."""

    def __init__(self, report: PipelineReport, report_path: Path | None = None) -> None:
        failures = ", ".join(
            f"{item.step_id}: {item.reason}" for item in report.required_failures
        )
        location = f" Receipt: {report_path}" if report_path else ""
        super().__init__(f"Required pipeline steps failed: {failures}.{location}")
        self.report = report
        self.report_path = report_path
