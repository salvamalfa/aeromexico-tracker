"""Pinned model settings shared by chat admission, storage and the provider."""

from __future__ import annotations

from typing import Any


def matches_turn_settings(turn: dict[str, Any], config: Any) -> bool:
    """Whether a queued paid turn still matches the active runtime configuration."""
    return all(
        turn.get(field) == getattr(config, field)
        for field in ("model", "reasoning_effort", "text_verbosity")
    )


def agent_configuration(
    model: str,
    instructions: str,
    tools: list[dict[str, Any]],
    reasoning_effort: str,
    text_verbosity: str,
) -> dict[str, Any]:
    """Build the typed Agents API inline agent object for an explicit turn."""
    return {
        "model": model,
        "instructions": instructions,
        "tools": tools,
        "reasoning": {"effort": reasoning_effort},
        "text": {"verbosity": text_verbosity},
    }


def fail_if_settings_changed(store: Any, turn: dict[str, Any], config: Any) -> bool:
    """Reject a not-yet-sent turn and release its reservation as known zero use."""
    pinned_provider = turn.get("provider")
    legacy_openai_session = pinned_provider is None and turn.get("provider_session_id") is not None
    provider_changed = (pinned_provider is not None and pinned_provider != config.provider) or (
        legacy_openai_session and config.provider != "openai"
    )
    if (
        not provider_changed
        and (
            config.provider != "openai"
            or not getattr(config, "model", None)
            or matches_turn_settings(turn, config)
        )
    ):
        return False
    store.fail_turn(
        turn["id"],
        "provider_configuration_changed" if provider_changed else "model_configuration_changed",
        "La configuración del proveedor o modelo cambió antes de procesar esta pregunta. "
        "Crea una conversación nueva y envíala de nuevo.",
        usage=(0, 0, 0.0),
    )
    return True


__all__ = ["agent_configuration", "fail_if_settings_changed", "matches_turn_settings"]
