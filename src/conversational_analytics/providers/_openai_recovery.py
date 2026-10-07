"""Read-only recovery helpers for the official Agents API provider."""

from __future__ import annotations

from typing import Any

from ._openai_helpers import field, to_dict


def retrieve_completed_turn_output(client: Any, session_id: str, turn_id: str) -> str:
    """Read only final-answer text from a complete page for this exact turn."""
    page = client.beta.agents.sessions.items.list(session_id, limit=100, order="desc")
    if field(page, "has_more") is True:
        return ""
    items = list(getattr(page, "data", []))
    assistant_messages: list[dict[str, Any]] = []
    for item in reversed(items):
        data = to_dict(item)
        if (
            data.get("turn_id") != turn_id
            or data.get("type") != "message"
            or data.get("role") != "assistant"
        ):
            continue
        assistant_messages.append(data)
    # Older item schemas omit phase. For those completed turns, use only the
    # last assistant message overall, while preferring explicit final answers.
    final_messages = [
        message
        for message in assistant_messages
        if message.get("phase") == "final_answer" and message.get("status") == "completed"
    ]
    selected = final_messages
    if not selected and assistant_messages:
        last_message = assistant_messages[-1]
        if last_message.get("phase") is None and last_message.get("status") == "completed":
            selected = [last_message]
    output: list[str] = []
    for message in selected:
        content_parts = message.get("content", [])
        if not isinstance(content_parts, list):
            continue
        for content in content_parts:
            part = to_dict(content)
            text = part.get("text")
            if part.get("type") in {"output_text", "text"} and isinstance(text, str):
                output.append(text)
    return "".join(output).strip()
