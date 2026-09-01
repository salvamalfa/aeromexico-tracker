"""Small adapters where legacy entry points do not expose one offline action."""

from __future__ import annotations

from pathlib import Path

from src.config import PATHS


def rebuild_peer_discovery() -> dict[str, object]:
    """Recreate peer SEC indexes from cached Bronze; the offline guard blocks gaps."""

    from src.ingest.peers.stage5 import rebuild_sec_peers_from_bronze

    return rebuild_sec_peers_from_bronze()


def parse_peer_reports() -> dict[str, object]:
    """Build peer facts explicitly even when SEC parsing already refreshed them."""

    from src.parse.peers.stage5 import build_peer_metrics

    return build_peer_metrics()


def parse_bts() -> dict[str, object]:
    from src.parse.bts.t100 import build_t100

    frame, crosswalk = build_t100()
    return {"rows": frame.height, "carriers": crosswalk.height}


def ingest_afac() -> int:
    from src.ingest.afac.download import main

    return main()


def ingest_loughran_mcdonald() -> int:
    from src.ingest.nlp.loughran_mcdonald import main

    return main()


def existing_path_summary(path: str) -> dict[str, object]:
    """Testing/debug adapter kept deliberately side-effect free."""

    target = Path(path)
    return {"path": target.as_posix(), "exists": target.exists(), "root": str(PATHS.root)}
