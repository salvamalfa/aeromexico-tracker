"""Login sessions and failed-login throttling stored next to chat state."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta

from ._storage_common import utcnow

AUTH_SCHEMA = """
CREATE TABLE IF NOT EXISTS chat_sessions (
    token_sha256 TEXT PRIMARY KEY,
    owner_id TEXT NOT NULL,
    hash_fingerprint TEXT NOT NULL,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS chat_sessions_expiry_idx ON chat_sessions(expires_at);
CREATE TABLE IF NOT EXISTS login_failures (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    client TEXT NOT NULL,
    attempted_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS login_failures_client_idx ON login_failures(client, attempted_at);
"""


def _iso(moment: datetime) -> str:
    return moment.isoformat(timespec="milliseconds")


class AuthSessionMixin:
    @staticmethod
    def _initialize_auth(db: sqlite3.Connection) -> None:
        db.executescript(AUTH_SCHEMA)

    def create_session(self, token_sha256: str, owner_id: str, fingerprint: str, ttl_hours: int) -> str:
        expires_at = _iso(datetime.now(UTC) + timedelta(hours=ttl_hours))
        with self._connect() as db:
            db.execute(
                "INSERT INTO chat_sessions(token_sha256,owner_id,hash_fingerprint,created_at,expires_at) "
                "VALUES(?,?,?,?,?)",
                (token_sha256, owner_id, fingerprint, utcnow(), expires_at),
            )
        return expires_at

    def session_owner(self, token_sha256: str, valid_fingerprints: dict[str, str]) -> str | None:
        """Return the owner of a live session whose password hash is still configured."""
        with self._connect() as db:
            row = db.execute(
                "SELECT owner_id,hash_fingerprint FROM chat_sessions WHERE token_sha256=? AND expires_at>?",
                (token_sha256, utcnow()),
            ).fetchone()
        if row is None or valid_fingerprints.get(row["owner_id"]) != row["hash_fingerprint"]:
            return None
        return row["owner_id"]

    def revoke_session(self, token_sha256: str) -> None:
        with self._connect() as db:
            db.execute("DELETE FROM chat_sessions WHERE token_sha256=?", (token_sha256,))

    def record_login_failure(self, client: str) -> None:
        with self._connect() as db:
            db.execute("INSERT INTO login_failures(client,attempted_at) VALUES(?,?)", (client[:64], utcnow()))

    def login_retry_after(
        self,
        client: str,
        *,
        max_per_client: int,
        client_window_minutes: int,
        max_global: int,
        global_window_minutes: int,
    ) -> int:
        """Seconds until another attempt is allowed, or 0 when the client may try now."""
        now = datetime.now(UTC)
        client_since = _iso(now - timedelta(minutes=client_window_minutes))
        global_since = _iso(now - timedelta(minutes=global_window_minutes))
        with self._connect() as db:
            client_rows = db.execute(
                "SELECT attempted_at FROM login_failures WHERE client=? AND attempted_at>? "
                "ORDER BY attempted_at",
                (client[:64], client_since),
            ).fetchall()
            global_rows = db.execute(
                "SELECT attempted_at FROM login_failures WHERE attempted_at>? ORDER BY attempted_at",
                (global_since,),
            ).fetchall()
        waits = []
        if len(client_rows) >= max_per_client:
            oldest = datetime.fromisoformat(client_rows[-max_per_client][0])
            waits.append(oldest + timedelta(minutes=client_window_minutes) - now)
        if len(global_rows) >= max_global:
            oldest = datetime.fromisoformat(global_rows[-max_global][0])
            waits.append(oldest + timedelta(minutes=global_window_minutes) - now)
        if not waits:
            return 0
        return max(1, int(max(waits).total_seconds()) + 1)

    def cleanup_auth(self) -> None:
        cutoff = _iso(datetime.now(UTC) - timedelta(days=1))
        with self._connect() as db:
            db.execute("DELETE FROM chat_sessions WHERE expires_at<=?", (utcnow(),))
            db.execute("DELETE FROM login_failures WHERE attempted_at<?", (cutoff,))


__all__ = ["AuthSessionMixin"]
