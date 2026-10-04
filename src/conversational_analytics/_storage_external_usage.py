"""Durable token-only accounting imported from external workload ledgers."""

from __future__ import annotations

import math
import sqlite3
from typing import Any

MAX_SQLITE_INTEGER = (1 << 63) - 1


class ExternalUsageMixin:
    @staticmethod
    def _initialize_external_usage(db: sqlite3.Connection) -> None:
        db.executescript(
            """
            CREATE TABLE IF NOT EXISTS external_usage (
                accounting_id TEXT PRIMARY KEY,
                owner_id TEXT NOT NULL,
                usage_date TEXT NOT NULL,
                status TEXT NOT NULL CHECK(status IN ('known','unknown')),
                input_tokens INTEGER,
                output_tokens INTEGER,
                estimated_cost_usd REAL,
                reserved_tokens INTEGER NOT NULL DEFAULT 0,
                reserved_cost_usd REAL NOT NULL DEFAULT 0,
                CHECK ((status='known' AND input_tokens IS NOT NULL AND output_tokens IS NOT NULL
                        AND estimated_cost_usd IS NOT NULL AND reserved_tokens=0 AND reserved_cost_usd=0)
                    OR (status='unknown' AND input_tokens IS NULL AND output_tokens IS NULL
                        AND estimated_cost_usd IS NULL))
            );
            CREATE INDEX IF NOT EXISTS external_usage_day_owner_idx
                ON external_usage(usage_date,owner_id,status);
            """
        )

    def external_usage_import(self, entries: list[dict[str, Any]], *, apply: bool) -> dict[str, int]:
        """Validate conflicts and optionally import one already validated batch atomically."""
        stats = {"new_known": 0, "new_unknown": 0, "reconciled": 0, "unchanged": 0}
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            for entry in entries:
                old = db.execute(
                    "SELECT * FROM external_usage WHERE accounting_id=?", (entry["accounting_id"],)
                ).fetchone()
                if old is None:
                    stats["new_" + entry["status"]] += 1
                    continue
                if old["owner_id"] != entry["owner_id"] or old["usage_date"] != entry["usage_date"]:
                    raise ValueError("ledger identity conflict")
                if old["status"] == "known":
                    if entry["status"] != "known" or any(
                        old[key] != entry[key]
                        for key in ("input_tokens", "output_tokens", "estimated_cost_usd")
                    ):
                        raise ValueError("known ledger record conflict")
                    stats["unchanged"] += 1
                elif entry["status"] == "unknown":
                    if any(old[key] != entry[key] for key in ("reserved_tokens", "reserved_cost_usd")):
                        raise ValueError("unknown ledger record conflict")
                    stats["unchanged"] += 1
                else:
                    stats["reconciled"] += 1
            self._validate_external_usage_projection_db(db, entries)
            if apply:
                for entry in entries:
                    old = db.execute(
                        "SELECT status FROM external_usage WHERE accounting_id=?", (entry["accounting_id"],)
                    ).fetchone()
                    values = (
                        entry["owner_id"],
                        entry["usage_date"],
                        entry["status"],
                        entry.get("input_tokens"),
                        entry.get("output_tokens"),
                        entry.get("estimated_cost_usd"),
                        entry.get("reserved_tokens", 0),
                        entry.get("reserved_cost_usd", 0.0),
                        entry["accounting_id"],
                    )
                    if old is None:
                        db.execute(
                            "INSERT INTO external_usage(owner_id,usage_date,status,input_tokens,"
                            "output_tokens,"
                            "estimated_cost_usd,reserved_tokens,reserved_cost_usd,accounting_id) "
                            "VALUES(?,?,?,?,?,?,?,?,?)",
                            values,
                        )
                    elif old["status"] == "unknown" and entry["status"] == "known":
                        db.execute(
                            "UPDATE external_usage SET status=?,input_tokens=?,output_tokens=?,"
                            "estimated_cost_usd=?,reserved_tokens=0,reserved_cost_usd=0 "
                            "WHERE accounting_id=? AND status='unknown'",
                            (
                                entry["status"],
                                entry["input_tokens"],
                                entry["output_tokens"],
                                entry["estimated_cost_usd"],
                                entry["accounting_id"],
                            ),
                        )
            db.execute("COMMIT")
        return stats

    @staticmethod
    def _validate_external_usage_projection_db(db: sqlite3.Connection, entries: list[dict[str, Any]]) -> None:
        """Check post-import day totals and all-date holds using Python integers."""
        external = {
            row["accounting_id"]: dict(row) for row in db.execute("SELECT * FROM external_usage").fetchall()
        }
        for entry in entries:
            previous = external.get(entry["accounting_id"])
            if previous is None or (previous["status"] == "unknown" and entry["status"] == "known"):
                external[entry["accounting_id"]] = entry

        days: dict[str, list[int | float]] = {}

        def add_day(day: str, inp: int, out: int, cost: float) -> None:
            if not isinstance(inp, int) or not isinstance(out, int) or inp < 0 or out < 0:
                raise ValueError("invalid persisted usage totals")
            if not _finite_cost(cost):
                raise ValueError("invalid persisted usage cost")
            values = days.setdefault(day, [0, 0, 0.0])
            values[0] += inp
            values[1] += out
            values[2] += cost
            if (
                values[0] > MAX_SQLITE_INTEGER
                or values[1] > MAX_SQLITE_INTEGER
                or values[0] + values[1] > MAX_SQLITE_INTEGER
                or not _finite_cost(values[2])
            ):
                raise ValueError("aggregate daily usage exceeds safe numeric range")

        for row in db.execute(
            "SELECT usage_date,input_tokens,output_tokens,estimated_cost_usd FROM usage_daily"
        ).fetchall():
            add_day(row[0], row[1], row[2], row[3])
        for row in external.values():
            if row["status"] == "known":
                add_day(
                    row["usage_date"],
                    row["input_tokens"],
                    row["output_tokens"],
                    row["estimated_cost_usd"],
                )

        hold_tokens = 0
        hold_cost = 0.0

        def add_hold(tokens: int, cost: float) -> None:
            nonlocal hold_tokens, hold_cost
            if not isinstance(tokens, int) or tokens < 0 or not _finite_cost(cost):
                raise ValueError("invalid persisted usage hold")
            hold_tokens += tokens
            hold_cost += cost
            if hold_tokens > MAX_SQLITE_INTEGER or not _finite_cost(hold_cost):
                raise ValueError("aggregate usage holds exceed safe numeric range")

        for row in db.execute(
            "SELECT reserved_tokens,reserved_cost_usd FROM turns "
            "WHERE status IN ('pending','running') OR usage_complete=0"
        ).fetchall():
            add_hold(row[0], row[1])
        for row in db.execute(
            "SELECT reserved_tokens,reserved_cost_usd FROM usage_tombstones WHERE status='unknown'"
        ).fetchall():
            add_hold(row[0], row[1])
        for row in external.values():
            if row["status"] == "unknown":
                add_hold(row["reserved_tokens"], row["reserved_cost_usd"])

    @staticmethod
    def _external_usage_totals_db(
        db: sqlite3.Connection, usage_date: str, owner_id: str | None = None
    ) -> tuple[int, int, float]:
        where = "usage_date=? AND status='known'"
        args: tuple[Any, ...] = (usage_date,)
        if owner_id is not None:
            where += " AND owner_id=?"
            args += (owner_id,)
        row = db.execute(
            "SELECT COALESCE(SUM(input_tokens),0),COALESCE(SUM(output_tokens),0),"
            f"COALESCE(SUM(estimated_cost_usd),0) FROM external_usage WHERE {where}",
            args,
        ).fetchone()
        return int(row[0]), int(row[1]), float(row[2])

    @staticmethod
    def _external_unknown_count_db(db: sqlite3.Connection) -> int:
        return int(db.execute("SELECT COUNT(*) FROM external_usage WHERE status='unknown'").fetchone()[0])


def _finite_cost(value: Any) -> bool:
    if not isinstance(value, (int, float)) or isinstance(value, bool) or value < 0:
        return False
    try:
        return math.isfinite(value)
    except (OverflowError, TypeError, ValueError):
        return False
