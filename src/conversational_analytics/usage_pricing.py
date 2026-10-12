"""Conservative pricing helpers for confirmed provider token usage."""

from __future__ import annotations

from typing import Any


def price_usage(config: Any, input_tokens: int, output_tokens: int) -> float:
    return config.usage_cost_usd(input_tokens, output_tokens)


def reported_usage(exc: BaseException, config: Any) -> tuple[int, int, float] | None:
    """Price usage attached to a provider failure when it is explicitly known."""
    usage = getattr(exc, "usage", None)
    if not usage:
        return None
    input_tokens, output_tokens = usage
    return input_tokens, output_tokens, price_usage(config, input_tokens, output_tokens)


__all__ = ["price_usage", "reported_usage"]
