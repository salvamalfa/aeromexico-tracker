"""Single-process durable turn worker, independent of browser connections."""

from __future__ import annotations

import hashlib
import json
import logging
import os
import threading
import time
from typing import Any

from .config import ChatConfig
from .providers.base import Provider, ProviderResult
from .semantic.plan import PlanValidationError
from .storage import ChatStore

LOG = logging.getLogger("conversational_analytics.worker")


class TurnWorker:
    def __init__(self, store: ChatStore, config: ChatConfig, provider: Provider, snapshot: Any):
        self.store, self.config, self.provider, self.snapshot = store, config, provider, snapshot
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._guard = threading.Lock()
        self._active: dict[str, tuple[threading.Event, str | None]] = {}
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
            self._thread = threading.Thread(target=self._run, name="chat-turn-worker", daemon=True)
            self._thread.start()

    def stop(self, timeout: float = 5) -> None:
        self._stop.set()
        thread = self._thread
        if thread:
            thread.join(timeout=timeout)

    def cancel(self, turn_id: str) -> None:
        with self._guard:
            active = self._active.get(turn_id)
        if active:
            cancel_event, session_id = active
            cancel_event.set()
            if session_id:
                try:
                    self.provider.cancel(session_id)
                except Exception:  # Provider cancellation is best effort; do not expose SDK errors.
                    LOG.warning("Provider cancellation failed for turn %s", turn_id)

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
            self._last_retention_sweep = time.monotonic()

    def _execute_turn(self, turn: dict[str, Any]) -> None:
        turn_id, conversation_id = turn["id"], turn["conversation_id"]
        cancel_event = threading.Event()
        session_id = turn.get("provider_session_id")
        with self._guard:
            self._active[turn_id] = (cancel_event, session_id)
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

        def timeout_turn() -> None:
            cancel_event.set()
            with self._guard:
                active = self._active.get(turn_id)
                provider_session = active[1] if active else session_id
            if provider_session:
                try:
                    self.provider.cancel(provider_session)
                except Exception:
                    LOG.warning("Provider cancellation failed after timeout for turn %s", turn_id)
            self.store.fail_turn(turn_id, "timeout", "El turno excedió el tiempo máximo configurado.")

        timer = threading.Timer(self.config.max_turn_seconds, timeout_turn)
        timer.daemon = True
        timer.start()

        def emit(event_type: str, payload: dict[str, Any]) -> None:
            nonlocal emitted_chars
            if not self.store.is_running(turn_id):
                return
            if event_type == "provider.metadata":
                self.store.set_provider_turn(
                    turn_id,
                    str(payload.get("provider_turn_id", payload.get("turn_id", ""))),
                    str(payload.get("provider_event_id", "")) or None,
                    str(payload.get("provider_event_type", "")) or None,
                )
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
                    self._active[turn_id] = (cancel_event, session_id)

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
            except PlanValidationError:
                result = {
                    "error": {
                        "code": "tool_rejected",
                        "message": "La consulta no pasó la validación semántica.",
                    }
                }
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

        try:
            messages = self.store.turn_messages(turn["owner_id"], conversation_id)
            if messages:
                messages[-1]["turn_id"] = turn_id
            result = self.provider.run_turn(
                session_id=session_id,
                messages=messages,
                context=turn["context"],
                tool_specs=tool_specs,
                call_tool=call_tool,
                emit=emit,
                persist_session=persist_session,
                cancel_event=cancel_event,
            )
            if not isinstance(result, ProviderResult):
                raise TypeError("provider returned an invalid result")
            if result.provider_session_id:
                persist_session(result.provider_session_id)
            if cancel_event.is_set() or not self.store.is_running(turn_id):
                return
            if time.monotonic() > deadline:
                raise TimeoutError("turn deadline exceeded")
            content = result.content
            if len(content) > self.config.max_message_chars * 4:
                raise ValueError("provider output size exceeded")
            input_tokens = result.input_tokens if result.usage_complete else 0
            output_tokens = result.output_tokens if result.usage_complete else 0
            cost = (
                (
                    (
                        input_tokens * self.config.estimated_input_cost_per_million
                        + output_tokens * self.config.estimated_output_cost_per_million
                    )
                    / 1_000_000
                )
                if result.usage_complete
                else 0.0
            )
            payload = {"references": result.references, "chart": result.chart}
            self.store.complete_turn(
                turn_id, content, payload, input_tokens, output_tokens, cost, result.usage_complete
            )
        except InterruptedError:
            if not self.store.is_cancelled(turn_id):
                self.store.fail_turn(turn_id, "cancelled", "El turno fue cancelado.")
        except TimeoutError:
            cancel_event.set()
            if session_id:
                try:
                    self.provider.cancel(session_id)
                except Exception:
                    LOG.warning("Provider cancellation failed after timeout for turn %s", turn_id)
            self.store.fail_turn(turn_id, "timeout", "El turno excedió el tiempo máximo configurado.")
        except Exception as exc:
            # Keep details in internal logs with redaction; clients get a stable message.
            LOG.error("Turn %s failed (%s)", turn_id, type(exc).__name__)
            self.store.fail_turn(
                turn_id, "provider_error", "No fue posible completar el turno. Inténtalo de nuevo."
            )
        finally:
            timer.cancel()
            with self._guard:
                self._active.pop(turn_id, None)


__all__ = ["TurnWorker"]
