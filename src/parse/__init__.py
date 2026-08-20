"""Bronze-to-silver parsers registered by source stage."""


def run() -> None:
    from src.parse.sec.pipeline import main as run_sec_parser

    if run_sec_parser() != 0:
        raise RuntimeError("SEC parse failed")
