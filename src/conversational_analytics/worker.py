"""Single-process durable turn worker, independent of browser connections."""

from __future__ import annotations

import hashlib
import json
import logging
import os
import threading
import time
from dataclasses import dataclass
from typing import Any

from .config import ChatConfig
from .providers._openai_helpers import (
    PROVIDER_REASON_CODES,
    TERMINAL_USAGE_RECONCILIATION_SECONDS,
    recover_usage_after_cancel,
)
from .providers.base import Provider, ProviderResult
from .semantic.plan import PlanValidationError
from .storage import ChatStore, NotFound

LOG = logging.getLogger("conversational_analytics.worker")


@dataclass
class _ActiveTurn:
    cancel_event: threading.Event
    provider_session_id: str | None
    cancel_drained: threading.Event
    owner_id: str
    provider_cancel_started: bool = False
    provider_input_started: bool = False
    provider_terminal_completed: bool = False


class TurnWorker:
    def __init__(self, store: ChatStore, config: ChatConfig, provider: Provider, snapshot: Any):
        self.store, self.config, self.provider, self.snapshot = store, config, provider, snapshot
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._guard = threading.Lock()
        self._active: dict[str, _ActiveTurn] = {}
        self._shutdown_expired = False
        self._registry = None
        self._last_retention_sweep = 0.0

    @property
    def running(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    def start(self) -> None:
        with self._guard:
            if self.running:
                return
            self._stop.clear()
            self._shutdown_expired = False
            self._thread = threading.Thread(target=self._run, name="chat-turn-worker", daemon=True)
            self._thread.start()

    def stop(self, timeout: float | None = None) -> None:
        """Stop claiming work, drain the current turn, then time it out if needed."""
        if timeout is None:
            timeout = self.config.max_turn_seconds + 5
        self.begin_shutdown()
        with self._guard:
            thread = self._thread
        if not thread:
            return
        thread.join(timeout=max(0.0, timeout))
        if not thread.is_alive():
            return

        # A provider may ignore cancellation. Make the turn terminal before the
        # process exits so startup recovery cannot replay an ambiguous request.
        with self._guard:
            self._shutdown_expired = True
            active = list(self._active.items())
        for turn_id, active_turn in active:
            with self._guard:
                if self._active.get(turn_id) is not active_turn:
                    continue
                input_started = active_turn.provider_input_started
                self.store.fail_turn(
                    turn_id,
                    "timeout",
                    "El cierre del servicio excedió el tiempo de espera del turno.",
                    usage=None if input_started else (0, 0, 0.0),
                )
            if input_started:
                self._cancel_terminal_session(turn_id, wait_for_cancel=False, asynchronous=True)

    def begin_shutdown(self) -> None:
        """Fence new claims immediately when the ASGI server receives shutdown."""
        with self._guard:
            self._stop.set()

    def cancel(self, turn_id: str) -> None:
        self._cancel_terminal_session(turn_id)

    def _cancel_terminal_session(
        self, turn_id: str, *, wait_for_cancel: bool = True, asynchronous: bool = False
    ) -> None:
        """Cancel a known session for a cancelled or timed-out turn exactly once."""
        with self._guard:
            active = self._active.get(turn_id)
            if active is None:
                return
            if not active.provider_input_started:
                active.cancel_event.set()
                return
        # Terminal status prevents late cancellation from reaching a reused session.
        try:
            record = self.store.get_turn(active.owner_id, turn_id)
        except NotFound:
            # Conversation deletion can precede the first session-created event.
            # Only an already-signalled cancellation authorizes cleanup of this
            # newly discovered remote session.
            orphaned_cancel = active.cancel_event.is_set()
            if not orphaned_cancel:
                return
        else:
            orphaned_cancel = False
        if (
            not orphaned_cancel
            and record["status"] != "cancelled"
            and not (record["status"] == "failed" and record.get("error_code") == "timeout")
        ):
            return
        with self._guard:
            if self._active.get(turn_id) is not active:
                return
            active.cancel_event.set()
            session_id = active.provider_session_id
            if not session_id:
                return
            if orphaned_cancel:
                self.store.queue_provider_deletion(session_id)
            owns_cancel = not active.provider_cancel_started
            if owns_cancel:
                active.provider_cancel_started = True
                active.cancel_drained.clear()
            should_wait = not active.cancel_drained.is_set()
        if not owns_cancel:
            if should_wait and wait_for_cancel:
                active.cancel_drained.wait()
            return

        def cancel_provider_session() -> None:
            try:
                self.provider.cancel(session_id)
            except Exception:  # Provider cancellation is best effort; do not expose SDK errors.
                LOG.warning("Provider cancellation failed for turn %s", turn_id)
            finally:
                active.cancel_drained.set()

        if asynchronous:
            threading.Thread(target=cancel_provider_session, name="chat-provider-cancel", daemon=True).start()
            return
        try:
            cancel_provider_session()
        finally:
            active.cancel_drained.set()

    def _get_registry(self):
        if self._registry is None:
            from .tools.registry import ToolRegistry

            self._registry = ToolRegistry(self.snapshot)
        return self._registry

    def _run(self) -> None:
        lock_path = self.store.path.with_suffix(self.store.path.suffix + ".worker.lock")
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        handle = lock_path.open("a+")
        try:
            try:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)

                def unlock():
                    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
            except ImportError:
                import msvcrt

                handle.seek(0)
                if os.name == "nt" and handle.tell() == 0:
                    handle.write("0")
                    handle.flush()
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)

                def unlock():
                    msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        except (OSError, BlockingIOError):
            handle.close()
            LOG.error("Another chat worker owns the configured state database")
            return
        try:
            self._run_loop()
        finally:
            unlock()
            handle.close()

    def _run_loop(self) -> None:
        # Running turns may have reached a paid provider before a process crash.
        # Cancel any known session, then fail them; never replay ambiguously.
        interrupted = self.store.list_interrupted_sessions()
        for item in interrupted:
            if item["provider_session_id"]:
                try:
                    self.provider.cancel(item["provider_session_id"])
                except Exception:
                    LOG.warning("Could not cancel provider session for interrupted turn %s", item["id"])
                try:
                    self.provider.delete(item["provider_session_id"])
                except Exception:
                    LOG.warning("Could not delete provider session for interrupted turn %s", item["id"])
                    self.store.queue_provider_deletion(item["provider_session_id"])
                self.store.clear_provider_session(item["conversation_id"])
        interrupted = self.store.recover_interrupted()
        if interrupted:
            LOG.warning("Marked %d interrupted chat turn(s) failed on worker startup", len(interrupted))
        self._sweep_retention()
        self._drain_provider_deletions()
        while not self._stop.is_set():
            self._sweep_retention()
            # Serialize claims with stop(): once stop sets the event no pending
            # turn can cross into running, even at the loop boundary.
            with self._guard:
                if self._stop.is_set():
                    break
                turn = self.store.claim_turn()
            if turn is None:
                self._drain_provider_deletions()
                self._stop.wait(self.config.poll_interval_seconds)
                continue
            self._execute_turn(turn)

    def _drain_provider_deletions(self) -> None:
        for session_id in self.store.pending_provider_deletions():
            try:
                self.provider.delete(session_id)
            except Exception:
                self.store.failed_provider_deletion(session_id)
                LOG.warning("Provider session deletion remains queued")
            else:
                self.store.complete_provider_deletion(session_id)

    def _sweep_retention(self) -> None:
        if time.monotonic() - self._last_retention_sweep >= 3600:
            self.store.cleanup_expired(self.config.retention_days)
            self.store.cleanup_auth()
            self._last_retention_sweep = time.monotonic()

    def _execute_turn(self, turn: dict[str, Any]) -> None:
        turn_id, conversation_id = turn["id"], turn["conversation_id"]
        cancel_event = threading.Event()
        cancel_drained = threading.Event()
        cancel_drained.set()
        session_id = turn.get("provider_session_id")
        active = _ActiveTurn(cancel_event, session_id, cancel_drained, owner_id=turn["owner_id"])
        with self._guard:
            self._active[turn_id] = active
            shutdown_expired = self._shutdown_expired
        if shutdown_expired:
            if self.store.is_running(turn_id):
                self.store.fail_turn(
                    turn_id,
                    "timeout",
                    "El cierre del servicio venció antes de iniciar la solicitud al proveedor.",
                    usage=(0, 0, 0.0),
                )
            with self._guard:
                self._active.pop(turn_id, None)
            return
        if not self.store.is_running(turn_id):
            cancel_event.set()
            with self._guard:
                self._active.pop(turn_id, None)
            return
        deadline = time.monotonic() + self.config.max_turn_seconds
        if turn["snapshot_version"] != str(getattr(self.snapshot, "version", "unavailable")):
            self.store.fail_turn(
                turn_id,
                "snapshot_changed",
                "La versión de datos cambió. Crea una conversación nueva para continuar.",
            )
            with self._guard:
                self._active.pop(turn_id, None)
            return
        current_semantic = getattr(self.snapshot, "semantic_version", None)
        if not current_semantic:
            current_semantic = hashlib.sha256(
                json.dumps(
                    self.snapshot.catalog(), ensure_ascii=False, sort_keys=True, separators=(",", ":")
                ).encode("utf-8")
            ).hexdigest()
        if turn.get("semantic_version", "") != current_semantic:
            self.store.fail_turn(
                turn_id,
                "semantic_changed",
                "Las definiciones cambiaron. Crea una conversación nueva para continuar.",
            )
            with self._guard:
                self._active.pop(turn_id, None)
            return
        registry = self._get_registry()
        tool_specs = registry.tool_specs()
        call_counter = 0
        emitted_chars = 0

        def timeout_turn(*, finalization_deadline: bool = False) -> None:
            # Commit the authoritative terminal state before waking the provider.
            # Otherwise it can raise InterruptedError on the event and win the
            # race, recording a user cancellation instead of this timeout. Keep
            # input authorization and this terminal write in the same fence so
            # an accepted SDK input cannot be booked as zero.
            with self._guard:
                if active.provider_terminal_completed and not finalization_deadline:
                    return
                if not self.store.is_running(turn_id):
                    return
                input_started = active.provider_input_started
                self.store.fail_turn(
                    turn_id,
                    "timeout",
                    "El turno excedió el tiempo máximo configurado.",
                    usage=None if input_started else (0, 0, 0.0),
                )
            self._cancel_terminal_session(turn_id)

        execution_timer = threading.Timer(self.config.max_turn_seconds, timeout_turn)
        execution_timer.daemon = True
        execution_timer.start()
        finalization_timer = threading.Timer(
            self.config.max_turn_seconds + TERMINAL_USAGE_RECONCILIATION_SECONDS,
            lambda: timeout_turn(finalization_deadline=True),
        )
        finalization_timer.daemon = True
        finalization_timer.start()

        def mark_terminal_completed(usage: tuple[int, int] | None = None) -> None:
            """Yield the execution watchdog only after provider completion."""
            with self._guard:
                if cancel_event.is_set() or not self.store.is_running(turn_id):
                    error = InterruptedError("turn was cancelled before terminal usage reconciliation")
                    if usage is not None:
                        error.usage = usage  # type: ignore[attr-defined]
                    raise error
                if time.monotonic() > deadline:
                    error = TimeoutError("turn deadline exceeded")
                    if usage is not None:
                        error.usage = usage  # type: ignore[attr-defined]
                    raise error
                active.provider_terminal_completed = True

        def emit(event_type: str, payload: dict[str, Any]) -> None:
            nonlocal emitted_chars
            if event_type == "provider.metadata":
                self.store.set_provider_turn(
                    turn_id,
                    str(payload.get("provider_turn_id") or payload.get("turn_id") or ""),
                    str(payload.get("provider_event_id", "")) or None,
                    str(payload.get("provider_event_type", "")) or None,
                )
                return
            if not self.store.is_running(turn_id):
                return
            payload = {k: v for k, v in payload.items() if k not in {"provider_turn_id", "turn_id"}}
            if event_type == "message.delta":
                delta = payload.get("text", "")
                if not isinstance(delta, str):
                    raise ValueError("provider delta size exceeded")
                emitted_chars += len(delta)
                if emitted_chars > self.config.max_message_chars * 4:
                    raise ValueError("provider output size exceeded")
            self.store.add_event(turn_id, event_type, payload)

        def persist_session(provider_session_id: str) -> None:
            nonlocal session_id
            if not provider_session_id or len(provider_session_id) > 300:
                raise ValueError("invalid provider session id")
            self.store.set_provider_session(conversation_id, provider_session_id)
            session_id = provider_session_id
            with self._guard:
                if turn_id in self._active:
                    self._active[turn_id].provider_session_id = session_id

        def authorize_provider_input() -> None:
            """Linearize each provider input against cancellation and shutdown."""
            with self._guard:
                if (
                    self._shutdown_expired
                    or active.provider_terminal_completed
                    or cancel_event.is_set()
                    or not self.store.is_running(turn_id)
                ):
                    raise InterruptedError("provider input was not authorized")
                if time.monotonic() > deadline:
                    raise TimeoutError("turn deadline exceeded")
                active.provider_input_started = True

        def call_tool(provider_turn_id: str, call_id: str, name: str, args: dict[str, Any]) -> dict[str, Any]:
            nonlocal call_counter
            if cancel_event.is_set() or not self.store.is_running(turn_id):
                raise InterruptedError("cancelled")
            if time.monotonic() > deadline:
                raise TimeoutError("turn deadline exceeded")
            cached = self.store.get_tool_result(turn_id, call_id, name, args, provider_turn_id)
            if cached is not None:
                return cached
            claimed, prior_result = self.store.begin_tool_call(turn_id, call_id, name, provider_turn_id)
            if not claimed:
                return prior_result or {}
            call_counter += 1
            if call_counter > self.config.max_tool_calls:
                raise ValueError("tool call limit exceeded")
            try:
                result = registry.invoke(name, args, context=turn["context"])
            except (PlanValidationError, ValueError, KeyError, TypeError) as exc:
                # Bad model arguments are answered to the model as a persisted
                # tool error so it can correct itself; storage failures below
                # still fail the turn.
                LOG.info("Tool %s rejected arguments (%s)", name, type(exc).__name__)
                message = (
                    str(exc)[:300]
                    if isinstance(exc, PlanValidationError)
                    else "La consulta no pasó la validación semántica."
                )
                result = {"error": {"code": "tool_rejected", "message": message}}
            if cancel_event.is_set() or not self.store.is_running(turn_id):
                raise InterruptedError("turn no longer active")
            encoded = json.dumps(result, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode(
                "utf-8"
            )
            if len(encoded) > self.config.max_tool_result_bytes:
                raise ValueError("tool result size exceeded")
            # Persist before returning the result to the provider. A repeated
            # call_id after reconnect/reconciliation is served from this row.
            return self.store.save_tool_result(turn_id, call_id, name, args, result, provider_turn_id)

        result: ProviderResult | None = None
        try:
            messages = self.store.turn_messages(turn["owner_id"], conversation_id)
            if messages:
                messages[-1]["turn_id"] = turn_id
            supports_input_authorization = getattr(self.provider, "supports_input_authorization", False)
            with self._guard:
                may_invoke_provider = (
                    not self._shutdown_expired
                    and not cancel_event.is_set()
                    and self.store.is_running(turn_id)
                )
                if may_invoke_provider and not supports_input_authorization:
                    # Legacy providers expose no callback before SDK input, so
                    # entering run_turn is their conservative authorization point.
                    active.provider_input_started = True
            if not may_invoke_provider:
                with self._guard:
                    if self.store.is_running(turn_id):
                        self.store.fail_turn(
                            turn_id,
                            "timeout",
                            "El cierre del servicio venció antes de iniciar la solicitud al proveedor.",
                            usage=(0, 0, 0.0),
                        )
                return
            provider_arguments = {
                "session_id": session_id,
                "messages": messages,
                "context": turn["context"],
                "tool_specs": tool_specs,
                "call_tool": call_tool,
                "emit": emit,
                "persist_session": persist_session,
                "cancel_event": cancel_event,
            }
            if supports_input_authorization:
                provider_arguments["authorize_input"] = authorize_provider_input
            if getattr(self.provider, "supports_terminal_usage_reconciliation", False):
                provider_arguments["mark_terminal_completed"] = mark_terminal_completed
            if getattr(self.provider, "supports_session_retirement", False):
                provider_arguments["retire_session"] = self.store.queue_provider_deletion
            result = self.provider.run_turn(**provider_arguments)
            if not isinstance(result, ProviderResult):
                raise TypeError("provider returned an invalid result")
            if result.provider_session_id:
                persist_session(result.provider_session_id)
            if cancel_event.is_set() or not self.store.is_running(turn_id):
                self._record_result_usage(turn_id, result)
                return
            if time.monotonic() > deadline and not active.provider_terminal_completed:
                raise TimeoutError("turn deadline exceeded")
            content = result.content
            if len(content) > self.config.max_message_chars * 4:
                raise ValueError("provider output size exceeded")
            input_tokens = result.input_tokens if result.usage_complete else 0
            output_tokens = result.output_tokens if result.usage_complete else 0
            cost = self.config.usage_cost_usd(input_tokens, output_tokens) if result.usage_complete else 0.0
            payload = {"references": result.references, "chart": result.chart}
            completed = self.store.complete_turn(
                turn_id, content, payload, input_tokens, output_tokens, cost, result.usage_complete
            )
            if not completed:
                self._record_result_usage(turn_id, result)
        except InterruptedError as exc:
            if not self.store.is_cancelled(turn_id):
                self.store.fail_turn(turn_id, "cancelled", "El turno fue cancelado.")
            usage = self._reported_usage(exc)
            if usage is not None:
                self.store.record_terminal_usage(turn_id, *usage)
        except TimeoutError as exc:
            self.store.fail_turn(turn_id, "timeout", "El turno excedió el tiempo máximo configurado.")
            if result is not None:
                self._record_result_usage(turn_id, result)
            else:
                usage = self._reported_usage(exc)
                if usage is not None:
                    self.store.record_terminal_usage(turn_id, *usage)
        except Exception as exc:
            # Keep details in internal logs with redaction; clients get a stable message.
            reason_code = getattr(exc, "reason_code", None)
            failure_marker_persisted = True
            if isinstance(reason_code, str) and reason_code in PROVIDER_REASON_CODES:
                if self.store.is_running(turn_id):
                    try:
                        self.store.add_event(turn_id, "provider.failure", {"reason_code": reason_code})
                    except Exception as event_exc:
                        failure_marker_persisted = False
                        LOG.error(
                            "Turn %s failure metadata could not be persisted (%s)",
                            turn_id,
                            type(event_exc).__name__,
                        )
                LOG.error("Turn %s failed (%s; reason=%s)", turn_id, type(exc).__name__, reason_code)
            else:
                LOG.error("Turn %s failed (%s)", turn_id, type(exc).__name__)
            usage = self._reported_usage(exc)
            self.store.fail_turn(
                turn_id,
                "provider_error" if failure_marker_persisted else "provider_guard_error",
                "No fue posible completar el turno. Inténtalo de nuevo.",
                usage=usage,
            )
            if usage is None and isinstance(reason_code, str) and reason_code in PROVIDER_REASON_CODES:
                self._book_usage_after_limit(turn_id, exc)
        finally:
            execution_timer.cancel()
            finalization_timer.cancel()
            # The timeout callback may still be cancelling a provider session.
            # Drain it before the worker loop can claim the next turn on that
            # session. This also prevents cancellation from outliving a completed turn.
            if execution_timer.ident != threading.get_ident():
                execution_timer.join()
            if finalization_timer.ident != threading.get_ident():
                finalization_timer.join()
            # Drain explicit cancellation or timeout after the provider has
            # surfaced any just-discovered session ID.
            self._cancel_terminal_session(turn_id)
            with self._guard:
                if self._active.get(turn_id) is active:
                    self._active.pop(turn_id, None)

    def _reported_usage(self, exc: BaseException) -> tuple[int, int, float] | None:
        """Provider usage attached to a failure, priced like a completed turn."""
        usage = getattr(exc, "usage", None)
        if not usage:
            return None
        input_tokens, output_tokens = usage
        return input_tokens, output_tokens, self.config.usage_cost_usd(input_tokens, output_tokens)

    def _book_usage_after_limit(self, turn_id: str, exc: BaseException) -> None:
        """Cancel the provider turn a local limit stopped, then book its final usage.

        Otherwise the failed turn keeps its whole reservation as unknown usage,
        which never expires and shrinks the quota of every later day.
        """
        session_id = getattr(exc, "session_id", None)
        cancel = getattr(self.provider, "cancel", None)
        if not isinstance(session_id, str) or not session_id or not callable(cancel):
            return
        try:
            cancel(session_id)
            usage, _ = recover_usage_after_cancel(self.provider, exc, session_id)
        except Exception:
            return
        if usage is not None:
            self.store.record_terminal_usage(turn_id, *usage, self.config.usage_cost_usd(*usage))

    def _record_result_usage(self, turn_id: str, result: ProviderResult) -> None:
        if not result.usage_complete:
            return
        cost = self.config.usage_cost_usd(result.input_tokens, result.output_tokens)
        self.store.record_terminal_usage(turn_id, result.input_tokens, result.output_tokens, cost)


__all__ = ["TurnWorker"]
