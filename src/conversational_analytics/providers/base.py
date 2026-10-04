"""Provider boundary shared by offline and hosted agent runtimes."""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Any, Callable, Protocol


@dataclass(frozen=True)
class ProviderResult:
    content: str
    references: list[dict[str, Any]] = field(default_factory=list)
    chart: dict[str, Any] | None = None
    input_tokens: int = 0
    output_tokens: int = 0
    provider_session_id: str | None = None
    usage_complete: bool = False


ToolCall = Callable[[str, str, str, dict[str, Any]], dict[str, Any]]
EventSink = Callable[[str, dict[str, Any]], None]
SessionSink = Callable[[str], None]


class Provider(Protocol):
    """Portable session/message/event/function/cancellation provider API."""

    def run_turn(
        self,
        *,
        session_id: str | None,
        messages: list[dict[str, Any]],
        context: dict[str, Any],
        tool_specs: list[dict[str, Any]],
        call_tool: ToolCall,
        emit: EventSink,
        persist_session: SessionSink,
        cancel_event: threading.Event,
    ) -> ProviderResult: ...

    def cancel(self, session_id: str) -> None: ...

    def delete(self, session_id: str) -> None: ...


__all__ = ["EventSink", "Provider", "ProviderResult", "SessionSink", "ToolCall"]
