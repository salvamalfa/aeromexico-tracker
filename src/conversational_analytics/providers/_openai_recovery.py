"""Read-only recovery helpers for the official Agents API provider."""

from __future__ import annotations

import threading
import time
from typing import Any, Callable

from ._openai_helpers import (
    OpenAIProviderError,
    field,
    parse_usage,
    read_completed_turn_usage,
    result_from_recovered,
    to_dict,
)
from .base import ProviderResult


def recover_exact_turn(
    client: Any, session_id: str | None, turn_id: str | None, *, deadline: float
) -> tuple[str, str, str | None, dict[str, Any]] | None:
    """Read status and final text for the observed root turn within its deadline."""
    if not session_id or not turn_id:
        return None
    try:

        def remaining_timeout() -> float:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("turn deadline elapsed")
            return remaining

        session = to_dict(
            client.beta.agents.sessions.retrieve(session_id, timeout=remaining_timeout())
        )
        if session.get("id") != session_id:
            return None
        actions = session.get("required_actions") or []
        if isinstance(actions, list) and any(
            to_dict(action).get("type") == "function_call" for action in actions
        ):
            raise OpenAIProviderError("Hay una acción pendiente para recuperar")
        page = client.beta.agents.sessions.turns.list(
            session_id, limit=100, order="desc", timeout=remaining_timeout()
        )
        candidate = next(
            (item for item in getattr(page, "data", []) if field(item, "id") == turn_id), None
        )
        if candidate is None:
            return None
        data = to_dict(candidate)
        if (
            data.get("id") != turn_id
            or data.get("session_id") != session_id
            or data.get("subagent_id") is not None
        ):
            return None
        status = data.get("status")
        if status not in {"completed", "failed", "cancelled"}:
            return None
        content = (
            retrieve_completed_turn_output(client, session_id, turn_id, deadline=deadline)
            if status == "completed"
            else ""
        )
        usage = data.get("usage") if isinstance(data.get("usage"), dict) else {}
        return content, status, turn_id, usage
    except OpenAIProviderError:
        raise
    except Exception:
        return None


def read_exact_turn_items(
    client: Any, session_id: str, turn_id: str, *, deadline: float | None = None
) -> list[dict[str, Any]] | None:
    """Read the exact root turn across bounded cursor pages, oldest first.

    The SDK exposes item pagination by ID, not a turn-ID query filter. Descending
    pages let us fail if a newer turn is present, then stop at the first older
    turn after collecting the target's contiguous item run.
    """
    if not session_id or not turn_id:
        return None
    deadline = min(deadline, time.monotonic() + 30.0) if deadline is not None else time.monotonic() + 30.0
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


def retrieve_completed_turn_output(
    client: Any, session_id: str, turn_id: str, *, deadline: float | None = None
) -> str:
    """Read only final-answer text from a complete page for this exact turn."""
    items = read_exact_turn_items(client, session_id, turn_id, deadline=deadline)
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


def finish_recovered_completion(
    recovered: tuple[str, str, str | None, dict[str, Any]],
    *,
    client: Any,
    session_id: str,
    cancel_event: threading.Event,
    deadline: float,
    close_stream: Callable[[], None],
    accept_completed: Callable[[tuple[int, int] | None], None],
    tool_outputs: list[dict[str, Any]],
) -> ProviderResult:
    """Accept a recovered completed turn, then read any usage it still lacks.

    Completion is signalled before the bounded usage poll, as on the in-stream
    terminal path, so the worker's execution watchdog cannot time out a turn
    whose answer is already recovered. Missing usage would otherwise keep the
    turn's cost hold and block later admissions.
    """
    content, _, recovered_turn_id, usage_data = recovered
    input_tokens, output_tokens, usage_complete = parse_usage(usage_data)
    accept_completed((input_tokens, output_tokens) if usage_complete else None)
    if not usage_complete and recovered_turn_id:
        usage = read_completed_turn_usage(
            client,
            session_id,
            recovered_turn_id,
            cancel_event=cancel_event,
            deadline=deadline,
            close_stream=close_stream,
        )
        if usage is not None:
            usage_data = {
                "input_tokens": usage[0],
                "output_tokens": usage[1],
                "total_tokens": usage[0] + usage[1],
            }
    return result_from_recovered(content, usage_data, session_id, tool_outputs)


def recover_completed_provider_error(
    error: OpenAIProviderError,
    *,
    recover: Callable[..., tuple[str, str, str | None, dict[str, Any]] | None],
    session_id: str | None,
    turn_id: str | None,
    prior_turn_id: str | None,
    client: Any,
    cancel_event: threading.Event,
    deadline: float,
    close_stream: Callable[[], None],
    accept_completed: Callable[[tuple[int, int] | None], None],
    tool_outputs: list[dict[str, Any]],
) -> ProviderResult | None:
    """Recover a completed exact turn after a non-hardguard provider error."""
    if error.reason_code or not session_id or not turn_id:
        return None
    close_stream()
    recovered = recover(session_id, turn_id, prior_turn_id)
    if not recovered or recovered[1] != "completed" or not recovered[0]:
        return None
    return finish_recovered_completion(
        recovered,
        client=client,
        session_id=session_id,
        cancel_event=cancel_event,
        deadline=deadline,
        close_stream=close_stream,
        accept_completed=accept_completed,
        tool_outputs=tool_outputs,
    )
