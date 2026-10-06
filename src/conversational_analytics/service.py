"""Business rules and admission control for the chat HTTP API."""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from .config import ChatConfig
from .providers._openai_helpers import question_envelope
from .semantic.context import validate_context as _validate_semantic_context
from .semantic.plan import PlanValidationError
from .storage import AdmissionDenied, ChatStore, Conflict


class InvalidRequest(ValueError):
    pass


def validate_context(raw: Any) -> dict[str, Any]:
    try:
        return _validate_semantic_context(raw)
    except PlanValidationError as exc:
        raise InvalidRequest(str(exc)) from exc


class ChatService:
    def __init__(
        self, store: ChatStore, config: ChatConfig, snapshot: Any, worker: Any = None, provider: Any = None
    ):
        config.validate_admission_budgets()
        self.store, self.config, self.snapshot, self.worker, self.provider = (
            store,
            config,
            snapshot,
            worker,
            provider,
        )

    @property
    def snapshot_version(self) -> str:
        return str(getattr(self.snapshot, "version", "unavailable"))

    @property
    def semantic_version(self) -> str:
        pinned = getattr(self.snapshot, "semantic_version", None)
        if pinned:
            return str(pinned)
        catalog = self.snapshot.catalog() if hasattr(self.snapshot, "catalog") else {}
        encoded = json.dumps(catalog, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()

    def create_conversation(self, owner_id: str) -> dict[str, Any]:
        return self.store.create_conversation(owner_id, self.snapshot_version, self.semantic_version)

    def ensure_current_snapshot(self, owner_id: str, conversation_id: str) -> None:
        history = self.store.get_conversation(owner_id, conversation_id)
        if (
            history["snapshot_version"] != self.snapshot_version
            or history.get("semantic_version", "") != self.semantic_version
        ):
            raise Conflict(
                "snapshot_changed: crea una conversación nueva para usar los datos y definiciones vigentes"
            )

    def delete_conversation(self, owner_id: str, conversation_id: str) -> None:
        conv = self.store.owned_conversation(owner_id, conversation_id)
        for turn in conv["turns"]:
            if turn["status"] in {"pending", "running"}:
                self.store.request_cancel(owner_id, turn["id"])
                if self.worker:
                    self.worker.cancel(turn["id"])
        if conv["provider_session_id"] and self.provider:
            try:
                self.provider.delete(conv["provider_session_id"])
            except Exception:
                # Local deletion must not retain chat data if remote deletion is
                # temporarily unavailable; deployment should alert on this.
                import logging

                logging.getLogger("conversational_analytics").warning(
                    "Provider session deletion failed for conversation %s", conversation_id
                )
                self.store.queue_provider_deletion(conv["provider_session_id"])
        self.store.delete_conversation(owner_id, conversation_id)

    def submit(
        self, owner_id: str, conversation_id: str, content: str, client_message_id: str, context: Any
    ) -> dict[str, Any]:
        if not self.config.admission_enabled:
            raise AdmissionDenied("chat admission is disabled")
        if not isinstance(content, str) or not content.strip():
            raise InvalidRequest("content es requerido")
        if len(content) > self.config.max_message_chars:
            raise InvalidRequest("content excede el tamaño máximo")
        if (
            not isinstance(client_message_id, str)
            or not 1 <= len(client_message_id) <= 128
            or not re.fullmatch(r"[A-Za-z0-9_.:-]+", client_message_id)
        ):
            raise InvalidRequest("client_message_id inválido")
        validated_context = validate_context(context)
        try:
            # Same envelope limit the provider enforces, checked before admission.
            question_envelope(validated_context, content)
        except ValueError as exc:
            raise InvalidRequest(str(exc)) from exc
        existing = self.store.find_deduplicated_turn(owner_id, conversation_id, client_message_id)
        if existing:
            if (
                existing["user_content"] != content
                or json.loads(existing["context_json"]) != validated_context
            ):
                raise Conflict("client_message_id was already used with different content or context")
            return {"turn_id": existing["id"], "status": existing["status"], "deduplicated": True}
        # Reserve a deliberately broad input/output window, including prior
        # history, tool schemas/catalog, all bounded tool outputs, and answer.
        self.ensure_current_snapshot(owner_id, conversation_id)
        history = self.store.get_conversation(owner_id, conversation_id)
        catalog = self.snapshot.catalog() if hasattr(self.snapshot, "catalog") else {}
        history_chars = sum(len(m["content"]) for m in history["messages"])
        fixed = (
            len(content)
            + history_chars
            + len(json.dumps(validated_context))
            + len(json.dumps(catalog, ensure_ascii=False))
        )
        reserve_tokens = max(
            2_000, (fixed + 2 * self.config.max_tool_calls * self.config.max_tool_result_bytes) // 4 + 4_096
        )
        # The pilot floor applies to paid provider calls. Mock mode stays usable
        # under the existing conservative cost budgets without pretending to
        # consume the OpenAI token allowance.
        if self.config.provider == "openai":
            reserve_tokens = max(reserve_tokens, self.config.minimum_turn_reservation_tokens)
        reserve_cost = self.config.reservation_cost_usd(reserve_tokens)
        turn, duplicate = self.store.submit_turn(
            owner_id,
            conversation_id,
            content,
            client_message_id,
            validated_context,
            max_active_per_user=self.config.max_active_per_user,
            reserved_tokens=reserve_tokens,
            reserved_cost_usd=reserve_cost,
            user_token_budget=self.config.daily_token_budget_user,
            global_token_budget=self.config.daily_token_budget_global,
            user_cost_budget=self.config.daily_cost_budget_user_usd,
            global_cost_budget=self.config.daily_cost_budget_global_usd,
            max_active_global=self.config.max_concurrent_global,
        )
        return {"turn_id": turn["id"], "status": turn["status"], "deduplicated": duplicate}

    def health(self) -> dict[str, Any]:
        return {
            "status": "ok",
            "admission_enabled": self.config.admission_enabled,
            "provider": self.config.provider,
            "snapshot_version": self.snapshot_version,
            "worker_running": bool(self.worker and self.worker.running),
        }


__all__ = ["ChatService", "InvalidRequest", "validate_context"]
