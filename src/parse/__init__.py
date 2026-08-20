"""Bronze-to-silver parsers registered by source stage."""


def run() -> None:
    from src.parse.bmv.pipeline import main as run_bmv_parser
    from src.parse.sec.pipeline import main as run_sec_parser

    if run_sec_parser() != 0:
        raise RuntimeError("SEC parse failed")
    if run_bmv_parser() != 0:
        raise RuntimeError("BMV parse failed")
