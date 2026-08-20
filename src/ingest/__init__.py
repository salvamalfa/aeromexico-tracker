"""Network ingestion pipelines registered by source stage."""


def run() -> None:
    from src.ingest.sec.discover import main as run_sec_discovery

    if run_sec_discovery() != 0:
        raise RuntimeError("SEC ingestion failed")
