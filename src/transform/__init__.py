"""Silver-to-gold transformations registered by stage."""

from src.config import PATHS


def run() -> None:
    from src.transform.stage4 import run as run_stage4
    from src.transform.validate_stage4 import run as validate_stage4

    run_stage4()
    validate_stage4()
    if (
        (PATHS.silver / "peer_operating_metrics.parquet").exists()
        and (PATHS.silver / "bts_t100_segment.parquet").exists()
    ):
        from src.transform.validate_stage5 import validate_stage5

        validate_stage5()
