"""Usage accounting, turn finalization, retention, and provider cleanup."""

from __future__ import annotations

import sqlite3
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from ._storage_common import utcnow


class UsageRetentionMixin:
    @staticmethod
    def _initialize_usage_tombstones(db: sqlite3.Connection) -> None:
        """Keep billing-only rows independent from conversation content and cascades."""
        db.executescript(
            """
            CREATE TABLE IF NOT EXISTS usage_tombstones (
                turn_id TEXT PRIMARY KEY,
                owner_id TEXT NOT NULL,
                usage_date TEXT NOT NULL,
                reserved_tokens INTEGER NOT NULL,
                reserved_cost_usd REAL NOT NULL,
                status TEXT NOT NULL CHECK(status IN ('unknown','booked')),
                input_tokens INTEGER,
                output_tokens INTEGER,
                estimated_cost_usd REAL
            );
            CREATE INDEX IF NOT EXISTS usage_tombstones_hold_idx
                ON usage_tombstones(status, owner_id, usage_date);
            """
        )

    @staticmethod
    def _preserve_usage_tombstones_db(
        db: sqlite3.Connection,
        *,
        conversation_id: str | None = None,
        owner_id: str | None = None,
        retention_cutoff: str | None = None,
    ) -> None:
        """Copy unresolved paid holds only; never copy conversation or provider content."""
        today = datetime.now(UTC).date().isoformat()
        if retention_cutoff is not None:
            db.execute(
                "INSERT OR IGNORE INTO usage_tombstones "
                "(turn_id,owner_id,usage_date,reserved_tokens,reserved_cost_usd,status) "
                "SELECT t.id,t.owner_id,COALESCE(NULLIF(t.reserved_usage_date,''),?),"
                "t.reserved_tokens,t.reserved_cost_usd,'unknown' "
                "FROM turns t JOIN conversations c ON c.id=t.conversation_id "
                "WHERE c.updated_at<? AND t.status!='pending' AND t.usage_complete=0 "
                "AND NOT EXISTS (SELECT 1 FROM turns active WHERE active.conversation_id=c.id "
                "AND active.status IN ('pending','running'))",
                (today, retention_cutoff),
            )
            return
        if conversation_id is None or owner_id is None:
            raise ValueError("conversation_id and owner_id are required without retention_cutoff")
        db.execute(
            "INSERT OR IGNORE INTO usage_tombstones "
            "(turn_id,owner_id,usage_date,reserved_tokens,reserved_cost_usd,status) "
            "SELECT id,owner_id,COALESCE(NULLIF(reserved_usage_date,''),?),"
            "reserved_tokens,reserved_cost_usd,'unknown' FROM turns "
            "WHERE conversation_id=? AND owner_id=? AND status!='pending' AND usage_complete=0",
            (today, conversation_id, owner_id),
        )

    @staticmethod
    def _usage_hold_totals_db(db: sqlite3.Connection, owner_id: str | None = None) -> tuple[int, float]:
        if owner_id is None:
            turns = db.execute(
                "SELECT COALESCE(SUM(reserved_tokens),0),COALESCE(SUM(reserved_cost_usd),0) "
                "FROM turns WHERE status IN ('pending','running') OR usage_complete=0"
            ).fetchone()
            tombstones = db.execute(
                "SELECT COALESCE(SUM(reserved_tokens),0),COALESCE(SUM(reserved_cost_usd),0) "
                "FROM usage_tombstones WHERE status='unknown'"
            ).fetchone()
            external = db.execute(
                "SELECT COALESCE(SUM(reserved_tokens),0),COALESCE(SUM(reserved_cost_usd),0) "
                "FROM external_usage WHERE status='unknown'"
            ).fetchone()
        else:
            turns = db.execute(
                "SELECT COALESCE(SUM(reserved_tokens),0),COALESCE(SUM(reserved_cost_usd),0) "
                "FROM turns WHERE owner_id=? AND (status IN ('pending','running') OR usage_complete=0)",
                (owner_id,),
            ).fetchone()
            tombstones = db.execute(
                "SELECT COALESCE(SUM(reserved_tokens),0),COALESCE(SUM(reserved_cost_usd),0) "
                "FROM usage_tombstones WHERE owner_id=? AND status='unknown'",
                (owner_id,),
            ).fetchone()
            external = db.execute(
                "SELECT COALESCE(SUM(reserved_tokens),0),COALESCE(SUM(reserved_cost_usd),0) "
                "FROM external_usage WHERE owner_id=? AND status='unknown'",
                (owner_id,),
            ).fetchone()
        return int(turns[0] + tombstones[0] + external[0]), float(turns[1] + tombstones[1] + external[1])

    @staticmethod
    def _usage_incomplete_count_db(db: sqlite3.Connection, owner_id: str | None = None) -> int:
        if owner_id is None:
            turns = db.execute("SELECT COUNT(*) FROM turns WHERE usage_complete=0").fetchone()[0]
            tombstones = db.execute(
                "SELECT COUNT(*) FROM usage_tombstones WHERE status='unknown'"
            ).fetchone()[0]
            external = db.execute("SELECT COUNT(*) FROM external_usage WHERE status='unknown'").fetchone()[0]
        else:
            turns = db.execute(
                "SELECT COUNT(*) FROM turns WHERE owner_id=? AND usage_complete=0", (owner_id,)
            ).fetchone()[0]
            tombstones = db.execute(
                "SELECT COUNT(*) FROM usage_tombstones WHERE owner_id=? AND status='unknown'", (owner_id,)
            ).fetchone()[0]
            external = db.execute(
                "SELECT COUNT(*) FROM external_usage WHERE owner_id=? AND status='unknown'", (owner_id,)
            ).fetchone()[0]
        return int(turns + tombstones + external)

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
            # If provider usage is unavailable, keep the conservative hold
            # across UTC date boundaries instead of claiming $0.
            db.execute("COMMIT")
        return True

    def fail_turn(
        self, turn_id: str, code: str, message: str, usage: tuple[int, int, float] | None = None
    ) -> None:
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
        if usage is not None:
            self.record_terminal_usage(turn_id, *usage)

    def record_terminal_usage(self, turn_id: str, input_tokens: int, output_tokens: int, cost: float) -> None:
        """Book confirmed terminal usage once, including after its content was deleted."""
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT owner_id,status,usage_complete FROM turns WHERE id=?", (turn_id,)
            ).fetchone()
            if (
                row is not None
                and row["status"] in {"completed", "failed", "cancelled"}
                and not row["usage_complete"]
            ):
                self._add_usage_db(db, row["owner_id"], input_tokens, output_tokens, cost)
                db.execute(
                    "UPDATE turns SET usage_complete=1,reserved_tokens=0,reserved_cost_usd=0,"
                    "estimated_input_tokens=?,estimated_output_tokens=?,estimated_cost_usd=? WHERE id=?",
                    (input_tokens, output_tokens, cost, turn_id),
                )
            elif row is None:
                hold = db.execute(
                    "SELECT owner_id,usage_date,status FROM usage_tombstones WHERE turn_id=?",
                    (turn_id,),
                ).fetchone()
                if hold is not None and hold["status"] == "unknown":
                    self._add_usage_db(
                        db,
                        hold["owner_id"],
                        input_tokens,
                        output_tokens,
                        cost,
                    )
                    db.execute(
                        "UPDATE usage_tombstones SET status='booked',reserved_tokens=0,"
                        "reserved_cost_usd=0,input_tokens=?,output_tokens=?,estimated_cost_usd=? "
                        "WHERE turn_id=? AND status='unknown'",
                        (input_tokens, output_tokens, cost, turn_id),
                    )
            db.execute("COMMIT")

    def usage(self, owner_id: str | None = None) -> dict[str, float | int]:
        today = datetime.now(UTC).date().isoformat()
        # Totals stay on the current UTC day; unresolved holds remain visible
        # across dates until confirmed provider usage releases them.
        with self._connect() as db:
            if owner_id:
                row = db.execute(
                    "SELECT COALESCE(SUM(input_tokens),0),COALESCE(SUM(output_tokens),0),"
                    "COALESCE(SUM(estimated_cost_usd),0),COALESCE(SUM(turn_count),0) "
                    "FROM usage_daily WHERE usage_date=? AND owner_id=?",
                    (today, owner_id),
                ).fetchone()
                external = self._external_usage_totals_db(db, today, owner_id)
                incomplete = self._usage_incomplete_count_db(db, owner_id)
            else:
                row = db.execute(
                    "SELECT COALESCE(SUM(input_tokens),0),COALESCE(SUM(output_tokens),0),"
                    "COALESCE(SUM(estimated_cost_usd),0),COALESCE(SUM(turn_count),0) "
                    "FROM usage_daily WHERE usage_date=?",
                    (today,),
                ).fetchone()
                external = self._external_usage_totals_db(db, today)
                incomplete = self._usage_incomplete_count_db(db)
        return {
            "input_tokens": row[0] + external[0],
            "output_tokens": row[1] + external[1],
            "estimated_cost_usd": row[2] + external[2],
            "turn_count": row[3],
            "usage_incomplete_turns": incomplete,
        }

    @staticmethod
    def _add_usage_db(db: sqlite3.Connection, owner: str, inp: int, out: int, cost: float) -> None:
        # Known usage is booked on the UTC day it is confirmed, using configured
        # per-token prices; the original reservation date remains on a tombstone.
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
            # Same predicate for both statements: never queue remote deletion
            # for a conversation that is kept because it still has a live turn.
            expired = (
                "updated_at < ? AND NOT EXISTS (SELECT 1 FROM turns WHERE "
                "turns.conversation_id=conversations.id AND turns.status IN ('pending','running'))"
            )
            self._preserve_usage_tombstones_db(db, retention_cutoff=cutoff)
            db.execute(
                "INSERT OR IGNORE INTO provider_deletions(session_id,queued_at) "
                f"SELECT provider_session_id,? FROM conversations WHERE {expired} "
                "AND provider_session_id IS NOT NULL",
                (utcnow(), cutoff),
            )
            cur = db.execute(f"DELETE FROM conversations WHERE {expired}", (cutoff,))
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
