"""Structured JSON file logging with a concise human-readable console."""

from __future__ import annotations

from datetime import UTC, datetime
import json
import logging
from pathlib import Path
import sys
from typing import Any

from src.config import PATHS


class JsonFormatter(logging.Formatter):
    """Serialize stable log fields plus explicit event data as one JSON object."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        event_data = getattr(record, "event_data", None)
        if isinstance(event_data, dict):
            payload.update(event_data)
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)


def configure_logging(
    *,
    level: int = logging.INFO,
    json_log_path: Path | None = None,
    force: bool = False,
) -> logging.Logger:
    """Configure root logging once and return the project logger."""

    root = logging.getLogger()
    if root.handlers and not force:
        return logging.getLogger("aeromexico_tracker")

    if force:
        for handler in root.handlers[:]:
            handler.close()
            root.removeHandler(handler)

    root.setLevel(level)

    console = logging.StreamHandler(sys.stderr)
    console.setLevel(level)
    console.setFormatter(
        logging.Formatter(
            fmt="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
            datefmt="%Y-%m-%dT%H:%M:%S",
        )
    )
    root.addHandler(console)

    target = json_log_path or (PATHS.logs / "pipeline.jsonl")
    target.parent.mkdir(parents=True, exist_ok=True)
    json_handler = logging.FileHandler(target, encoding="utf-8")
    json_handler.setLevel(level)
    json_handler.setFormatter(JsonFormatter())
    root.addHandler(json_handler)

    return logging.getLogger("aeromexico_tracker")


def log_event(
    logger: logging.Logger,
    level: int,
    event: str,
    **fields: Any,
) -> None:
    """Emit a structured event without leaking arbitrary LogRecord attributes."""

    logger.log(level, event, extra={"event_data": {"event": event, **fields}})
