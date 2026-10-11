"""Bounded, single-request provider cancellation helpers."""

from __future__ import annotations

from typing import Any

from ._openai_error_metadata import upstream_error_metadata


def cancel_session(client: Any, session_id: str, timeout: float) -> dict[str, Any]:
    if not session_id:
        return {"status": "unavailable_manual_reconciliation"}
    with_options = getattr(client, "with_options", None)
    if callable(with_options):
        client = with_options(timeout=timeout, max_retries=0)
    try:
        client.beta.agents.sessions.events.create(
            session_id,
            events=[{"type": "agent.session.input.cancel"}],
            timeout=timeout,
        )
    except Exception as exc:
        return {"status": "failed_manual_reconciliation", "error_metadata": upstream_error_metadata(exc)}
    return {"status": "cancelled"}
