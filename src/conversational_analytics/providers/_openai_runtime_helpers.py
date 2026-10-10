"""Pure request and schema helpers used by the OpenAI provider adapter."""

from __future__ import annotations

import json
import uuid
from typing import Any

from ._openai_helpers import ALLOWED_TOOL_NAMES, OpenAIProviderError, question_envelope


def validate_tool_specs(specs: list[dict[str, Any]]) -> list[dict[str, Any]]:
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


def latest_user_message(messages: list[dict[str, Any]]) -> str:
    for message in reversed(messages):
        if isinstance(message, dict) and message.get("role") == "user":
            content = message.get("content")
            if isinstance(content, str) and content.strip():
                return content
    raise OpenAIProviderError("No hay un mensaje de usuario para enviar al proveedor")


def app_turn_id(messages: list[dict[str, Any]]) -> str:
    for message in reversed(messages):
        if isinstance(message, dict) and message.get("role") == "user":
            for key in ("turn_id", "id"):
                candidate = message.get(key)
                if isinstance(candidate, str) and candidate:
                    return candidate
    return str(uuid.uuid4())


def message_input(
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


def track_session(session_id: str | None, persist_session, tracked: set[str]) -> None:
    if session_id and session_id not in tracked:
        persist_session(session_id)
        tracked.add(session_id)


def attach_failure_context(error: OpenAIProviderError, session_id: str | None, turn_id: str | None) -> None:
    error.session_id = error.session_id or session_id
    error.turn_id = error.turn_id or turn_id
    if error.reason_code is None and error.session_id:
        error.reason_code = "provider_terminal_failed"
