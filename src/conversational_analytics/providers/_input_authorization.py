"""Authorization boundary for provider-side input writes."""

from __future__ import annotations

from typing import Any, Callable

InputAuthorizer = Callable[[], None]


def send_tool_result(
    client: Any,
    session_id: str,
    turn_id: str,
    call_id: str,
    *,
    success: bool,
    output: str | None = None,
    error: str | None = None,
    authorize_input: InputAuthorizer | None = None,
) -> None:
    payload: dict[str, Any] = {
        "type": "agent.session.input.tool_result",
        "turn_id": turn_id,
        "call_id": call_id,
        "success": success,
    }
    if success:
        payload["output"] = output or "{}"
    else:
        payload["error"] = error or "La herramienta no pudo completar la consulta."
    if authorize_input is not None:
        authorize_input()
    client.beta.agents.sessions.events.create(
        session_id,
        idempotency_key=f"airline-tracker-tool-{turn_id}-{call_id}",
        events=[payload],
    )
