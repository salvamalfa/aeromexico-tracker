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
        cancel_event = threading.Event()
        deadline_fired = threading.Event()
        cancellation_started = threading.Event()
        state_lock = threading.Lock()
        provider_turn_id: list[str | None] = [None]
        turn_finished = False

        def cancel_once(session_id: str) -> None:
            if cancellation_started.is_set():
                return
            with state_lock:
                if cancellation_started.is_set():
                    return
                cancellation_started.set()
            cancel = getattr(provider, "cancel", None)
            if callable(cancel):
                cancel(session_id)

        def capture_metadata(event: str, payload: dict[str, Any]) -> None:
            if event == "provider.metadata" and isinstance(payload, dict):
                turn_id = payload.get("provider_turn_id")
                if isinstance(turn_id, str):
                    provider_turn_id[0] = turn_id
            emit(event, payload)

        def persist_provider_session(session_id: str) -> None:
            persist_session(session_id)
            # Session creation can itself block past the deadline before the
            # provider exposes its ID. Cancel as soon as that ID is persisted.
            if deadline_fired.is_set():
                try:
                    cancel_once(session_id)
                except Exception:
                    pass

        max_turn_seconds = getattr(provider, "max_turn_seconds", None)
        timer: threading.Timer | None = None

        def expire_turn() -> None:
            with state_lock:
                if turn_finished:
                    return
                deadline_fired.set()
                cancel_event.set()
                session_id = session[-1] if session else None
            if session_id:
                try:
                    cancel_once(session_id)
                except Exception:
                    # The case failure path records usage as unknown if the
                    # provider cannot confirm the exact terminal turn.
                    pass

        if isinstance(max_turn_seconds, (int, float)) and max_turn_seconds > 0:
            timer = threading.Timer(max_turn_seconds, expire_turn)
            timer.daemon = True
            timer.start()
        try:
            result = provider.run_turn(
                session_id=session[-1] if session else None,
                messages=[{"role": "user", "content": message}],
                context=context,
                tool_specs=tool_specs,
                call_tool=call_tool,
                emit=capture_metadata,
                persist_session=persist_provider_session,
                cancel_event=cancel_event,
                cancel_provider=cancel_once,
            )
            with state_lock:
                turn_finished = True
            if deadline_fired.is_set():
                error = TimeoutError("live evaluation provider turn exceeded its wall-clock deadline")
                error.reason_code = "turn_timeout"  # type: ignore[attr-defined]
                error.session_id = session[-1] if session else None  # type: ignore[attr-defined]
                error.turn_id = provider_turn_id[0]  # type: ignore[attr-defined]
                if getattr(result, "usage_complete", False):
                    error.usage = (result.input_tokens, result.output_tokens)  # type: ignore[attr-defined]
                raise error
            results.append(result)
        except Exception as exc:
            with state_lock:
                turn_finished = True
            if deadline_fired.is_set():
                for name, value in (
                    ("reason_code", "turn_timeout"),
                    ("session_id", session[-1] if session else None),
                    ("turn_id", provider_turn_id[0]),
                ):
                    if not getattr(exc, name, None):
                        try:
                            setattr(exc, name, value)
                        except Exception:
                            pass
                try:
                    exc.deadline_watchdog_fired = True  # type: ignore[attr-defined]
                except Exception:
                    pass
            raise ConversationRunError(results, turn_index, exc) from exc
        finally:
            with state_lock:
                turn_finished = True
            if timer is not None:
                timer.cancel()
                timer.join()
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
