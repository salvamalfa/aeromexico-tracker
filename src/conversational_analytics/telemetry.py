"""Structured chat telemetry with an explicit low-risk field allowlist."""

from __future__ import annotations

import logging
from typing import Any

_ALLOWED = {
    "event",
    "turn_id",
    "conversation_id",
    "provider",
    "status",
    "error_code",
    "input_tokens",
    "output_tokens",
    "estimated_cost_usd",
    "duration_ms",
    "tool_name",
}


def log_chat_event(logger: logging.Logger, **fields: Any) -> None:
    """Log only operational identifiers and numeric usage; omit prompts/secrets."""
    safe = {key: value for key, value in fields.items() if key in _ALLOWED}
    logger.info("chat_event", extra={"chat": safe})


__all__ = ["log_chat_event"]
