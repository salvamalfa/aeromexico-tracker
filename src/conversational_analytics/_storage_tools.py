"""Durable idempotency records for provider function calls."""

from __future__ import annotations

import json
from typing import Any

from ._storage_common import Conflict, utcnow


class ToolResultMixin:
    def save_tool_result(
        self,
        turn_id: str,
        call_id: str,
        name: str,
        args: dict[str, Any],
        result: dict[str, Any],
        provider_turn_id: str = "",
    ) -> dict[str, Any]:
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT result_json FROM tool_results WHERE turn_id=? AND call_id=?", (turn_id, call_id)
            ).fetchone()
            if row:
                db.execute("COMMIT")
                return json.loads(row[0])
            encoded = self._dump(result)
            db.execute(
                "INSERT INTO tool_results(turn_id,provider_turn_id,call_id,tool_name,args_json,"
                "result_json,created_at) "
                "VALUES(?,?,?,?,?,?,?)",
                (turn_id, provider_turn_id, call_id, name, self._dump(args), encoded, utcnow()),
            )
            db.execute(
                "UPDATE tool_calls SET status='completed' WHERE turn_id=? AND call_id=?", (turn_id, call_id)
            )
            db.execute("COMMIT")
        return result

    def begin_tool_call(
        self, turn_id: str, call_id: str, name: str, provider_turn_id: str = ""
    ) -> tuple[bool, dict[str, Any] | None]:
        """Claim a tool call once; unresolved prior calls are never repeated."""
        if not call_id or len(call_id) > 300:
            raise ValueError("invalid call id")
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            existing = db.execute(
                "SELECT status FROM tool_calls WHERE turn_id=? AND call_id=?", (turn_id, call_id)
            ).fetchone()
            if existing:
                result = db.execute(
                    "SELECT result_json FROM tool_results WHERE turn_id=? AND call_id=?", (turn_id, call_id)
                ).fetchone()
                db.execute("COMMIT")
                if result:
                    return False, json.loads(result[0])
                raise Conflict("tool call outcome is ambiguous and will not be replayed")
            db.execute(
                "INSERT INTO tool_calls(turn_id,provider_turn_id,call_id,tool_name,status,created_at) "
                "VALUES(?,?,?,?,'running',?)",
                (turn_id, provider_turn_id, call_id, name, utcnow()),
            )
            db.execute("COMMIT")
        return True, None

    def get_tool_result(
        self,
        turn_id: str,
        call_id: str,
        name: str | None = None,
        args: dict[str, Any] | None = None,
        provider_turn_id: str | None = None,
    ) -> dict[str, Any] | None:
        with self._connect() as db:
            row = db.execute(
                "SELECT result_json,tool_name,args_json,provider_turn_id FROM tool_results "
                "WHERE turn_id=? AND call_id=?",
                (turn_id, call_id),
            ).fetchone()
        if row is None:
            return None
        if name is not None and row["tool_name"] != name:
            raise Conflict("call_id was reused for a different tool")
        if args is not None and json.loads(row["args_json"]) != args:
            raise Conflict("call_id was reused with different tool arguments")
        if provider_turn_id is not None and row["provider_turn_id"] != provider_turn_id:
            raise Conflict("call_id was reused for a different provider turn")
        return json.loads(row["result_json"])
