import json
import logging
from pathlib import Path

from src.common.logging import configure_logging, log_event


def test_json_log_contains_structured_request_fields(tmp_path: Path) -> None:
    target = tmp_path / "pipeline.jsonl"
    logger = configure_logging(json_log_path=target, force=True)

    log_event(
        logger,
        logging.INFO,
        "ingest_complete",
        source="sec",
        status=200,
        bytes=128,
        duration_ms=12.5,
        attempt=1,
    )
    for handler in logging.getLogger().handlers:
        handler.flush()

    payload = json.loads(target.read_text(encoding="utf-8").strip())
    assert payload["event"] == "ingest_complete"
    assert payload["source"] == "sec"
    assert payload["status"] == 200
    assert payload["bytes"] == 128
    assert payload["attempt"] == 1
    assert payload["timestamp"].endswith("+00:00")
