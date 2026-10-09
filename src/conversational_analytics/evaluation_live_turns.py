"""Conversation-turn execution helpers for the private live evaluation harness."""

from __future__ import annotations

import json
import threading
from dataclasses import replace
from typing import Any, Callable


class ConversationRunError(RuntimeError):
    """A failed turn with its already completed conversation usage attached."""

    def __init__(self, completed_turns: list[Any], failed_turn_index: int, cause: BaseException) -> None:
        super().__init__("A provider turn failed during the multi-turn conversation")
        self.completed_turns = completed_turns
        self.failed_turn_index = failed_turn_index
        self.original_error = cause
        self.usage = getattr(cause, "usage", None)


def run_conversation(
    provider: Any,
    case: dict[str, Any],
    *,
    context: dict[str, Any],
    tool_specs: list[dict[str, Any]],
    call_tool: Callable,
    emit: Callable,
    persist_session: Callable,
    session: list[str],
    current_turn_index: list[int],
    calls_by_turn: list[list[dict[str, Any]]],
) -> tuple[list[Any], Any, list[list[dict[str, Any]]]]:
    """Send all fixture turns in one provider session and aggregate confirmed usage.

    If any turn's usage is incomplete, aggregate usage stays unknown. This avoids
    treating a partial conversation as if its total cost were complete.
    """
    results = []
    for turn_index, message in enumerate(case.get("turns", [case["question"]])):
        current_turn_index[0] = turn_index
        calls_by_turn.append([])
        try:
            results.append(provider.run_turn(
                session_id=session[-1] if session else None,
                messages=[{"role": "user", "content": message}],
                context=context,
                tool_specs=tool_specs,
                call_tool=call_tool,
                emit=emit,
                persist_session=persist_session,
                cancel_event=threading.Event(),
            ))
        except Exception as exc:
            raise ConversationRunError(results, turn_index, exc) from exc
    final = results[-1]
    usage_complete = all(result.usage_complete for result in results)
    known_results = [result for result in results if result.usage_complete]
    input_tokens = sum(result.input_tokens for result in known_results)
    output_tokens = sum(result.output_tokens for result in known_results)
    references: list[dict[str, Any]] = []
    seen: set[str] = set()
    for result in results:
        for ref in result.references:
            key = json.dumps(ref, sort_keys=True, ensure_ascii=False)
            if key not in seen:
                seen.add(key)
                references.append(ref)
    combined = replace(
        final,
        content="\n\n".join(result.content for result in results),
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        usage_complete=usage_complete,
        references=references,
    )
    return results, combined, calls_by_turn
