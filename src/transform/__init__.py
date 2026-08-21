"""Silver-to-gold transformations registered by stage."""


def run() -> None:
    from src.transform.stage4 import run as run_stage4
    from src.transform.validate_stage4 import run as validate_stage4

    run_stage4()
    validate_stage4()
