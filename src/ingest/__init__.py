"""Network ingestion through the project-wide declarative registry."""

from src.config import PATHS
from src.pipeline import PipelinePhase, PipelineReport, run_pipeline


def run() -> PipelineReport:
    return run_pipeline(
        root=PATHS.root,
        phases=(PipelinePhase.INGEST,),
        offline=False,
        include_dependencies=False,
    )
