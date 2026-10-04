"""Usage accounting, turn finalization, retention, and provider cleanup."""

from __future__ import annotations

import sqlite3
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from ._storage_common import utcnow


class UsageRetentionMixin:
    def complete_turn(
        self,
        turn_id: str,
        content: str,
        payload: dict[str, Any],
        input_tokens: int,
        output_tokens: int,
        cost: float,
        usage_complete: bool = False,
    ) -> bool:
        now = utcnow()
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT conversation_id,owner_id,status FROM turns WHERE id=?", (turn_id,)
            ).fetchone()
            if row is None or row["status"] != "running":
                db.execute("COMMIT")
                return False
            db.execute(
                "UPDATE turns SET status='completed',completed_at=?,estimated_input_tokens=?,"
                "estimated_output_tokens=?,estimated_cost_usd=? WHERE id=?",
                (now, input_tokens, output_tokens, cost, turn_id),
            )
            db.execute(
                "INSERT INTO messages(id,conversation_id,turn_id,owner_id,role,content,"
                "payload_json,created_at) "
                "VALUES(?,?,?,?, 'assistant',?,?,?)",
                (
                    str(uuid.uuid4()),
                    row["conversation_id"],
                    turn_id,
                    row["owner_id"],
                    content,
                    self._dump(payload),
                    now,
                ),
            )
            self._append_event_db(db, turn_id, "message.completed", {"content": content, **payload})
            self._append_event_db(db, turn_id, "turn.completed", {"status": "completed"})
            if usage_complete:
                self._add_usage_db(db, row["owner_id"], input_tokens, output_tokens, cost)
                db.execute(
                    "UPDATE turns SET usage_complete=1,reserved_tokens=0,reserved_cost_usd=0 WHERE id=?",
                    (turn_id,),
                )
            # If provider usage is unavailable, keep the conservative hold for
            # the rest of the current usage window instead of claiming $0.
            db.execute("COMMIT")
        return True

    def fail_turn(self, turn_id: str, code: str, message: str) -> None:
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT status FROM turns WHERE id=?", (turn_id,)).fetchone()
            if row is not None and row[0] == "running":
                db.execute(
                    "UPDATE turns SET status='failed',completed_at=?,error_code=?,error_message=? WHERE id=?",
                    (utcnow(), code, message[:500], turn_id),
                )
                self._append_event_db(db, turn_id, "turn.failed", {"code": code, "message": message[:500]})
            db.execute("COMMIT")

    def usage(self, owner_id: str | None = None) -> dict[str, float | int]:
        today = datetime.now(UTC).date().isoformat()
        with self._connect() as db:
            if owner_id:
                row = db.execute(
                    "SELECT COALESCE(SUM(input_tokens),0),COALESCE(SUM(output_tokens),0),"
                    "COALESCE(SUM(estimated_cost_usd),0),COALESCE(SUM(turn_count),0) "
                    "FROM usage_daily WHERE usage_date=? AND owner_id=?",
                    (today, owner_id),
                ).fetchone()
                incomplete = db.execute(
                    "SELECT COUNT(*) FROM turns WHERE owner_id=? AND reserved_usage_date=? "
                    "AND usage_complete=0",
                    (owner_id, today),
                ).fetchone()[0]
            else:
                row = db.execute(
                    "SELECT COALESCE(SUM(input_tokens),0),COALESCE(SUM(output_tokens),0),"
                    "COALESCE(SUM(estimated_cost_usd),0),COALESCE(SUM(turn_count),0) "
                    "FROM usage_daily WHERE usage_date=?",
                    (today,),
                ).fetchone()
                incomplete = db.execute(
                    "SELECT COUNT(*) FROM turns WHERE reserved_usage_date=? AND usage_complete=0", (today,)
                ).fetchone()[0]
        return {
            "input_tokens": row[0],
            "output_tokens": row[1],
            "estimated_cost_usd": row[2],
            "turn_count": row[3],
            "usage_incomplete_turns": incomplete,
        }

    @staticmethod
    def _add_usage_db(db: sqlite3.Connection, owner: str, inp: int, out: int, cost: float) -> None:
        day = datetime.now(UTC).date().isoformat()
        db.execute(
            "INSERT INTO usage_daily(usage_date,owner_id,input_tokens,output_tokens,"
            "estimated_cost_usd,turn_count) "
            "VALUES(?,?,?,?,?,1) ON CONFLICT(usage_date,owner_id) DO UPDATE SET "
            "input_tokens=input_tokens+excluded.input_tokens,"
            "output_tokens=output_tokens+excluded.output_tokens,"
            "estimated_cost_usd=estimated_cost_usd+excluded.estimated_cost_usd,turn_count=turn_count+1",
            (day, owner, inp, out, cost),
        )

    def cleanup_expired(self, retention_days: int) -> int:
        cutoff = (datetime.now(UTC) - timedelta(days=retention_days)).isoformat(timespec="milliseconds")
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute(
                "INSERT OR IGNORE INTO provider_deletions(session_id,queued_at) "
                "SELECT provider_session_id,? FROM conversations "
                "WHERE updated_at < ? AND provider_session_id IS NOT NULL",
                (utcnow(), cutoff),
            )
            cur = db.execute(
                "DELETE FROM conversations WHERE updated_at < ? AND NOT EXISTS "
                "(SELECT 1 FROM turns WHERE turns.conversation_id=conversations.id "
                "AND turns.status IN ('pending','running'))",
                (cutoff,),
            )
            db.execute("COMMIT")
            return cur.rowcount

    def queue_provider_deletion(self, session_id: str) -> None:
        if not session_id:
            return
        with self._connect() as db:
            db.execute(
                "INSERT OR IGNORE INTO provider_deletions(session_id,queued_at) VALUES(?,?)",
                (session_id, utcnow()),
            )

    def pending_provider_deletions(self, limit: int = 20) -> list[str]:
        with self._connect() as db:
            now = utcnow()
            return [
                row[0]
                for row in db.execute(
                    "SELECT session_id FROM provider_deletions WHERE next_attempt_at<=? "
                    "ORDER BY queued_at LIMIT ?",
                    (now, limit),
                ).fetchall()
            ]

    def complete_provider_deletion(self, session_id: str) -> None:
        with self._connect() as db:
            db.execute("DELETE FROM provider_deletions WHERE session_id=?", (session_id,))

    def failed_provider_deletion(self, session_id: str) -> None:
        with self._connect() as db:
            row = db.execute(
                "SELECT attempts FROM provider_deletions WHERE session_id=?", (session_id,)
            ).fetchone()
            if row:
                delay = min(3600, 5 * (2 ** min(int(row[0]), 10)))
                retry_at = (datetime.now(UTC) + timedelta(seconds=delay)).isoformat(timespec="milliseconds")
                db.execute(
                    "UPDATE provider_deletions SET attempts=attempts+1,next_attempt_at=? WHERE session_id=?",
                    (retry_at, session_id),
                )
