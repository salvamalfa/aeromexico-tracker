"""Bronze-to-silver parsers registered by source stage."""


def run() -> None:
    from src.parse.afac.monthly_stats import main as run_afac_parser
    from src.parse.bmv.pipeline import main as run_bmv_parser
    from src.parse.sec.pipeline import main as run_sec_parser
    from src.parse.stage4 import main as run_stage4_parser

    if run_sec_parser() != 0:
        raise RuntimeError("SEC parse failed")
    if run_bmv_parser() != 0:
        raise RuntimeError("BMV parse failed")
    if run_afac_parser() != 0:
        raise RuntimeError("AFAC parse failed")
    if run_stage4_parser() != 0:
        raise RuntimeError("Stage 4 parse failed")
