"""Shared exceptions and clock utility for private storage modules."""

from __future__ import annotations

from datetime import UTC, datetime


def utcnow() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds")


class ChatError(Exception):
    """Base for expected service errors."""


class NotFound(ChatError):
    pass


class Conflict(ChatError):
    pass


class AdmissionDenied(ChatError):
    pass
