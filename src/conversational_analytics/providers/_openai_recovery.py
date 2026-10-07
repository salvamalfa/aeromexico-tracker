"""Read-only recovery helpers for the official Agents API provider."""

from __future__ import annotations

import time
from typing import Any

from ._openai_helpers import field, to_dict


def read_exact_turn_items(client: Any, session_id: str, turn_id: str) -> list[dict[str, Any]] | None:
    """Read the exact root turn across bounded cursor pages, oldest first.

    The SDK exposes item pagination by ID, not a turn-ID query filter. Descending
    pages let us fail if a newer turn is present, then stop at the first older
    turn after collecting the target's contiguous item run.
    """
    if not session_id or not turn_id:
        return None
    deadline = time.monotonic() + 30.0
    cursor: str | None = None
    total_items = 0
    exact_desc: list[dict[str, Any]] = []
    seen_item_ids: set[str] = set()
    saw_target = False
    for _ in range(10):
        remaining = deadline - time.monotonic()
        if remaining <= 0 or total_items >= 1000:
            return None
        query: dict[str, Any] = {
            "limit": min(100, 1000 - total_items),
            "order": "desc",
            "timeout": min(5.0, remaining),
        }
        if cursor is not None:
            query["after"] = cursor
        try:
            page = client.beta.agents.sessions.items.list(session_id, **query)
        except Exception:
            return None
        data = field(page, "data")
        has_more = field(page, "has_more")
        if not isinstance(data, (list, tuple)) or not isinstance(has_more, bool):
            return None
        if not data:
            return list(reversed(exact_desc)) if saw_target and not has_more else None
        page_items: list[dict[str, Any]] = []
        for item in data:
            item_data = to_dict(item)
            item_id = item_data.get("id")
            item_turn_id = item_data.get("turn_id")
            if not isinstance(item_id, str) or not item_id or not isinstance(item_turn_id, str):
                return None
            if item_id in seen_item_ids:
                return None
            seen_item_ids.add(item_id)
            page_items.append(item_data)
            if item_turn_id == turn_id:
                saw_target = True
                exact_desc.append(item_data)
            elif saw_target:
                return list(reversed(exact_desc))
            else:
                # With descending order, any different identified turn before
                # the target means a newer turn superseded this recovery.
                return None
        total_items += len(page_items)
        if not has_more:
            return list(reversed(exact_desc)) if saw_target else None
        next_cursor = page_items[-1]["id"]
        if next_cursor == cursor:
            return None
        cursor = next_cursor
    return None


def retrieve_completed_turn_output(client: Any, session_id: str, turn_id: str) -> str:
    """Read only final-answer text from a complete page for this exact turn."""
    items = read_exact_turn_items(client, session_id, turn_id)
    if items is None:
        return ""
    assistant_messages: list[dict[str, Any]] = []
    for data in items:
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
