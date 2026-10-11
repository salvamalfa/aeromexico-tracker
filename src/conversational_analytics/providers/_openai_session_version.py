"""Verify whether a persisted session carries the active system instructions."""

from __future__ import annotations

import threading
import time
from typing import Any, Callable

from ._openai_helpers import OpenAIProviderError, to_dict

INSTRUCTIONS_FINGERPRINT_KEY = "chat_instructions_sha256"
PROMPT_INPUT_FINGERPRINT_KEY = "chat_prompt_input_sha256"
INSTRUCTIONS_DERIVATION_KEY = "chat_instructions_derivation"


def verify_or_rotate_session(
    sessions: Any,
    session_id: str | None,
    instructions_fingerprint: str,
    deadline: float,
    cancel_event: threading.Event,
    retire_session: Callable[[str], None] | None,
) -> tuple[str | None, str | None]:
    """Reuse only a session whose identity and effective prompt hash are verified."""
    if session_id is None:
        return None, None
    if cancel_event.is_set():
        raise InterruptedError("turn cancelled")
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise OpenAIProviderError("El turno excedió el límite de tiempo configurado")
    try:
        persisted_session = to_dict(sessions.retrieve(session_id, timeout=remaining))
    except Exception:
        raise OpenAIProviderError("No se pudo verificar la versión de instrucciones de la sesión") from None
    if persisted_session.get("id") != session_id:
        raise OpenAIProviderError("No se pudo verificar la identidad de la sesión")
    metadata = persisted_session.get("metadata")
    stored_fingerprint = metadata.get(INSTRUCTIONS_FINGERPRINT_KEY) if isinstance(metadata, dict) else None
    if stored_fingerprint == instructions_fingerprint:
        return session_id, None
    if retire_session is None:
        raise OpenAIProviderError("No se pudo encolar la sesión anterior para borrado")
    return None, session_id
