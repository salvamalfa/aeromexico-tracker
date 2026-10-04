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

    def begin_login_attempt(
        self, client: str, *, max_per_client: int, window_minutes: int
    ) -> tuple[int, int | None]:
        """Atomically check the per-client limit and count this attempt as a failure.

        Returns ``(retry_after_seconds, None)`` when the client is blocked, else
        ``(0, attempt_id)``. The attempt is recorded before the password is
        verified, so concurrent requests cannot all pass the check; a
        successful login removes it with :meth:`forget_login_attempt`.
        """
        now = datetime.now(UTC)
        since = _iso(now - timedelta(minutes=window_minutes))
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            rows = db.execute(
                "SELECT attempted_at FROM login_failures WHERE client=? AND attempted_at>? "
                "ORDER BY attempted_at",
                (client[:64], since),
            ).fetchall()
            if len(rows) >= max_per_client:
                db.execute("COMMIT")
                oldest = datetime.fromisoformat(rows[-max_per_client][0])
                wait = oldest + timedelta(minutes=window_minutes) - now
                return max(1, int(wait.total_seconds()) + 1), None
            cur = db.execute(
                "INSERT INTO login_failures(client,attempted_at) VALUES(?,?)", (client[:64], _iso(now))
            )
            db.execute("COMMIT")
            return 0, cur.lastrowid

    def forget_login_attempt(self, attempt_id: int) -> None:
        with self._connect() as db:
            db.execute("DELETE FROM login_failures WHERE id=?", (attempt_id,))

    def recent_login_failures(self, window_minutes: int) -> int:
        since = _iso(datetime.now(UTC) - timedelta(minutes=window_minutes))
        with self._connect() as db:
            return int(
                db.execute("SELECT COUNT(*) FROM login_failures WHERE attempted_at>?", (since,)).fetchone()[0]
            )

    def cleanup_auth(self) -> None:
        cutoff = _iso(datetime.now(UTC) - timedelta(days=1))
        with self._connect() as db:
            db.execute("DELETE FROM chat_sessions WHERE expires_at<=?", (utcnow(),))
            db.execute("DELETE FROM login_failures WHERE attempted_at<?", (cutoff,))


__all__ = ["AuthSessionMixin"]
