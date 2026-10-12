"""Pure request and schema helpers used by the OpenAI provider adapter."""

from __future__ import annotations

import copy
import hashlib
import json
import uuid
from typing import Any

from ._openai_helpers import ALLOWED_TOOL_NAMES, PROVIDER_REASON_CODES, OpenAIProviderError, question_envelope

OPTIONAL_TOOL_NAMES = frozenset(
    {
        "query_routes",
        "find_shared_routes",
        "query_business_metrics",
        "get_business_metric_definition",
        "search_reports",
        "search_news",
    }
)


def _strict_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """Make every property required and nullable where callers may omit it."""
    if schema.get("type") != "object" or schema.get("additionalProperties") is not False:
        raise OpenAIProviderError("Cada herramienta debe tener un esquema JSON de objeto cerrado")
    properties = schema.get("properties")
    required = schema.get("required")
    if not isinstance(properties, dict) or not isinstance(required, list):
        raise OpenAIProviderError("El esquema de argumentos de herramienta está incompleto")
    if any(name not in properties for name in required):
        raise OpenAIProviderError("El esquema marca como requerido un campo no declarado")
    result = copy.deepcopy(schema)
    normalized_properties = {}
    for name, prop in properties.items():
        if not isinstance(prop, dict):
            raise OpenAIProviderError("Cada propiedad de herramienta requiere un esquema JSON")
        normalized = copy.deepcopy(prop)
        if normalized.get("type") == "object":
            normalized = _strict_schema(normalized)
        elif name not in required:
            value_type = normalized.get("type")
            if isinstance(value_type, str):
                normalized["type"] = [value_type, "null"]
            elif isinstance(value_type, list) and "null" not in value_type:
                normalized["type"] = [*value_type, "null"]
            else:
                raise OpenAIProviderError("Una propiedad opcional debe declarar tipo para admitir null")
            if isinstance(normalized.get("enum"), list) and None not in normalized["enum"]:
                normalized["enum"].append(None)
        normalized_properties[name] = normalized
    result["properties"] = normalized_properties
    result["required"] = list(properties)
    return result


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
        if name not in ALLOWED_TOOL_NAMES | OPTIONAL_TOOL_NAMES or name in names or not isinstance(params, dict):
            raise OpenAIProviderError("El catálogo contiene una herramienta desconocida o duplicada")
        params = _strict_schema(params)
        clean = {
            "type": "function",
            "name": name,
            "description": str(raw.get("description", ""))[:1000],
            "parameters": params,
        }
        if "strict" in raw and raw["strict"] is not True:
            raise OpenAIProviderError("Las herramientas solo admiten validación estricta")
        clean["strict"] = True
        names.add(name)
        validated.append(clean)
    if not ALLOWED_TOOL_NAMES <= names:
        raise OpenAIProviderError("Se requieren las siete herramientas base aprobadas")
    return validated


def session_configuration_fingerprint(instructions: str, tools: list[dict[str, Any]]) -> str:
    """Pin a provider session to exact instructions and its closed tool catalogue."""
    canonical = json.dumps(
        {"instructions": instructions, "tools": tools},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


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


def attach_failure_context(
    error: OpenAIProviderError,
    session_id: str | None,
    turn_id: str | None,
    reason_code: str | None = None,
) -> None:
    error.session_id = error.session_id or session_id
    error.turn_id = error.turn_id or turn_id
    candidate_reason = reason_code or error.diagnostic_reason_code
    if (
        error.reason_code is None
        and isinstance(candidate_reason, str)
        and candidate_reason in PROVIDER_REASON_CODES
    ):
        error.reason_code = candidate_reason
