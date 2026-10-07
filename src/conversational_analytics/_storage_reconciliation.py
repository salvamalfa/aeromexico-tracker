"""Fenced restoration of one exact completed provider turn."""

from __future__ import annotations

import json
import uuid
from typing import Any

from ._storage_common import NotFound, utcnow


class TurnReconciliationMixin:
    def reconcile_failed_provider_turn(
        self,
        *,
        turn_id: str,
        owner_id: str,
        conversation_id: str,
        snapshot_version: str,
        semantic_version: str,
        provider_session_id: str,
        provider_turn_id: str,
        content: str,
        payload: dict[str, Any],
        input_tokens: int,
        output_tokens: int,
        cost: float,
    ) -> bool:
        """Restore one exact completed provider turn after a local provider error."""
        identities = (
            turn_id,
            owner_id,
            conversation_id,
            snapshot_version,
            semantic_version,
            provider_session_id,
            provider_turn_id,
        )
        if (
            any(not isinstance(value, str) or not value for value in identities)
            or not isinstance(content, str)
            or not content.strip()
            or not isinstance(payload, dict)
            or any(
                isinstance(value, bool) or not isinstance(value, int) or value < 0
                for value in (input_tokens, output_tokens)
            )
            or isinstance(cost, bool)
            or not isinstance(cost, (int, float))
            or cost < 0
        ):
            raise ValueError("invalid recovered turn data")

        now = utcnow()
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT t.*,c.owner_id AS conversation_owner,c.snapshot_version,c.semantic_version,"
                "c.provider_session_id FROM turns t JOIN conversations c ON c.id=t.conversation_id "
                "WHERE t.id=?",
                (turn_id,),
            ).fetchone()
            if row is None:
                db.execute("ROLLBACK")
                return False
            if (
                row["owner_id"] != owner_id
                or row["conversation_owner"] != owner_id
                or row["conversation_id"] != conversation_id
                or row["snapshot_version"] != snapshot_version
                or row["semantic_version"] != semantic_version
                or row["provider_session_id"] != provider_session_id
                or row["provider_turn_id"] != provider_turn_id
                or row["status"] != "failed"
                or row["error_code"] != "provider_error"
            ):
                db.execute("ROLLBACK")
                return False

            later_turn = db.execute(
                "SELECT 1 FROM turns WHERE conversation_id=? AND id<>? AND created_at>=? LIMIT 1",
                (conversation_id, turn_id, row["created_at"]),
            ).fetchone()
            pending_deletion = db.execute(
                "SELECT 1 FROM provider_deletions WHERE session_id=?", (provider_session_id,)
            ).fetchone()
            assistant_message = db.execute(
                "SELECT 1 FROM messages WHERE turn_id=? AND role='assistant' LIMIT 1", (turn_id,)
            ).fetchone()
            unsafe_event = db.execute(
                "SELECT 1 FROM turn_events WHERE turn_id=? AND event_type IN "
                "('turn.cancelled','turn.timeout','turn.timed_out','provider.failure') LIMIT 1",
                (turn_id,),
            ).fetchone()
            if later_turn or pending_deletion or assistant_message or unsafe_event:
                db.execute("ROLLBACK")
                return False

            expected_cost = float(cost)
            if row["usage_complete"] and (
                row["estimated_input_tokens"] != input_tokens
                or row["estimated_output_tokens"] != output_tokens
                or abs(float(row["estimated_cost_usd"]) - expected_cost) > 1e-12
            ):
                db.execute("ROLLBACK")
                return False

            db.execute(
                "UPDATE turns SET status='completed',completed_at=?,error_code=NULL,error_message=NULL,"
                "estimated_input_tokens=?,estimated_output_tokens=?,estimated_cost_usd=? WHERE id=?",
                (now, input_tokens, output_tokens, expected_cost, turn_id),
            )
            db.execute(
                "INSERT INTO messages(id,conversation_id,turn_id,owner_id,role,content,payload_json,"
                "created_at) VALUES(?,?,?,?, 'assistant',?,?,?)",
                (
                    str(uuid.uuid4()),
                    conversation_id,
                    turn_id,
                    owner_id,
                    content,
                    self._dump(payload),
                    now,
                ),
            )
            self._append_event_db(db, turn_id, "message.completed", {"content": content, **payload})
            self._append_event_db(db, turn_id, "turn.completed", {"status": "completed"})
            self._append_event_db(
                db,
                turn_id,
                "turn.reconciled",
                {
                    "source": "provider_completed_turn",
                    "provider_session_id": provider_session_id,
                    "provider_turn_id": provider_turn_id,
                },
            )
            if not row["usage_complete"]:
                self._add_usage_db(db, owner_id, input_tokens, output_tokens, expected_cost)
            db.execute(
                "UPDATE turns SET usage_complete=1,reserved_tokens=0,reserved_cost_usd=0 WHERE id=?",
                (turn_id,),
            )
            db.execute("COMMIT")
        return True

    def turn_reconciliation_metadata(self, owner_id: str, turn_id: str) -> dict[str, Any]:
        """Return non-content metadata for the protected reconciliation CLI."""
        with self._connect() as db:
            row = db.execute(
                "SELECT t.id,t.owner_id,t.conversation_id,t.status,t.error_code,t.usage_complete,"
                "t.provider_turn_id,c.snapshot_version,c.semantic_version,c.provider_session_id "
                "FROM turns t JOIN conversations c ON c.id=t.conversation_id "
                "WHERE t.id=? AND t.owner_id=?",
                (turn_id, owner_id),
            ).fetchone()
            if row is None:
                raise NotFound("turn not found")
            later = db.execute(
                "SELECT 1 FROM turns WHERE conversation_id=? AND id<>? AND "
                "created_at>=(SELECT created_at FROM turns WHERE id=?) LIMIT 1",
                (row["conversation_id"], turn_id, turn_id),
            ).fetchone()
            assistant = db.execute(
                "SELECT 1 FROM messages WHERE turn_id=? AND role='assistant' LIMIT 1", (turn_id,)
            ).fetchone()
            queued = db.execute(
                "SELECT 1 FROM provider_deletions WHERE session_id=?", (row["provider_session_id"],)
            ).fetchone()
            unsafe = db.execute(
                "SELECT 1 FROM turn_events WHERE turn_id=? AND event_type IN "
                "('turn.cancelled','turn.timeout','turn.timed_out','provider.failure') LIMIT 1",
                (turn_id,),
            ).fetchone()
        return {
            "turn_id": row["id"],
            "owner_id": row["owner_id"],
            "conversation_id": row["conversation_id"],
            "status": row["status"],
            "error_code": row["error_code"],
            "usage_complete": bool(row["usage_complete"]),
            "has_provider_turn_id": bool(row["provider_turn_id"]),
            "has_provider_session_id": bool(row["provider_session_id"]),
            "has_snapshot_version": bool(row["snapshot_version"]),
            "has_semantic_version": bool(row["semantic_version"]),
            "has_later_turn": bool(later),
            "has_assistant_message": bool(assistant),
            "provider_deletion_queued": bool(queued),
            "has_cancel_or_timeout_event": bool(unsafe),
            "provider_turn_id": row["provider_turn_id"],
            "provider_session_id": row["provider_session_id"],
            "snapshot_version": row["snapshot_version"],
            "semantic_version": row["semantic_version"],
        }

    def reconciliation_tool_results(self, turn_id: str) -> list[dict[str, Any]]:
        """Read locally persisted tool outputs for a private reconciliation."""
        with self._connect() as db:
            rows = db.execute(
                "SELECT provider_turn_id,call_id,tool_name,args_json,result_json FROM tool_results "
                "WHERE turn_id=? ORDER BY created_at,call_id",
                (turn_id,),
            ).fetchall()
        return [
            {
                "provider_turn_id": row["provider_turn_id"],
                "call_id": row["call_id"],
                "tool_name": row["tool_name"],
                "arguments": json.loads(row["args_json"]),
                "result": json.loads(row["result_json"]),
            }
            for row in rows
        ]
