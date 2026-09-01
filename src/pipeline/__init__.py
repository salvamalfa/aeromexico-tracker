"""Declarative orchestration for the Aeromexico data pipeline."""

from src.pipeline.model import (
    PipelinePhase,
    PipelineReport,
    PipelineRunError,
    PipelineStatus,
    RequirementLevel,
)
from src.pipeline.registry import PIPELINE_STEPS, steps_for_phases
from src.pipeline.runner import run_pipeline

__all__ = [
    "PIPELINE_STEPS",
    "PipelinePhase",
    "PipelineReport",
    "PipelineRunError",
    "PipelineStatus",
    "RequirementLevel",
    "run_pipeline",
    "steps_for_phases",
]
