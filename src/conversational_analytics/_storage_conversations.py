"""Conversation and admission transactions for the chat SQLite store."""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import UTC, datetime
from typing import Any

from ._storage_common import AdmissionDenied, Conflict, NotFound, utcnow


class ConversationStoreMixin:
    def create_conversation(
        self,
        owner_id: str,
        snapshot_version: str,
        semantic_version: str = "",
        model: str | None = None,
        reasoning_effort: str | None = None,
        text_verbosity: str | None = None,
        provider: str | None = None,
    ) -> dict[str, Any]:
        now, conv_id = utcnow(), str(uuid.uuid4())
        with self._connect() as db:
            db.execute(
                "INSERT INTO conversations(id,owner_id,snapshot_version,semantic_version,model,"
                "reasoning_effort,text_verbosity,provider,created_at,updated_at) "
                "VALUES(?,?,?,?,?,?,?,?,?,?)",
                (
                    conv_id,
                    owner_id,
                    snapshot_version,
                    semantic_version,
                    model,
                    reasoning_effort,
                    text_verbosity,
                    provider,
                    now,
                    now,
                ),
            )
        return {
            "id": conv_id,
            "snapshot_version": snapshot_version,
            "semantic_version": semantic_version,
            "model": model,
            "reasoning_effort": reasoning_effort,
            "text_verbosity": text_verbosity,
            "provider": provider,
            "created_at": now,
        }

    def get_conversation(self, owner_id: str, conversation_id: str) -> dict[str, Any]:
        with self._connect() as db:
            conv = db.execute(
                "SELECT id,snapshot_version,semantic_version,provider_session_id,model,reasoning_effort,"
                "text_verbosity,provider,"
                "created_at FROM conversations "
                "WHERE id=? AND owner_id=?",
                (conversation_id, owner_id),
            ).fetchone()
            if not conv:
                raise NotFound("conversation not found")
            messages = db.execute(
                "SELECT id,role,content,turn_id,created_at,payload_json FROM messages "
                "WHERE conversation_id=? AND owner_id=? ORDER BY created_at,id",
                (conversation_id, owner_id),
            ).fetchall()
            turns = db.execute(
                "SELECT id,status,created_at,started_at,completed_at,error_code,error_message,"
                "estimated_input_tokens,estimated_output_tokens,estimated_cost_usd,model,"
                "reasoning_effort,text_verbosity FROM turns "
                "WHERE conversation_id=? AND owner_id=? ORDER BY created_at,id",
                (conversation_id, owner_id),
            ).fetchall()
        return {
            **dict(conv),
            "messages": [
                {
                    **{k: row[k] for k in ("id", "role", "content", "turn_id", "created_at")},
                    **{
                        k: v
                        for k, v in json.loads(row["payload_json"]).items()
                        if k in {"references", "chart"}
                    },
                }
                for row in messages
            ],
            "turns": [dict(row) for row in turns],
        }

    def delete_conversation(self, owner_id: str, conversation_id: str) -> None:
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            self._preserve_usage_tombstones_db(db, conversation_id=conversation_id, owner_id=owner_id)
            cur = db.execute(
                "DELETE FROM conversations WHERE id=? AND owner_id=?", (conversation_id, owner_id)
            )
            if cur.rowcount == 0:
                raise NotFound("conversation not found")
            db.execute("COMMIT")

    def owned_conversation(self, owner_id: str, conversation_id: str) -> dict[str, Any]:
        with self._connect() as db:
            row = db.execute(
                "SELECT id,provider_session_id FROM conversations WHERE id=? AND owner_id=?",
                (conversation_id, owner_id),
            ).fetchone()
            if not row:
                raise NotFound("conversation not found")
            turns = db.execute(
                "SELECT id,status FROM turns WHERE conversation_id=? AND owner_id=?",
                (conversation_id, owner_id),
            ).fetchall()
        return {
            "id": row["id"],
            "provider_session_id": row["provider_session_id"],
            "turns": [dict(t) for t in turns],
        }

    def submit_turn(
        self,
        owner_id: str,
        conversation_id: str,
        content: str,
        client_message_id: str,
        context: dict[str, Any],
        max_active_per_user: int = 1,
        reserved_tokens: int = 0,
        reserved_cost_usd: float = 0.0,
        user_token_budget: int = 100_000,
        global_token_budget: int = 500_000,
        user_cost_budget: float = 2.0,
        global_cost_budget: float = 10.0,
        max_active_global: int = 2,
        model: str | None = None,
        reasoning_effort: str | None = None,
        text_verbosity: str | None = None,
        provider: str | None = None,
    ) -> tuple[dict[str, Any], bool]:
        now = utcnow()
        turn_id = str(uuid.uuid4())
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            conv = db.execute(
                "SELECT id FROM conversations WHERE id=? AND owner_id=?", (conversation_id, owner_id)
            ).fetchone()
            if not conv:
                raise NotFound("conversation not found")
            existing = db.execute(
                "SELECT id,status,created_at,user_content,context_json FROM turns "
                "WHERE owner_id=? AND conversation_id=? AND client_message_id=?",
                (owner_id, conversation_id, client_message_id),
            ).fetchone()
            if existing:
                if existing["user_content"] != content or json.loads(existing["context_json"]) != context:
                    raise Conflict("client_message_id was already used with different content or context")
                db.execute("COMMIT")
                return {key: existing[key] for key in ("id", "status", "created_at")}, True
            if self._external_unknown_count_db(db):
                raise AdmissionDenied("external usage reconciliation is incomplete")
            active_user = db.execute(
                "SELECT COUNT(*) FROM turns WHERE owner_id=? AND status IN ('pending','running')", (owner_id,)
            ).fetchone()[0]
            if active_user >= max_active_per_user:
                raise AdmissionDenied("active turn limit reached")
            active_global = db.execute(
                "SELECT COUNT(*) FROM turns WHERE status IN ('pending','running')"
            ).fetchone()[0]
            if active_global >= max_active_global:
                raise AdmissionDenied("global active turn limit reached")
            usage_day = datetime.now(UTC).date().isoformat()
            user_usage = db.execute(
                "SELECT COALESCE(SUM(input_tokens+output_tokens),0),"
                "COALESCE(SUM(estimated_cost_usd),0) FROM usage_daily WHERE usage_date=? AND owner_id=?",
                (usage_day, owner_id),
            ).fetchone()
            global_usage = db.execute(
                "SELECT COALESCE(SUM(input_tokens+output_tokens),0),"
                "COALESCE(SUM(estimated_cost_usd),0) FROM usage_daily WHERE usage_date=?",
                (usage_day,),
            ).fetchone()
            ext_user = self._external_usage_totals_db(db, usage_day, owner_id)
            ext_global = self._external_usage_totals_db(db, usage_day)
            user_usage = (user_usage[0] + ext_user[0] + ext_user[1], user_usage[1] + ext_user[2])
            global_usage = (
                global_usage[0] + ext_global[0] + ext_global[1],
                global_usage[1] + ext_global[2],
            )
            user_holds = self._usage_hold_totals_db(db, owner_id)
            global_holds = self._usage_hold_totals_db(db)
            if (
                user_usage[0] + user_holds[0] + reserved_tokens > user_token_budget
                or global_usage[0] + global_holds[0] + reserved_tokens > global_token_budget
            ):
                raise AdmissionDenied("daily token budget exhausted")
            if (
                user_usage[1] + user_holds[1] + reserved_cost_usd > user_cost_budget
                or global_usage[1] + global_holds[1] + reserved_cost_usd > global_cost_budget
            ):
                raise AdmissionDenied("daily cost budget exhausted")
            try:
                db.execute(
                    "INSERT INTO turns(id,conversation_id,owner_id,client_message_id,status,user_content,"
                    "context_json,created_at,reserved_tokens,reserved_cost_usd,reserved_usage_date,"
                    "model,reasoning_effort,text_verbosity,provider) "
                    "VALUES(?,?,?,?, 'pending',?,?,?,?,?,?,?,?,?,?)",
                    (
                        turn_id,
                        conversation_id,
                        owner_id,
                        client_message_id,
                        content,
                        self._dump(context),
                        now,
                        reserved_tokens,
                        reserved_cost_usd,
                        usage_day,
                        model,
                        reasoning_effort,
                        text_verbosity,
                        provider,
                    ),
                )
            except sqlite3.IntegrityError as exc:
                raise Conflict("conversation already has an active turn") from exc
            db.execute(
                "INSERT INTO messages(id,conversation_id,turn_id,owner_id,role,content,created_at) "
                "VALUES(?,?,?,?, 'user',?,?)",
                (str(uuid.uuid4()), conversation_id, turn_id, owner_id, content, now),
            )
            db.execute("UPDATE conversations SET updated_at=? WHERE id=?", (now, conversation_id))
            db.execute(
                "INSERT INTO turn_events(turn_id,seq,event_type,payload_json,created_at) "
                "VALUES(?,1,'turn.queued',?,?)",
                (turn_id, self._dump({"status": "pending"}), now),
            )
            db.execute("COMMIT")
        return {"id": turn_id, "status": "pending", "created_at": now}, False

