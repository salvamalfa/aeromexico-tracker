"""Durable, owner-scoped SQLite state for chat conversations and turns."""

from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ._storage_common import AdmissionDenied, ChatError, Conflict, NotFound, utcnow
from ._storage_tools import ToolResultMixin
from ._storage_usage import UsageRetentionMixin

__all__ = ["AdmissionDenied", "ChatError", "ChatStore", "Conflict", "NotFound", "utcnow"]


class ChatStore(ToolResultMixin, UsageRetentionMixin):
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
            conv_columns = {row[1] for row in db.execute("PRAGMA table_info(conversations)")}
            if "semantic_version" not in conv_columns:
                db.execute("ALTER TABLE conversations ADD COLUMN semantic_version TEXT NOT NULL DEFAULT ''")
            deletion_columns = {row[1] for row in db.execute("PRAGMA table_info(provider_deletions)")}
            if "next_attempt_at" not in deletion_columns:
                db.execute(
                    "ALTER TABLE provider_deletions ADD COLUMN next_attempt_at TEXT NOT NULL DEFAULT ''"
                )
            for table in ("tool_results", "tool_calls"):
                columns = {row[1] for row in db.execute(f"PRAGMA table_info({table})")}
                if "provider_turn_id" not in columns:
                    db.execute(f"ALTER TABLE {table} ADD COLUMN provider_turn_id TEXT NOT NULL DEFAULT ''")

    @staticmethod
    def _dump(obj: Any) -> str:
        return json.dumps(obj, ensure_ascii=False, separators=(",", ":"), allow_nan=False)

    def create_conversation(
        self, owner_id: str, snapshot_version: str, semantic_version: str = ""
    ) -> dict[str, Any]:
        now, conv_id = utcnow(), str(uuid.uuid4())
        with self._connect() as db:
            db.execute(
                "INSERT INTO conversations(id,owner_id,snapshot_version,semantic_version,"
                "created_at,updated_at) "
                "VALUES(?,?,?,?,?,?)",
                (conv_id, owner_id, snapshot_version, semantic_version, now, now),
            )
        return {
            "id": conv_id,
            "snapshot_version": snapshot_version,
            "semantic_version": semantic_version,
            "created_at": now,
        }

    def get_conversation(self, owner_id: str, conversation_id: str) -> dict[str, Any]:
        with self._connect() as db:
            conv = db.execute(
                "SELECT id,snapshot_version,semantic_version,created_at FROM conversations "
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
                "estimated_input_tokens,estimated_output_tokens,estimated_cost_usd FROM turns "
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
            cur = db.execute(
                "DELETE FROM conversations WHERE id=? AND owner_id=?", (conversation_id, owner_id)
            )
            if cur.rowcount == 0:
                raise NotFound("conversation not found")

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
            user_holds = db.execute(
                "SELECT COALESCE(SUM(reserved_tokens),0),COALESCE(SUM(reserved_cost_usd),0) "
                "FROM turns WHERE owner_id=? AND reserved_usage_date=? "
                "AND (status IN ('pending','running') OR usage_complete=0)",
                (owner_id, usage_day),
            ).fetchone()
            global_holds = db.execute(
                "SELECT COALESCE(SUM(reserved_tokens),0),COALESCE(SUM(reserved_cost_usd),0) "
                "FROM turns WHERE reserved_usage_date=? "
                "AND (status IN ('pending','running') OR usage_complete=0)",
                (usage_day,),
            ).fetchone()
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
                    "context_json,created_at,reserved_tokens,reserved_cost_usd,reserved_usage_date) "
                    "VALUES(?,?,?,?, 'pending',?,?,?,?,?,?)",
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

    def claim_turn(self) -> dict[str, Any] | None:
        """Atomically claim one pending turn. Running turns are never replayed."""
        now = utcnow()
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
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
                "UPDATE turns SET provider_turn_id=?,provider_event_id=?,provider_event_type=? "
                "WHERE id=? AND status='running'",
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
