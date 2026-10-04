"""Provider implementations for conversational analytics."""

from .base import Provider, ProviderResult
from .mock import MockProvider

__all__ = ["MockProvider", "Provider", "ProviderResult"]
