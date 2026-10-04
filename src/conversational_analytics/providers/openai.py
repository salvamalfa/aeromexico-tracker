"""Official OpenAI Agents API adapter for the local chat service.

The adapter uses ``environment.type = none`` and application-owned function
tools. It deliberately does not retry a submitted user input after an
ambiguous network failure: the saved session is reconciled first, and the
application can decide whether a new user submission is appropriate.
"""

from __future__ import annotations

import json
import os
import threading
import time
import uuid
from typing import Any

from ._openai_helpers import (
    ALLOWED_TOOL_NAMES,
    SYSTEM_INSTRUCTIONS,
    chart_from_results,
    field,
    int_or_zero,
    parse_usage,
    references_from_results,
    required_string,
    result_from_recovered,
    to_dict,
)
from .base import ProviderResult, ToolCall


class OpenAIProviderError(RuntimeError):
    """Sanitized adapter failure safe to surface to the local API."""


class OpenAIProvider:
    """Blocking provider implementation backed by ``openai>=3.13.0``.

    ``client`` is injectable for offline tests. Production construction is
    credential-lazy and never probes the API; the official SDK reads its key
    from ``OPENAI_API_KEY`` only when a call is made.
    """

    def __init__(
        self,
        config: Any,
        *,
        client: Any | None = None,
    ) -> None:
        if not getattr(config, "openai_enabled", False) or not getattr(config, "model", None):
            raise OpenAIProviderError("OpenAI requiere habilitación explícita y CHAT_MODEL configurado")
        self.model = str(config.model)
        self.max_tool_calls = int(getattr(config, "max_tool_calls", 8))
        self.max_tool_result_bytes = int(getattr(config, "max_tool_result_bytes", 64_000))
        self.max_turn_seconds = int(getattr(config, "max_turn_seconds", 90))
        if min(self.max_tool_calls, self.max_tool_result_bytes, self.max_turn_seconds) <= 0:
            raise OpenAIProviderError("Los límites del proveedor OpenAI deben ser positivos")
        if client is None:
            if not os.environ.get("OPENAI_API_KEY"):
                raise OpenAIProviderError("OPENAI_API_KEY no está configurada")
            try:
                from openai import OpenAI
            except ImportError as exc:  # pragma: no cover - exercised in base-only installs
                raise OpenAIProviderError("Instala el extra opcional `chat` para usar OpenAI") from exc
            # Disabling SDK retries prevents an ambiguous input submission from
            # being silently replayed. The per-request timeout bounds stalled
            # streams; the turn loop also enforces the overall wall-clock limit.
            client = OpenAI(timeout=self.max_turn_seconds, max_retries=0)
        self.client = client
        self._active_sessions: set[str] = set()

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
    ) -> ProviderResult:
        message = self._latest_user_message(messages)
        tools = self._validate_tool_specs(tool_specs)
        instructions = self._instructions()
        app_turn_id = self._app_turn_id(messages)
        request_input = self._message_input(context, message)
        started_at = time.monotonic()
        stream_manager = None
        stream_iter = None
        content_parts: dict[tuple[int, int, int], str] = {}
        tool_outputs: list[dict[str, Any]] = []
        processed_actions: set[tuple[str, str]] = set()
        turn_id: str | None = None
        input_tokens = output_tokens = 0
        usage_complete = False
        terminal: str | None = None
        session_was_created = session_id is None
        prior_turn_id: str | None = None

        def check_limits() -> None:
            if cancel_event.is_set():
                raise InterruptedError("turn cancelled")
            if time.monotonic() - started_at >= self.max_turn_seconds:
                raise OpenAIProviderError("El turno excedió el límite de tiempo configurado")

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
                raise OpenAIProviderError("El turno alcanzó el máximo de llamadas de herramientas")
            check_limits()
            processed_actions.add(action_key)
            emit("tool.started", {"name": name})
            try:
                result = call_tool(action_turn_id, call_id, name, args)
                if not isinstance(result, dict):
                    raise TypeError("tool result must be a JSON object")
                encoded = json.dumps(result, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
                if len(encoded.encode("utf-8")) > self.max_tool_result_bytes:
                    raise ValueError("tool result exceeds configured limit")
            except Exception:
                safe_error = "La herramienta no pudo completar una consulta validada."
                emit("tool.completed", {"name": name, "error": safe_error})
                # The dispatcher owns durable result storage. If it raises, do
                # not tell the provider that an unpersisted result is final.
                raise OpenAIProviderError(safe_error) from None
            tool_outputs.append(result)
            emit(
                "tool.completed",
                {"name": name, "result": result},
            )
            self._send_tool_result(session_id, action_turn_id, call_id, success=True, output=encoded)

        def is_current_root_turn(event_data: dict[str, Any]) -> bool:
            nonlocal turn_id
            turn = event_data.get("turn")
            if isinstance(turn, dict) and turn.get("subagent_id") is not None:
                return False
            event_turn_id = self._event_turn_id(event_data)
            if not event_turn_id or (prior_turn_id and event_turn_id == prior_turn_id):
                return False
            if turn_id is None:
                turn_id = event_turn_id
            return event_turn_id == turn_id

        try:
            self._check_cancel(cancel_event)
            if session_was_created:
                stream_manager = self.client.beta.agents.sessions.create(
                    agent={"model": self.model, "instructions": instructions, "tools": tools},
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
                self._track_session(session_id, persist_session)
                prior_turn_id = self._latest_provider_turn_id(session_id)
                stream_manager = self.client.beta.agents.sessions.events.stream(session_id)
                stream_iter = (
                    stream_manager.__enter__() if hasattr(stream_manager, "__enter__") else stream_manager
                )
                # The event stream is attached before the user message is sent.
                self.client.beta.agents.sessions.events.create(
                    session_id,
                    idempotency_key=f"airline-tracker-turn-{app_turn_id}",
                    events=[{"type": "agent.session.input.message", "input": request_input}],
                )

            self._track_session(session_id, persist_session)
            if stream_iter is None:
                raise OpenAIProviderError("El SDK no abrió el stream de la sesión")
            for event in stream_iter:
                check_limits()
                event_data = to_dict(event)
                event_type = event_data.get("type")
                discovered_session = self._event_session_id(event_data)
                if discovered_session and discovered_session != session_id:
                    session_id = discovered_session
                    self._track_session(session_id, persist_session)
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
                            "provider_call_id": self._event_call_id(event_data),
                            "provider_event_id": event_id,
                            "provider_event_type": event_type,
                        },
                    )
                if event_type == "agent.session.turn.output_text.delta" and is_current_turn:
                    key = (
                        int_or_zero(event_data.get("output_index")),
                        int_or_zero(event_data.get("content_index")),
                        int_or_zero(event_data.get("item_id_index")),
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
                        int_or_zero(event_data.get("item_id_index")),
                    )
                    text = event_data.get("text")
                    if isinstance(text, str):
                        content_parts[key] = text
                elif event_type == "agent.session.requires_action":
                    actions = self._required_actions(event_data, session_id)
                    for action in actions:
                        handle_action(action)
                elif event_type == "agent.session.turn.completed":
                    if is_current_turn:
                        terminal = "completed"
                        turn = event_data.get("turn")
                        usage = event_data.get("usage") or (turn or {}).get("usage")
                        input_tokens, output_tokens, usage_complete = parse_usage(usage)
                        break
                elif event_type == "agent.session.turn.failed":
                    if is_current_turn:
                        terminal = "failed"
                        raise OpenAIProviderError("El proveedor marcó el turno como fallido")
                elif event_type == "agent.session.turn.cancelled":
                    if is_current_turn:
                        terminal = "cancelled"
                        raise InterruptedError("turn cancelled")
                elif event_type in {"agent.session.failed", "agent.session.environment.failed", "error"}:
                    raise OpenAIProviderError("El ciclo del agente falló antes de completar el turno")
            if terminal != "completed":
                recovered = self._recover(session_id, turn_id, prior_turn_id)
                if recovered is not None:
                    content, recovered_status, recovered_turn_id, usage = recovered
                    if recovered_status == "failed":
                        raise OpenAIProviderError("El proveedor marcó el turno como fallido")
                    if recovered_status == "cancelled":
                        raise InterruptedError("turn cancelled")
                    if recovered_status == "completed":
                        terminal = "completed"
                        if content:
                            content_parts[(0, 0, 0)] = content
                        turn_id = recovered_turn_id or turn_id
                        input_tokens, output_tokens, usage_complete = parse_usage(usage)
                if terminal != "completed":
                    # Idle or EOF is not proof that this user's turn succeeded.
                    raise OpenAIProviderError(
                        "El stream cerró sin resultado terminal; no se reenvió el mensaje"
                    )
            content = "".join(content_parts[key] for key in sorted(content_parts)).strip()
            if not content:
                recovered = self._recover(session_id, turn_id, prior_turn_id)
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
        except InterruptedError:
            raise
        except OpenAIProviderError:
            raise
        except Exception:
            recovered = self._recover(session_id, turn_id, prior_turn_id) if session_id else None
            if recovered and recovered[1] == "completed" and recovered[0]:
                return result_from_recovered(recovered[0], recovered[3], session_id, tool_outputs)
            # SDK exception strings can contain request details; keep the public
            # error deliberately generic and do not log the exception object.
            raise OpenAIProviderError(
                "No se pudo completar el turno de Agents API; no se reenviará el mensaje automáticamente"
            ) from None
        finally:
            if stream_manager is not None:
                self._close_stream(stream_manager)

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
            # Cancellation is best effort; the turn state remains owned by the
            # worker and will be reconciled on its next event or recovery read.
            return

    def delete(self, session_id: str) -> None:
        """Delete the provider-side session when its local conversation is deleted."""
        if not session_id:
            return
        try:
            self.client.beta.agents.sessions.delete(session_id)
        except Exception:
            raise OpenAIProviderError("No se pudo borrar la sesión del proveedor") from None

    def _send_tool_result(
        self,
        session_id: str,
        turn_id: str,
        call_id: str,
        *,
        success: bool,
        output: str | None = None,
        error: str | None = None,
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
        self.client.beta.agents.sessions.events.create(
            session_id,
            idempotency_key=f"airline-tracker-tool-{turn_id}-{call_id}",
            events=[payload],
        )

    def _required_actions(self, event: dict[str, Any], session_id: str | None) -> list[dict[str, Any]]:
        session = event.get("session")
        if not isinstance(session, dict):
            if not session_id:
                raise OpenAIProviderError("El evento no identifica la sesión que requiere acción")
            session = to_dict(self.client.beta.agents.sessions.retrieve(session_id))
        actions = session.get("required_actions")
        if not isinstance(actions, list):
            raise OpenAIProviderError("El proveedor no devolvió las acciones pendientes")
        return [to_dict(action) for action in actions]

    def _recover(
        self, session_id: str | None, turn_id: str | None, prior_turn_id: str | None = None
    ) -> tuple[str, str, str | None, dict[str, Any]] | None:
        """Read saved turns/items after interruption without replaying input."""
        if not session_id:
            return None
        try:
            session = to_dict(self.client.beta.agents.sessions.retrieve(session_id))
            actions = session.get("required_actions") or []
            if isinstance(actions, list) and actions:
                for action in actions:
                    data = to_dict(action)
                    if data.get("type") == "function_call":
                        # The same durable dispatcher key makes re-running this
                        # pending action safe after a worker interruption.
                        raise OpenAIProviderError("Hay una acción pendiente para recuperar")
            turns_page = self.client.beta.agents.sessions.turns.list(session_id, limit=100, order="desc")
            turns = list(getattr(turns_page, "data", []))
            candidate = next((t for t in turns if not turn_id or field(t, "id") == turn_id), None)
            if candidate is None and turns:
                candidate = turns[0]
            if candidate is None:
                return None
            candidate_data = to_dict(candidate)
            if not turn_id and candidate_data.get("id") == prior_turn_id:
                return None
            status = candidate_data.get("status")
            canonical_id = candidate_data.get("id")
            if status not in {"completed", "failed", "cancelled"}:
                return None
            content = self._retrieve_output_text(session_id, canonical_id) if status == "completed" else ""
            usage = candidate_data.get("usage") if isinstance(candidate_data.get("usage"), dict) else {}
            return content, status, canonical_id, usage
        except OpenAIProviderError:
            raise
        except Exception:
            return None

    def _latest_provider_turn_id(self, session_id: str) -> str | None:
        try:
            page = self.client.beta.agents.sessions.turns.list(session_id, limit=1, order="desc")
            turns = list(getattr(page, "data", []))
            if turns:
                value = field(turns[0], "id")
                return value if isinstance(value, str) and value else None
        except Exception:
            # This lookup is only a recovery guard; it is read-only and no input
            # has been submitted yet. If it fails, avoid guessing from old turns.
            raise OpenAIProviderError(
                "No se pudo verificar el historial antes del siguiente mensaje"
            ) from None
        return None

    def _retrieve_output_text(self, session_id: str, turn_id: str | None) -> str:
        if not turn_id:
            return ""
        page = self.client.beta.agents.sessions.items.list(session_id, limit=100, order="desc")
        output: list[str] = []
        for item in getattr(page, "data", []):
            data = to_dict(item)
            if (
                data.get("turn_id") != turn_id
                or data.get("type") != "message"
                or data.get("role") != "assistant"
            ):
                continue
            for content in data.get("content", []):
                part = to_dict(content)
                text = part.get("text")
                if part.get("type") in {"output_text", "text"} and isinstance(text, str):
                    output.append(text)
        return "".join(reversed(output)).strip()

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
    def _instructions() -> str:
        return SYSTEM_INSTRUCTIONS

    @staticmethod
    def _message_input(context: dict[str, Any], message: str) -> list[dict[str, Any]]:
        if not isinstance(context, dict):
            raise OpenAIProviderError("El contexto del dashboard debe ser un objeto")
        try:
            envelope = json.dumps(
                {"dashboard_context": context, "question": message},
                ensure_ascii=False,
                allow_nan=False,
                sort_keys=True,
                separators=(",", ":"),
            )
        except (TypeError, ValueError):
            raise OpenAIProviderError("El mensaje o contexto no es JSON válido") from None
        if len(envelope.encode("utf-8")) > 12_000:
            raise OpenAIProviderError("El mensaje y contexto exceden el límite permitido")
        return [{"role": "user", "content": [{"type": "input_text", "text": envelope}]}]

    @staticmethod
    def _check_cancel(cancel_event: threading.Event) -> None:
        if cancel_event.is_set():
            raise InterruptedError("turn cancelled")

    @staticmethod
    def _event_session_id(event: dict[str, Any]) -> str | None:
        session = event.get("session")
        if isinstance(session, dict) and isinstance(session.get("id"), str):
            return session["id"]
        value = event.get("session_id")
        return value if isinstance(value, str) and value else None

    @staticmethod
    def _event_turn_id(event: dict[str, Any]) -> str | None:
        value = event.get("turn_id")
        if isinstance(value, str) and value:
            return value
        turn = event.get("turn")
        if isinstance(turn, dict) and isinstance(turn.get("id"), str):
            return turn["id"]
        session = event.get("session")
        if isinstance(session, dict) and isinstance(session.get("required_actions"), list):
            for action in session["required_actions"]:
                action_data = to_dict(action)
                action_turn_id = action_data.get("turn_id")
                if isinstance(action_turn_id, str) and action_turn_id:
                    return action_turn_id
        return None

    @staticmethod
    def _event_call_id(event: dict[str, Any]) -> str | None:
        session = event.get("session")
        if isinstance(session, dict):
            actions = session.get("required_actions")
            if isinstance(actions, list):
                for action in actions:
                    data = to_dict(action)
                    call_id = data.get("call_id")
                    if isinstance(call_id, str):
                        return call_id
        call_id = event.get("call_id")
        return call_id if isinstance(call_id, str) else None

    def _track_session(self, session_id: str | None, persist_session) -> None:
        if session_id and session_id not in self._active_sessions:
            persist_session(session_id)
            self._active_sessions.add(session_id)

    @staticmethod
    def _close_stream(stream: Any) -> None:
        try:
            if hasattr(stream, "__exit__"):
                stream.__exit__(None, None, None)
            else:
                close = getattr(stream, "close", None)
                if callable(close):
                    close()
        except Exception:
            return


__all__ = ["OpenAIProvider", "OpenAIProviderError"]
