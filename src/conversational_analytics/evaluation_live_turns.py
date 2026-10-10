"""Conversation-turn execution helpers for the private live evaluation harness."""

from __future__ import annotations

import json
import queue
import threading
import time
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
    """Run turns under an independent wall-clock bound and never replay a timeout."""
    results = []
    for turn_index, message in enumerate(case.get("turns", [case["question"]])):
        current_turn_index[0] = turn_index
        calls_by_turn.append([])
        cancel_event = threading.Event()
        deadline_fired = threading.Event()
        cancellation_started = threading.Event()
        close_started = threading.Event()
        state_lock = threading.Lock()
        input_gate_lock = threading.Lock()
        input_gate_open = [True]
        provider_turn_id: list[str | None] = [None]
        stream_closer: list[Callable[[], None] | None] = [None]
        turn_id_ready = threading.Event()
        started = time.monotonic()
        max_turn_seconds = getattr(provider, "max_turn_seconds", 180)
        timeout_seconds = max_turn_seconds if isinstance(max_turn_seconds, (int, float)) else 180
        deadline = started + timeout_seconds
        output: queue.Queue[tuple[bool, Any]] = queue.Queue(maxsize=1)
        timeout_error = TimeoutError("live evaluation provider turn exceeded its wall-clock deadline")
        timeout_error.reason_code = "turn_timeout"  # type: ignore[attr-defined]

        def async_call(callback: Callable, *args: Any) -> None:
            thread = threading.Thread(target=callback, args=args, daemon=True)
            thread.start()

        def cancel_once(session_id: str) -> None:
            with state_lock:
                if cancellation_started.is_set():
                    return
                cancellation_started.set()
            cancel = getattr(provider, "cancel", None)
            if callable(cancel):
                async_call(cancel, session_id)

        def close_once(closer: Callable[[], None] | None) -> None:
            if closer is None:
                return
            with state_lock:
                if close_started.is_set():
                    return
                close_started.set()
            async_call(closer)

        def set_timeout_metadata() -> None:
            try:
                timeout_error.session_id = session[-1] if session else None  # type: ignore[attr-defined]
                timeout_error.turn_id = provider_turn_id[0]  # type: ignore[attr-defined]
                timeout_error.deadline_watchdog_fired = True  # type: ignore[attr-defined]
            except Exception:
                pass

        def expire_turn() -> None:
            with input_gate_lock:
                input_gate_open[0] = False
            deadline_fired.set()
            cancel_event.set()
            set_timeout_metadata()
            def cleanup() -> None:
                with state_lock:
                    session_id = session[-1] if session else None
                    closer = stream_closer[0]
                if session_id:
                    cancel_once(session_id)
                close_once(closer)

            async_call(cleanup)

        def authorize_input() -> None:
            if deadline_fired.is_set() or time.monotonic() >= deadline:
                expire_turn()
                raise timeout_error
            if cancel_event.is_set():
                raise InterruptedError("live evaluation turn was cancelled")

        def dispatch_input(request: Callable[[], Any]) -> Any:
            # Admission is atomic with gate closure; do not hold the gate over
            # network I/O, so timeout/cancel remains independent of a stuck SDK.
            with input_gate_lock:
                expired = time.monotonic() >= deadline or deadline_fired.is_set()
                admitted = (
                    input_gate_open[0]
                    and not expired
                    and not cancel_event.is_set()
                )
                if not admitted:
                    input_gate_open[0] = False
            if not admitted:
                if expired:
                    expire_turn()
                    raise timeout_error
                raise InterruptedError("live evaluation turn was cancelled")
            return request()

        def capture_metadata(event: str, payload: dict[str, Any]) -> None:
            if event == "provider.metadata" and isinstance(payload, dict):
                turn_id = payload.get("provider_turn_id")
                if isinstance(turn_id, str):
                    provider_turn_id[0] = turn_id
                    turn_id_ready.set()
                    if deadline_fired.is_set():
                        set_timeout_metadata()
            emit(event, payload)

        def persist_provider_session(session_id: str) -> None:
            try:
                persist_session(session_id)
            finally:
                if deadline_fired.is_set():
                    set_timeout_metadata()
                    cancel_once(session_id)
                    close_once(stream_closer[0])

        def register_stream_close(closer: Callable[[], None]) -> None:
            with state_lock:
                stream_closer[0] = closer
                expired = deadline_fired.is_set()
            if expired:
                close_once(closer)

        def run_provider() -> None:
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
                    authorize_input=authorize_input,
                    dispatch_input=dispatch_input,
                    register_stream_close=register_stream_close,
                )
                output.put((True, result))
            except BaseException as exc:
                output.put((False, exc))

        worker = threading.Thread(target=run_provider, daemon=True)
        worker.start()
        remaining = max(0.0, deadline - time.monotonic())
        try:
            succeeded, value = output.get(timeout=remaining)
        except queue.Empty:
            expire_turn()
            set_timeout_metadata()
            # Drain only for exact terminal usage/turn metadata after cancel.
            # No late content is returned or appended to completed results.
            try:
                late_success, late_value = output.get(timeout=0.1)
                usage = (
                    (late_value.input_tokens, late_value.output_tokens)
                    if late_success and getattr(late_value, "usage_complete", False)
                    else getattr(late_value, "usage", None)
                )
                if (
                    isinstance(usage, tuple)
                    and len(usage) == 2
                    and all(
                        isinstance(token, int) and not isinstance(token, bool) and token >= 0
                        for token in usage
                    )
                ):
                    timeout_error.usage = usage  # type: ignore[attr-defined]
            except queue.Empty:
                # A metadata-only wait lets read-only reconciliation target the
                # exact provider turn if cancellation produces its ID shortly.
                turn_id_ready.wait(0.1)
            set_timeout_metadata()
            raise ConversationRunError(results, turn_index, timeout_error) from timeout_error

        if deadline_fired.is_set() or time.monotonic() > deadline:
            expire_turn()
            if succeeded and getattr(value, "usage_complete", False):
                timeout_error.usage = (value.input_tokens, value.output_tokens)  # type: ignore[attr-defined]
            raise ConversationRunError(results, turn_index, timeout_error) from timeout_error
        if not succeeded:
            raise ConversationRunError(results, turn_index, value) from value
        results.append(value)
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
