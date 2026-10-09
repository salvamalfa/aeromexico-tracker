"""Durable, owner-scoped SQLite state for chat conversations and turns."""

from __future__ import annotations

import json
import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from ._storage_auth import AuthSessionMixin
from ._storage_common import AdmissionDenied, ChatError, Conflict, NotFound, utcnow
from ._storage_conversations import ConversationStoreMixin
from ._storage_external_usage import ExternalUsageMixin
from ._storage_reconciliation import TurnReconciliationMixin
from ._storage_tools import ToolResultMixin
from ._storage_usage import UsageRetentionMixin

__all__ = ["AdmissionDenied", "ChatError", "ChatStore", "Conflict", "NotFound", "utcnow"]


class ChatStore(
    TurnReconciliationMixin, ToolResultMixin, UsageRetentionMixin, ExternalUsageMixin, AuthSessionMixin,
    ConversationStoreMixin,
):
    """SQLite store. Every operation opens its own connection for thread safety."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self._lock = threading.RLock()
        if str(path) != ":memory:":
            self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    @contextmanager
    def _connect(self):
        conn = sqlite3.connect(str(self.path), timeout=30, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA busy_timeout=30000")
        if str(self.path) != ":memory:":
            conn.execute("PRAGMA journal_mode=WAL")
        try:
            yield conn
        finally:
            conn.close()

    def _initialize(self) -> None:
        with self._lock, self._connect() as db:
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS conversations (
                    id TEXT PRIMARY KEY,
                    owner_id TEXT NOT NULL,
                    snapshot_version TEXT NOT NULL,
                    semantic_version TEXT NOT NULL DEFAULT '',
                    provider_session_id TEXT,
                    provider TEXT,
                    model TEXT,
                    reasoning_effort TEXT,
                    text_verbosity TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS conversation_owner_idx ON conversations(owner_id, created_at);
                CREATE TABLE IF NOT EXISTS turns (
                    id TEXT PRIMARY KEY,
                    conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
                    owner_id TEXT NOT NULL,
                    client_message_id TEXT NOT NULL,
                    status TEXT NOT NULL CHECK(status IN (
                        'pending','running','completed','failed','cancelled'
                    )),
                    user_content TEXT NOT NULL,
                    context_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    started_at TEXT,
                    completed_at TEXT,
                    error_code TEXT,
                    error_message TEXT,
                    estimated_input_tokens INTEGER NOT NULL DEFAULT 0,
                    estimated_output_tokens INTEGER NOT NULL DEFAULT 0,
                    estimated_cost_usd REAL NOT NULL DEFAULT 0,
                    reserved_tokens INTEGER NOT NULL DEFAULT 0,
                    reserved_cost_usd REAL NOT NULL DEFAULT 0,
                    usage_complete INTEGER NOT NULL DEFAULT 0,
                    reserved_usage_date TEXT NOT NULL DEFAULT '',
                    provider_turn_id TEXT,
                    provider_event_id TEXT,
                    provider_event_type TEXT,
                    model TEXT,
                    reasoning_effort TEXT,
                    text_verbosity TEXT,
                    provider TEXT,
                    UNIQUE(owner_id, conversation_id, client_message_id)
                );
                CREATE INDEX IF NOT EXISTS turns_status_idx ON turns(status, created_at);
                CREATE UNIQUE INDEX IF NOT EXISTS one_active_turn_per_conversation
                    ON turns(conversation_id) WHERE status IN ('pending','running');
                CREATE TABLE IF NOT EXISTS messages (
                    id TEXT PRIMARY KEY,
                    conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
                    turn_id TEXT NOT NULL REFERENCES turns(id) ON DELETE CASCADE,
                    owner_id TEXT NOT NULL,
                    role TEXT NOT NULL CHECK(role IN ('user','assistant')),
                    content TEXT NOT NULL,
                    payload_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS messages_conversation_idx ON messages(conversation_id, created_at);
                CREATE TABLE IF NOT EXISTS turn_events (
                    turn_id TEXT NOT NULL REFERENCES turns(id) ON DELETE CASCADE,
                    seq INTEGER NOT NULL,
                    event_type TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY(turn_id, seq)
                );
                CREATE TABLE IF NOT EXISTS tool_results (
                    turn_id TEXT NOT NULL REFERENCES turns(id) ON DELETE CASCADE,
                    provider_turn_id TEXT NOT NULL DEFAULT '',
                    call_id TEXT NOT NULL,
                    tool_name TEXT NOT NULL,
                    args_json TEXT NOT NULL,
                    result_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY(turn_id, call_id)
                );
                CREATE TABLE IF NOT EXISTS tool_calls (
                    turn_id TEXT NOT NULL REFERENCES turns(id) ON DELETE CASCADE,
                    provider_turn_id TEXT NOT NULL DEFAULT '',
                    call_id TEXT NOT NULL,
                    tool_name TEXT NOT NULL,
                    status TEXT NOT NULL CHECK(status IN ('running','completed','failed')),
                    created_at TEXT NOT NULL,
                    PRIMARY KEY(turn_id, call_id)
                );
                CREATE TABLE IF NOT EXISTS usage_daily (
                    usage_date TEXT NOT NULL,
                    owner_id TEXT NOT NULL,
                    input_tokens INTEGER NOT NULL,
                    output_tokens INTEGER NOT NULL,
                    estimated_cost_usd REAL NOT NULL,
                    turn_count INTEGER NOT NULL,
                    PRIMARY KEY(usage_date, owner_id)
                );
                CREATE TABLE IF NOT EXISTS provider_deletions (
                    session_id TEXT PRIMARY KEY,
                    queued_at TEXT NOT NULL,
                    attempts INTEGER NOT NULL DEFAULT 0,
                    next_attempt_at TEXT NOT NULL DEFAULT ''
                );
                """
            )
            # Existing pilot state remains readable when fields are added.
            columns = {row[1] for row in db.execute("PRAGMA table_info(turns)")}
            for name, declaration in (
                ("reserved_tokens", "INTEGER NOT NULL DEFAULT 0"),
                ("reserved_cost_usd", "REAL NOT NULL DEFAULT 0"),
                ("usage_complete", "INTEGER NOT NULL DEFAULT 0"),
                ("reserved_usage_date", "TEXT NOT NULL DEFAULT ''"),
            ):
                if name not in columns:
                    db.execute(f"ALTER TABLE turns ADD COLUMN {name} {declaration}")
            columns = {row[1] for row in db.execute("PRAGMA table_info(turns)")}
            for name in ("provider_turn_id", "provider_event_id", "provider_event_type"):
                if name not in columns:
                    db.execute(f"ALTER TABLE turns ADD COLUMN {name} TEXT")
            for name in ("model", "reasoning_effort", "text_verbosity"):
                if name not in columns:
                    db.execute(f"ALTER TABLE turns ADD COLUMN {name} TEXT")
            if "provider" not in columns:
                db.execute("ALTER TABLE turns ADD COLUMN provider TEXT")
            conv_columns = {row[1] for row in db.execute("PRAGMA table_info(conversations)")}
            if "semantic_version" not in conv_columns:
                db.execute("ALTER TABLE conversations ADD COLUMN semantic_version TEXT NOT NULL DEFAULT ''")
            conv_columns = {row[1] for row in db.execute("PRAGMA table_info(conversations)")}
            for name in ("model", "reasoning_effort", "text_verbosity"):
                if name not in conv_columns:
                    db.execute(f"ALTER TABLE conversations ADD COLUMN {name} TEXT")
            if "provider" not in conv_columns:
                db.execute("ALTER TABLE conversations ADD COLUMN provider TEXT")
            deletion_columns = {row[1] for row in db.execute("PRAGMA table_info(provider_deletions)")}
            if "next_attempt_at" not in deletion_columns:
                db.execute(
                    "ALTER TABLE provider_deletions ADD COLUMN next_attempt_at TEXT NOT NULL DEFAULT ''"
                )
            for table in ("tool_results", "tool_calls"):
                columns = {row[1] for row in db.execute(f"PRAGMA table_info({table})")}
                if "provider_turn_id" not in columns:
                    db.execute(f"ALTER TABLE {table} ADD COLUMN provider_turn_id TEXT NOT NULL DEFAULT ''")
            self._initialize_auth(db)
            self._initialize_usage_tombstones(db)
            self._initialize_external_usage(db)

    @staticmethod
    def _dump(obj: Any) -> str:
        return json.dumps(obj, ensure_ascii=False, separators=(",", ":"), allow_nan=False)

    def claim_turn(self) -> dict[str, Any] | None:
        """Atomically claim one pending turn. Running turns are never replayed."""
        now = utcnow()
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            if self._external_unknown_count_db(db):
                db.execute("COMMIT")
                return None
            row = db.execute(
                "SELECT t.*,c.provider_session_id,c.snapshot_version,c.semantic_version FROM turns t "
                "JOIN conversations c ON c.id=t.conversation_id WHERE t.status='pending' "
                "ORDER BY t.created_at,t.id LIMIT 1"
            ).fetchone()
            if row is None:
                db.execute("COMMIT")
                return None
            cur = db.execute(
                "UPDATE turns SET status='running',started_at=? WHERE id=? AND status='pending'",
                (now, row["id"]),
            )
            if cur.rowcount != 1:
                db.execute("COMMIT")
                return None
            self._append_event_db(db, row["id"], "turn.started", {"status": "running"})
            db.execute("COMMIT")
            result = dict(row)
            result["status"] = "running"
            result["started_at"] = now
            result["context"] = json.loads(result.pop("context_json"))
            return result

    def recover_interrupted(self) -> list[dict[str, Any]]:
        """Fail claimed turns at startup: provider side effects may be ambiguous."""
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            rows = db.execute(
                "SELECT t.id,c.provider_session_id FROM turns t JOIN conversations c "
                "ON c.id=t.conversation_id WHERE t.status='running'"
            ).fetchall()
            for row in rows:
                db.execute(
                    "UPDATE turns SET status='failed',completed_at=?,error_code='worker_interrupted',"
                    "error_message='The worker stopped during this turn; submit again to retry.' "
                    "WHERE id=?",
                    (utcnow(), row["id"]),
                )
                self._append_event_db(
                    db,
                    row["id"],
                    "turn.failed",
                    {
                        "code": "worker_interrupted",
                        "message": "The worker stopped during this turn; submit again to retry.",
                    },
                )
            db.execute("COMMIT")
        return [dict(row) for row in rows]

    def set_provider_session(self, conversation_id: str, session_id: str) -> None:
        with self._connect() as db:
            db.execute(
                "UPDATE conversations SET provider_session_id=?,updated_at=? WHERE id=?",
                (session_id, utcnow(), conversation_id),
            )

    def set_provider_turn(
        self, turn_id: str, provider_turn_id: str, event_id: str | None = None, event_type: str | None = None
    ) -> None:
        if not provider_turn_id or len(provider_turn_id) > 300:
            return
        with self._connect() as db:
            db.execute(
                "UPDATE turns SET provider_turn_id=?,provider_event_id=?,provider_event_type=? WHERE id=?",
                (provider_turn_id, (event_id or "")[:300] or None, (event_type or "")[:120] or None, turn_id),
            )

    def clear_provider_session(self, conversation_id: str) -> None:
        with self._connect() as db:
            db.execute(
                "UPDATE conversations SET provider_session_id=NULL,updated_at=? WHERE id=?",
                (utcnow(), conversation_id),
            )

    def list_interrupted_sessions(self) -> list[dict[str, Any]]:
        with self._connect() as db:
            rows = db.execute(
                "SELECT t.id,t.conversation_id,c.provider_session_id FROM turns t JOIN conversations c "
                "ON c.id=t.conversation_id WHERE t.status='running'"
            ).fetchall()
        return [dict(row) for row in rows]

    def get_provider_session(self, conversation_id: str) -> str | None:
        with self._connect() as db:
            row = db.execute(
                "SELECT provider_session_id FROM conversations WHERE id=?", (conversation_id,)
            ).fetchone()
            return row[0] if row else None

    def add_event(self, turn_id: str, event_type: str, payload: dict[str, Any]) -> int:
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            seq = self._append_event_db(db, turn_id, event_type, payload)
            db.execute("COMMIT")
        return seq

    @staticmethod
    def _append_event_db(
        db: sqlite3.Connection, turn_id: str, event_type: str, payload: dict[str, Any]
    ) -> int:
        current = db.execute(
            "SELECT COALESCE(MAX(seq),0) FROM turn_events WHERE turn_id=?", (turn_id,)
        ).fetchone()[0]
        seq = current + 1
        db.execute(
            "INSERT INTO turn_events(turn_id,seq,event_type,payload_json,created_at) VALUES(?,?,?,?,?)",
            (turn_id, seq, event_type, ChatStore._dump(payload), utcnow()),
        )
        return seq

    def list_events(self, owner_id: str, turn_id: str, after: int = 0) -> list[dict[str, Any]]:
        with self._connect() as db:
            authorized = db.execute(
                "SELECT 1 FROM turns WHERE id=? AND owner_id=?", (turn_id, owner_id)
            ).fetchone()
            if not authorized:
                raise NotFound("turn not found")
            rows = db.execute(
                "SELECT seq,event_type,payload_json,created_at FROM turn_events "
                "WHERE turn_id=? AND seq>? ORDER BY seq",
                (turn_id, after),
            ).fetchall()
        return [
            {
                "seq": r["seq"],
                "type": r["event_type"],
                "data": json.loads(r["payload_json"]),
                "created_at": r["created_at"],
            }
            for r in rows
        ]

    def events_and_status(
        self, owner_id: str, turn_id: str, after: int = 0
    ) -> tuple[list[dict[str, Any]], str]:
        """Read new events and the turn status in one connection for SSE polling."""
        with self._connect() as db:
            turn = db.execute(
                "SELECT status FROM turns WHERE id=? AND owner_id=?", (turn_id, owner_id)
            ).fetchone()
            if not turn:
                raise NotFound("turn not found")
            rows = db.execute(
                "SELECT seq,event_type,payload_json FROM turn_events WHERE turn_id=? AND seq>? ORDER BY seq",
                (turn_id, after),
            ).fetchall()
        events = [{"seq": r[0], "type": r[1], "data": json.loads(r[2])} for r in rows]
        return events, turn["status"]

    def get_turn(self, owner_id: str, turn_id: str) -> dict[str, Any]:
        with self._connect() as db:
            row = db.execute("SELECT * FROM turns WHERE id=? AND owner_id=?", (turn_id, owner_id)).fetchone()
            if row is None:
                raise NotFound("turn not found")
            return dict(row)

    def turn_messages(self, owner_id: str, conversation_id: str) -> list[dict[str, str]]:
        with self._connect() as db:
            return [
                dict(row)
                for row in db.execute(
                    "SELECT role,content FROM messages WHERE owner_id=? AND conversation_id=? "
                    "ORDER BY created_at,id",
                    (owner_id, conversation_id),
                ).fetchall()
            ]

    def find_deduplicated_turn(
        self, owner_id: str, conversation_id: str, client_message_id: str
    ) -> dict[str, Any] | None:
        with self._connect() as db:
            row = db.execute(
                "SELECT id,status,created_at,user_content,context_json FROM turns "
                "WHERE owner_id=? AND conversation_id=? AND client_message_id=?",
                (owner_id, conversation_id, client_message_id),
            ).fetchone()
        return dict(row) if row else None

    def active_count(self) -> int:
        with self._connect() as db:
            return int(
                db.execute("SELECT COUNT(*) FROM turns WHERE status IN ('pending','running')").fetchone()[0]
            )

    def request_cancel(self, owner_id: str, turn_id: str) -> str:
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT status FROM turns WHERE id=? AND owner_id=?", (turn_id, owner_id)
            ).fetchone()
            if row is None:
                raise NotFound("turn not found")
            status = row["status"]
            if status in {"pending", "running"}:
                db.execute(
                    "UPDATE turns SET status='cancelled',completed_at=?,error_code='cancelled',"
                    "usage_complete=CASE WHEN status='pending' THEN 1 ELSE usage_complete END,"
                    "reserved_tokens=CASE WHEN status='pending' THEN 0 ELSE reserved_tokens END,"
                    "reserved_cost_usd=CASE WHEN status='pending' THEN 0 ELSE reserved_cost_usd END "
                    "WHERE id=? AND status IN ('pending','running')",
                    (utcnow(), turn_id),
                )
                self._append_event_db(db, turn_id, "turn.cancelled", {"status": "cancelled"})
                status = "cancelled"
            db.execute("COMMIT")
        return status

    def is_cancelled(self, turn_id: str) -> bool:
        with self._connect() as db:
            row = db.execute("SELECT status FROM turns WHERE id=?", (turn_id,)).fetchone()
        return row is None or row[0] == "cancelled"

    def is_running(self, turn_id: str) -> bool:
        with self._connect() as db:
            row = db.execute("SELECT status FROM turns WHERE id=?", (turn_id,)).fetchone()
        return row is not None and row[0] == "running"
