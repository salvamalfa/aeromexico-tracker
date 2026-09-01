"""Silver-to-Gold transformations through the central registry."""

from src.config import PATHS
from src.pipeline import PipelinePhase, PipelineReport, run_pipeline


def run() -> PipelineReport:
    return run_pipeline(
        root=PATHS.root,
        phases=(PipelinePhase.TRANSFORM,),
        offline=True,
        include_dependencies=False,
    )
