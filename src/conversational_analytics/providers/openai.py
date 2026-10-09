"""Official Agents API provider for local chat, without replaying inputs."""

from __future__ import annotations

import json
import os
import threading
import time
import uuid
from typing import Any, Callable

from ..model_settings import agent_configuration
from ._input_authorization import InputAuthorizer, send_tool_result
from ._openai_helpers import (
    ALLOWED_TOOL_NAMES,
    SYSTEM_INSTRUCTIONS,
    TERMINAL_USAGE_RECONCILIATION_SECONDS,
    OpenAIProviderError,
    ToolResultLimitExceeded,
    chart_from_results,
    close_stream,
    completion_guards,
    event_call_id,
    event_session_id,
    int_or_zero,
    latest_provider_turn_id,
    parse_usage,
    prior_history,
    provider_terminal_failure,
    question_envelope,
    read_completed_turn_usage,
    references_from_results,
    required_actions,
    required_string,
    terminal_event_usage,
    to_dict,
    usage_from_event,
)
from ._openai_helpers import event_turn_id as get_event_turn_id
from ._openai_recovery import (
    finish_recovered_completion,
    recover_completed_provider_error,
    recover_exact_turn,
)
from .base import ProviderResult, ToolCall


class OpenAIProvider:
    """Blocking provider implementation backed by ``openai>=3.13.0``.

    ``client`` is injectable for offline tests. Production construction is
    credential-lazy and never probes the API; the official SDK reads its key
    from ``OPENAI_API_KEY`` only when a call is made.
    """

    supports_input_authorization = True
    supports_terminal_usage_reconciliation = True

    def __init__(
        self,
        config: Any,
        *,
        client: Any | None = None,
    ) -> None:
        if not getattr(config, "openai_enabled", False) or not getattr(config, "model", None):
            raise OpenAIProviderError("OpenAI requiere habilitación explícita y CHAT_MODEL configurado")
        self.model = str(config.model)
        self.reasoning_effort = str(getattr(config, "reasoning_effort", "medium"))
        self.text_verbosity = str(getattr(config, "text_verbosity", "medium"))
        self.max_tool_calls = int(getattr(config, "max_tool_calls", 8))
        self.max_tool_result_bytes = int(getattr(config, "max_tool_result_bytes", 64_000))
        self.max_turn_seconds = int(getattr(config, "max_turn_seconds", 180))
        if min(self.max_tool_calls, self.max_tool_result_bytes, self.max_turn_seconds) <= 0:
            raise OpenAIProviderError("Los límites del proveedor OpenAI deben ser positivos")
        if client is None:
            if not os.environ.get("OPENAI_API_KEY"):
                raise OpenAIProviderError("OPENAI_API_KEY no está configurada")
            try:
                from openai import OpenAI
            except ImportError as exc:  # pragma: no cover - exercised in base-only installs
                raise OpenAIProviderError("Instala el extra opcional `chat` para usar OpenAI") from exc
            # No SDK retries prevent replay; request timeout and turn loop bound runtime.
            client = OpenAI(timeout=self.max_turn_seconds, max_retries=0)
        self.client = client

    def run_turn(
        self,
        *,
        session_id: str | None,
        messages: list[dict[str, Any]],
        context: dict[str, Any],
        tool_specs: list[dict[str, Any]],
        call_tool: ToolCall,
        emit,
        persist_session,
        cancel_event: threading.Event,
        authorize_input: InputAuthorizer | None = None,
        mark_terminal_completed: Callable[[tuple[int, int] | None], None] | None = None,
    ) -> ProviderResult:
        mark_terminal_completed = mark_terminal_completed or (lambda _usage=None: None)
        message = self._latest_user_message(messages)
        tools = self._validate_tool_specs(tool_specs)
        instructions = SYSTEM_INSTRUCTIONS
        app_turn_id = self._app_turn_id(messages)
        history = prior_history(messages) if session_id is None else []
        request_input = self._message_input(context, message, history)
        tracked_sessions: set[str] = set()
        started_at = time.monotonic()
        turn_deadline = started_at + self.max_turn_seconds
        usage_deadline = started_at + self.max_turn_seconds + TERMINAL_USAGE_RECONCILIATION_SECONDS
        stream_manager = None
        stream_iter = None
        stream_closed = False
        content_parts: dict[tuple[int, int, str], str] = {}
        tool_outputs: list[dict[str, Any]] = []
        processed_actions: set[tuple[str, str]] = set()
        turn_id: str | None = None
        input_tokens = output_tokens = 0
        usage_complete = False
        terminal: str | None = None
        session_was_created = session_id is None
        prior_turn_id: str | None = None
        authorize = authorize_input or (lambda: None)

        def limit_error(message: str, reason: str, current_turn: str | None) -> OpenAIProviderError:
            return OpenAIProviderError(
                message, reason_code=reason, session_id=session_id, turn_id=current_turn
            )

        check_limits, accept_completed = completion_guards(
            cancel_event,
            started_at,
            self.max_turn_seconds,
            mark_terminal_completed,
            lambda: limit_error("El turno excedió el límite de tiempo configurado", "turn_timeout", turn_id),
        )

        def close_active_stream() -> None:
            nonlocal stream_closed
            if stream_manager is not None and not stream_closed:
                close_stream(stream_manager)
                stream_closed = True

        # Shared by every path that accepts a recovered completed turn.
        finish: dict[str, Any] = {
            "client": self.client,
            "cancel_event": cancel_event,
            "deadline": usage_deadline,
            "close_stream": close_active_stream,
            "accept_completed": accept_completed,
            "tool_outputs": tool_outputs,
        }

        def handle_action(action: Any) -> None:
            nonlocal turn_id
            data = to_dict(action)
            if data.get("type") != "function_call":
                raise OpenAIProviderError("El agente solicitó una acción fuera de la lista permitida")
            action_turn_id = required_string(data.get("turn_id"), "turn_id")
            call_id = required_string(data.get("call_id"), "call_id")
            name = required_string(data.get("name"), "name")
            args = data.get("arguments")
            if not isinstance(args, dict):
                raise OpenAIProviderError("La llamada de herramienta no contiene argumentos JSON válidos")
            if name not in ALLOWED_TOOL_NAMES:
                raise OpenAIProviderError("El agente solicitó una herramienta fuera de la lista permitida")
            if session_id is None:
                raise OpenAIProviderError("El proveedor no devolvió la sesión antes de una acción")
            if turn_id is not None and action_turn_id != turn_id:
                raise OpenAIProviderError("La acción pertenece a otro turno del proveedor")
            turn_id = action_turn_id
            action_key = (action_turn_id, call_id)
            if action_key in processed_actions:
                return
            if len(processed_actions) >= self.max_tool_calls:
                raise limit_error(
                    "El turno alcanzó el máximo de llamadas de herramientas",
                    "tool_call_limit",
                    action_turn_id,
                )
            check_limits()
            processed_actions.add(action_key)
            emit("tool.started", {"name": name})
            try:
                result = call_tool(action_turn_id, call_id, name, args)
                if not isinstance(result, dict):
                    raise TypeError("tool result must be a JSON object")
                encoded = json.dumps(result, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
                if len(encoded.encode("utf-8")) > self.max_tool_result_bytes:
                    raise ToolResultLimitExceeded
            except ToolResultLimitExceeded:
                safe_error = "La herramienta no pudo completar una consulta validada."
                emit("tool.completed", {"name": name, "error": safe_error})
                raise limit_error(safe_error, "tool_result_limit", action_turn_id) from None
            except Exception:
                safe_error = "La herramienta no pudo completar una consulta validada."
                emit("tool.completed", {"name": name, "error": safe_error})
                # Do not mark a tool call final before durable result storage.
                raise OpenAIProviderError(safe_error) from None
            emit(
                "tool.completed",
                {"name": name, "result": result},
            )
            error = result.get("error") if set(result) == {"error"} else None
            if isinstance(error, dict):
                send_tool_result(
                    self.client,
                    session_id,
                    action_turn_id,
                    call_id,
                    success=False,
                    error=str(error.get("message", "")),
                    authorize_input=authorize,
                )
                return
            tool_outputs.append(result)
            send_tool_result(
                self.client,
                session_id,
                action_turn_id,
                call_id,
                success=True,
                output=encoded,
                authorize_input=authorize,
            )

        def is_current_root_turn(event_data: dict[str, Any]) -> bool:
            nonlocal turn_id
            turn = event_data.get("turn")
            if isinstance(turn, dict) and turn.get("subagent_id") is not None:
                return False
            event_turn_id = get_event_turn_id(event_data)
            if not event_turn_id or (prior_turn_id and event_turn_id == prior_turn_id):
                return False
            if turn_id is None:
                turn_id = event_turn_id
            return event_turn_id == turn_id

        try:
            if cancel_event.is_set():
                raise InterruptedError("turn cancelled")
            if session_was_created:
                authorize()
                stream_manager = self.client.beta.agents.sessions.create(
                    agent=agent_configuration(
                        self.model,
                        instructions,
                        tools,
                        self.reasoning_effort,
                        self.text_verbosity,
                    ),
                    environment={"type": "none"},
                    input=request_input,
                    stream=True,
                )
                if hasattr(stream_manager, "with_result_collection"):
                    stream_manager = stream_manager.with_result_collection()
                stream_iter = (
                    stream_manager.__enter__() if hasattr(stream_manager, "__enter__") else stream_manager
                )
            else:
                self._track_session(session_id, persist_session, tracked_sessions)
                prior_turn_id = latest_provider_turn_id(self.client, session_id)
                stream_manager = self.client.beta.agents.sessions.events.stream(session_id)
                stream_iter = (
                    stream_manager.__enter__() if hasattr(stream_manager, "__enter__") else stream_manager
                )
                # The event stream is attached before the user message is sent.
                authorize()
                try:
                    self.client.beta.agents.sessions.events.create(
                        session_id,
                        idempotency_key=f"airline-tracker-turn-{app_turn_id}",
                        events=[{"type": "agent.session.input.message", "input": request_input}],
                    )
                finally:
                    if cancel_event.is_set():
                        self.cancel(session_id)
                if cancel_event.is_set():
                    raise InterruptedError("turn cancelled")
            self._track_session(session_id, persist_session, tracked_sessions)
            if stream_iter is None:
                raise OpenAIProviderError("El SDK no abrió el stream de la sesión")
            for event in stream_iter:
                event_data = to_dict(event)
                event_type = event_data.get("type")
                discovered_session = event_session_id(event_data)
                if discovered_session and discovered_session != session_id:
                    session_id = discovered_session
                    self._track_session(session_id, persist_session, tracked_sessions)
                is_current_turn = is_current_root_turn(event_data)
                event_id = event_data.get("event_id")
                if event_type in {
                    "agent.session.created",
                    "agent.session.turn.created",
                    "agent.session.requires_action",
                    "agent.session.turn.completed",
                    "agent.session.turn.failed",
                    "agent.session.turn.cancelled",
                }:
                    emit(
                        "provider.metadata",
                        {
                            "provider_turn_id": turn_id,
                            "provider_call_id": event_call_id(event_data),
                            "provider_event_id": event_id,
                            "provider_event_type": event_type,
                        },
                    )
                # Capture IDs before cancellation so the worker can stop a just-created remote session.
                session_failure = event_type in {
                    "agent.session.failed",
                    "agent.session.environment.failed",
                    "error",
                }
                if session_failure or (event_type == "agent.session.turn.failed" and is_current_turn):
                    terminal = "failed"
                event_usage = usage_from_event(event_data) if session_failure else terminal_event_usage(
                    event_type, is_current_turn, event_data
                )
                check_limits(event_usage)
                if event_type == "agent.session.turn.output_text.delta" and is_current_turn:
                    key = (
                        int_or_zero(event_data.get("output_index")),
                        int_or_zero(event_data.get("content_index")),
                        str(event_data.get("item_id") or ""),
                    )
                    delta = event_data.get("delta")
                    if isinstance(delta, str):
                        content_parts[key] = content_parts.get(key, "") + delta
                        emit(
                            "message.delta",
                            {"text": delta},
                        )
                elif event_type == "agent.session.turn.output_text.done" and is_current_turn:
                    key = (
                        int_or_zero(event_data.get("output_index")),
                        int_or_zero(event_data.get("content_index")),
                        str(event_data.get("item_id") or ""),
                    )
                    text = event_data.get("text")
                    if isinstance(text, str):
                        content_parts[key] = text
                elif event_type == "agent.session.requires_action":
                    actions = required_actions(self.client, event_data, session_id)
                    for action in actions:
                        handle_action(action)
                elif event_type == "agent.session.turn.completed":
                    if is_current_turn:
                        usage = event_usage
                        accept_completed(usage)
                        terminal = "completed"
                        if usage is None and session_id and turn_id:
                            usage = read_completed_turn_usage(
                                self.client,
                                session_id,
                                turn_id,
                                cancel_event=cancel_event,
                                deadline=usage_deadline,
                                close_stream=close_active_stream,
                            )
                        if usage is not None:
                            input_tokens, output_tokens = usage
                            usage_complete = True
                        break
                elif event_type == "agent.session.turn.failed":
                    if is_current_turn:
                        terminal = "failed"
                        raise provider_terminal_failure(
                            "El proveedor marcó el turno como fallido",
                            usage_from_event(event_data),
                            session_id,
                            turn_id,
                        )
                elif event_type == "agent.session.turn.cancelled":
                    if is_current_turn:
                        terminal = "cancelled"
                        cancelled = InterruptedError("turn cancelled")
                        cancelled.usage = usage_from_event(event_data)  # type: ignore[attr-defined]
                        raise cancelled
                elif event_type in {"agent.session.failed", "agent.session.environment.failed", "error"}:
                    terminal = "failed"
                    raise provider_terminal_failure(
                        "El ciclo del agente falló antes de completar el turno",
                        usage_from_event(event_data),
                        session_id,
                        turn_id,
                    )
            if terminal != "completed":
                recovered = self._recover(session_id, turn_id, prior_turn_id, deadline=turn_deadline)
                if recovered is not None:
                    content, recovered_status, recovered_turn_id, usage = recovered
                    recovered_usage = usage_from_event({"usage": usage})
                    if recovered_status == "failed":
                        terminal = "failed"
                        raise provider_terminal_failure(
                            "El proveedor marcó el turno como fallido",
                            recovered_usage,
                            session_id,
                            recovered_turn_id,
                        )
                    if recovered_status == "cancelled":
                        terminal = "cancelled"
                        cancelled = InterruptedError("turn cancelled")
                        cancelled.usage = recovered_usage  # type: ignore[attr-defined]
                        raise cancelled
                    if recovered_status == "completed":
                        accept_completed(recovered_usage)
                        terminal = "completed"
                        # Recovered text replaces streamed deltas; with none, keep none.
                        content_parts = {(0, 0, ""): content} if content else {}
                        turn_id = recovered_turn_id or turn_id
                        input_tokens, output_tokens, usage_complete = parse_usage(usage)
                        if not usage_complete and session_id and turn_id:
                            usage = read_completed_turn_usage(
                                self.client,
                                session_id,
                                turn_id,
                                cancel_event=cancel_event,
                                deadline=usage_deadline,
                                close_stream=close_active_stream,
                            )
                            if usage is not None:
                                input_tokens, output_tokens = usage
                                usage_complete = True
                if terminal != "completed":
                    # Idle or EOF is not proof that this user's turn succeeded.
                    raise OpenAIProviderError(
                        "El stream cerró sin resultado terminal; no se reenvió el mensaje"
                    )
            content = "".join(content_parts[key] for key in sorted(content_parts)).strip()
            if not content:
                recovered = self._recover(session_id, turn_id, prior_turn_id, deadline=turn_deadline)
                content = recovered[0] if recovered and recovered[1] == "completed" else ""
            if not content:
                raise OpenAIProviderError(
                    "El turno se completó sin texto; revisa el historial antes de reintentar"
                )
            references = references_from_results(tool_outputs)
            chart = chart_from_results(tool_outputs)
            return ProviderResult(
                content=content,
                references=references,
                chart=chart,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                provider_session_id=session_id,
                usage_complete=usage_complete,
            )
        except InterruptedError as error:
            if usage_complete and getattr(error, "usage", None) is None:
                error.usage = (input_tokens, output_tokens)  # type: ignore[attr-defined]
            raise
        except OpenAIProviderError as error:
            if usage_complete and error.usage is None:
                error.usage = (input_tokens, output_tokens)
            if terminal in {"failed", "cancelled"} or cancel_event.is_set():
                raise
            recovered_result = recover_completed_provider_error(
                error,
                recover=lambda sid, tid, prior: self._recover(sid, tid, prior, deadline=turn_deadline),
                session_id=session_id,
                turn_id=turn_id,
                prior_turn_id=prior_turn_id,
                **finish,
            )
            if recovered_result is not None:
                return recovered_result
            raise
        except Exception:
            if terminal in {"failed", "cancelled"}:
                raise
            recovered = (
                self._recover(session_id, turn_id, prior_turn_id, deadline=turn_deadline)
                if session_id and not cancel_event.is_set()
                else None
            )
            if recovered and recovered[1] == "completed" and recovered[0]:
                return finish_recovered_completion(recovered, session_id=session_id, **finish)
            raise OpenAIProviderError(
                "No se pudo completar el turno de Agents API; no se reenviará el mensaje automáticamente",
                (input_tokens, output_tokens) if usage_complete else None,
            ) from None
        finally:
            close_active_stream()

    def cancel(self, session_id: str) -> None:
        """Request cancellation through the documented session event API."""
        if not session_id:
            return
        try:
            self.client.beta.agents.sessions.events.create(
                session_id,
                events=[{"type": "agent.session.input.cancel"}],
            )
        except Exception:
            return

    def delete(self, session_id: str) -> None:
        """Delete the provider-side session when its local conversation is deleted."""
        if not session_id:
            return
        try:
            self.client.beta.agents.sessions.delete(session_id)
        except Exception:
            raise OpenAIProviderError("No se pudo borrar la sesión del proveedor") from None

    def _recover(
        self,
        session_id: str | None,
        turn_id: str | None,
        prior_turn_id: str | None = None,
        *,
        deadline: float,
    ) -> tuple[str, str, str | None, dict[str, Any]] | None:
        """Read saved turns/items after interruption without replaying input."""
        return recover_exact_turn(self.client, session_id, turn_id, deadline=deadline)

    @staticmethod
    def _validate_tool_specs(specs: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if not isinstance(specs, list):
            raise OpenAIProviderError("El catálogo de herramientas es inválido")
        validated: list[dict[str, Any]] = []
        names: set[str] = set()
        for raw in specs:
            if not isinstance(raw, dict) or raw.get("type") != "function":
                raise OpenAIProviderError("El catálogo contiene una herramienta fuera del formato function")
            name = raw.get("name")
            params = raw.get("parameters")
            if name not in ALLOWED_TOOL_NAMES or name in names or not isinstance(params, dict):
                raise OpenAIProviderError("El catálogo contiene una herramienta desconocida o duplicada")
            if params.get("type") != "object" or params.get("additionalProperties") is not False:
                raise OpenAIProviderError("Cada herramienta debe tener un esquema JSON de objeto cerrado")
            if not isinstance(params.get("properties"), dict) or not isinstance(params.get("required"), list):
                raise OpenAIProviderError("El esquema de argumentos de herramienta está incompleto")
            clean = {
                "type": "function",
                "name": name,
                "description": str(raw.get("description", ""))[:1000],
                "parameters": params,
            }
            if "strict" in raw:
                if raw["strict"] is not True:
                    raise OpenAIProviderError("Las herramientas solo admiten validación estricta")
                clean["strict"] = True
            names.add(name)
            validated.append(clean)
        if names != ALLOWED_TOOL_NAMES:
            raise OpenAIProviderError("Se requieren exactamente las siete herramientas aprobadas")
        return validated

    @staticmethod
    def _latest_user_message(messages: list[dict[str, Any]]) -> str:
        for message in reversed(messages):
            if isinstance(message, dict) and message.get("role") == "user":
                content = message.get("content")
                if isinstance(content, str) and content.strip():
                    return content
        raise OpenAIProviderError("No hay un mensaje de usuario para enviar al proveedor")

    @staticmethod
    def _app_turn_id(messages: list[dict[str, Any]]) -> str:
        for message in reversed(messages):
            if isinstance(message, dict) and message.get("role") == "user":
                for key in ("turn_id", "id"):
                    candidate = message.get(key)
                    if isinstance(candidate, str) and candidate:
                        return candidate
        return str(uuid.uuid4())

    @staticmethod
    def _message_input(
        context: dict[str, Any], message: str, history: list[dict[str, str]] | None = None
    ) -> list[dict[str, Any]]:
        try:
            envelope = question_envelope(context, message)
            if history:
                envelope["conversation_history"] = history
            text = json.dumps(
                envelope, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":")
            )
        except (TypeError, ValueError) as exc:
            raise OpenAIProviderError(
                str(exc)
                if isinstance(exc, ValueError) and str(exc)
                else "El mensaje o contexto no es JSON válido"
            ) from None
        return [{"role": "user", "content": [{"type": "input_text", "text": text}]}]

    @staticmethod
    def _track_session(session_id: str | None, persist_session, tracked: set[str]) -> None:
        if session_id and session_id not in tracked:
            persist_session(session_id)
            tracked.add(session_id)


__all__ = ["OpenAIProvider", "OpenAIProviderError"]
