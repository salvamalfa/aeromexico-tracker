"""Offline Bronze-to-Silver parsing through the central registry."""

from src.config import PATHS
from src.pipeline import PipelinePhase, PipelineReport, run_pipeline


def run() -> PipelineReport:
    return run_pipeline(
        root=PATHS.root,
        phases=(PipelinePhase.PARSE,),
        offline=True,
        include_dependencies=False,
    )
