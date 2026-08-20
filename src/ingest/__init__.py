"""Network ingestion pipelines registered by source stage."""


def run() -> None:
    from src.ingest.afac.download import main as run_afac_download
    from src.ingest.bmv.download import main as run_bmv_download
    from src.ingest.sec.discover import main as run_sec_discovery

    if run_sec_discovery() != 0:
        raise RuntimeError("SEC ingestion failed")
    if run_bmv_download() != 0:
        raise RuntimeError("BMV ingestion failed")
    if run_afac_download() != 0:
        raise RuntimeError("AFAC ingestion failed")
