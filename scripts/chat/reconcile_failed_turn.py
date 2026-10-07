#!/usr/bin/env python3
"""Privately restore one local provider_error turn from its exact completed SDK turn.

Default mode reads local metadata only. ``--apply`` performs read-only provider
GETs for the explicitly supplied existing IDs, then writes the canonical answer
and confirmed usage only to the private chat database.
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from pathlib import Path
from typing import Any
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--turn-id", required=True, help="existing local turn ID")
    parser.add_argument("--owner-id", required=True, help="existing local owner ID")
    parser.add_argument(
        "--apply", action="store_true", help="retrieve exact provider turn and write recovery"
    )
    parser.add_argument("--conversation-id", help="required for --apply")
    parser.add_argument("--provider-session-id", help="required for --apply")
    parser.add_argument("--provider-turn-id", help="required for --apply")
    parser.add_argument("--snapshot-version", help="required for --apply")
    parser.add_argument("--semantic-version", help="required for --apply")
    return parser


def _safe_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    eligible = (
        metadata["status"] == "failed"
        and metadata["error_code"] == "provider_error"
        and metadata["has_provider_turn_id"]
        and metadata["has_provider_session_id"]
        and metadata["has_snapshot_version"]
        and metadata["has_semantic_version"]
        and not metadata["has_later_turn"]
        and not metadata["has_assistant_message"]
        and not metadata["provider_deletion_queued"]
        and not metadata["has_cancel_or_timeout_event"]
    )
    return {
        "mode": "dry_run",
        "eligible_by_local_metadata": eligible,
        "status": metadata["status"],
        "error_code": metadata["error_code"],
        "usage_already_booked": metadata["usage_complete"],
        "has_existing_provider_ids": (
            metadata["has_provider_turn_id"] and metadata["has_provider_session_id"]
        ),
        "has_later_turn": metadata["has_later_turn"],
        "has_assistant_message": metadata["has_assistant_message"],
        "provider_deletion_queued": metadata["provider_deletion_queued"],
        "has_cancel_or_timeout_event": metadata["has_cancel_or_timeout_event"],
        "provider_calls": 0,
        "database_writes": 0,
    }


def _required_apply_args(args: argparse.Namespace) -> None:
    names = (
        "conversation_id",
        "provider_session_id",
        "provider_turn_id",
        "snapshot_version",
        "semantic_version",
    )
    if any(not getattr(args, name) for name in names):
        raise ValueError("--apply requires every explicit existing identity field")


def _validate_recovered_content(content: str, max_message_chars: int) -> None:
    """Match the live worker's expanded provider-output ceiling."""
    if len(content) > max_message_chars * 4:
        raise ValueError("recovered answer exceeds the configured provider-output limit")


def _state_path() -> Path:
    return Path(
        os.environ.get(
            "CHAT_STATE_PATH",
            str(Path.home() / ".local/state/airline-tracker/chat.sqlite3"),
        )
    )


def _read_local_metadata(db_path: Path, owner_id: str, turn_id: str) -> dict[str, Any]:
    """Read only the recovery fence from SQLite without migrations or WAL setup."""
    uri = f"file:{quote(db_path.resolve().as_posix(), safe='/')}?mode=ro"
    with sqlite3.connect(uri, uri=True, timeout=10) as db:
        db.row_factory = sqlite3.Row
        row = db.execute(
            "SELECT t.id,t.owner_id,t.conversation_id,t.status,t.error_code,t.usage_complete,"
            "t.provider_turn_id,c.snapshot_version,c.semantic_version,c.provider_session_id,"
            "t.created_at FROM turns t JOIN conversations c ON c.id=t.conversation_id "
            "WHERE t.id=? AND t.owner_id=?",
            (turn_id, owner_id),
        ).fetchone()
        if row is None:
            raise LookupError
        later = db.execute(
            "SELECT 1 FROM turns WHERE conversation_id=? AND id<>? AND created_at>=? LIMIT 1",
            (row["conversation_id"], turn_id, row["created_at"]),
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


def _read_tool_results(db_path: Path, turn_id: str) -> list[dict[str, Any]]:
    uri = f"file:{quote(db_path.resolve().as_posix(), safe='/')}?mode=ro"
    with sqlite3.connect(uri, uri=True, timeout=10) as db:
        rows = db.execute(
            "SELECT provider_turn_id,call_id,tool_name,args_json,result_json FROM tool_results "
            "WHERE turn_id=? ORDER BY created_at,call_id",
            (turn_id,),
        ).fetchall()
    return [
        {
            "provider_turn_id": row[0],
            "call_id": row[1],
            "tool_name": row[2],
            "arguments": json.loads(row[3]),
            "result": json.loads(row[4]),
        }
        for row in rows
    ]


def _recover_exact(
    provider: Any, session_id: str, turn_id: str
) -> tuple[str, int, int, list[dict[str, Any]]]:
    """GET one exact completed root turn and its items; never sends provider input."""
    from src.conversational_analytics.providers._openai_helpers import (
        parse_usage,
        to_dict,
    )

    turn = provider.client.beta.agents.sessions.turns.retrieve(
        turn_id, session_id=session_id, timeout=30
    )
    data = to_dict(turn)
    if (
        data.get("id") != turn_id
        or data.get("session_id") != session_id
        or data.get("subagent_id") is not None
        or data.get("status") != "completed"
    ):
        raise ValueError("provider identity or status mismatch")
    usage = data.get("usage")
    if not isinstance(usage, dict):
        usage = to_dict(usage)
    input_tokens, output_tokens, complete = parse_usage(usage)
    if not complete:
        raise ValueError("provider usage is incomplete")

    page = provider.client.beta.agents.sessions.items.list(session_id, limit=100, order="desc")
    items = [to_dict(item) for item in getattr(page, "data", [])]
    if getattr(page, "has_more", False):
        raise ValueError("provider item list is incomplete")
    target = [item for item in items if item.get("turn_id") == turn_id]
    if not target:
        raise ValueError("provider returned no items for the exact turn")

    output_parts: list[str] = []
    final_messages = 0
    calls: list[dict[str, Any]] = []
    for item in reversed(target):
        phase = item.get("phase")
        if (
            item.get("type") == "message"
            and item.get("role") == "assistant"
            and item.get("status") == "completed"
            and (phase == "final_answer" or (phase is None and item.get("status") == "completed"))
        ):
            final_messages += 1
            for raw_part in item.get("content", []):
                part = to_dict(raw_part)
                text = part.get("text")
                if part.get("type") in {"output_text", "text"} and isinstance(text, str):
                    output_parts.append(text)
        elif item.get("type") == "function_call":
            args = item.get("arguments")
            if isinstance(args, str):
                args = json.loads(args)
            if not isinstance(args, dict):
                raise ValueError("provider function call is malformed")
            calls.append(
                {
                    "call_id": item.get("call_id"),
                    "tool_name": item.get("name"),
                    "arguments": args,
                }
            )
    content = "".join(output_parts).strip()
    if not content or final_messages != 1:
        raise ValueError("provider completed turn has no final answer")
    # Reject duplicated call IDs or malformed references before matching local
    # persisted tool outputs. Calls themselves are never executed here.
    call_ids = [call.get("call_id") for call in calls]
    if any(not isinstance(call_id, str) or not call_id for call_id in call_ids):
        raise ValueError("provider function call identity is missing")
    if len(call_ids) != len(set(call_ids)):
        raise ValueError("provider function call IDs are duplicated")
    return content, input_tokens, output_tokens, calls


def run(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        metadata = _read_local_metadata(_state_path(), args.owner_id, args.turn_id)
        if not args.apply:
            print(json.dumps(_safe_metadata(metadata), separators=(",", ":")))
            return 0

        _required_apply_args(args)
        safe = _safe_metadata(metadata)
        if not safe["eligible_by_local_metadata"]:
            raise ValueError("local turn does not meet recovery eligibility")
        identity_matches = (
            metadata["conversation_id"] == args.conversation_id
            and metadata["provider_session_id"] == args.provider_session_id
            and metadata["provider_turn_id"] == args.provider_turn_id
            and metadata["snapshot_version"] == args.snapshot_version
            and metadata["semantic_version"] == args.semantic_version
        )
        if not identity_matches:
            raise ValueError("explicit identity does not match existing local metadata")
        from src.conversational_analytics.config import ChatConfig

        config = ChatConfig.from_env()
        if config.provider != "openai" or not config.openai_enabled:
            raise ValueError("OpenAI provider is not explicitly enabled")

        from src.conversational_analytics.providers._openai_helpers import (
            chart_from_results,
            references_from_results,
        )
        from src.conversational_analytics.providers.openai import OpenAIProvider
        from src.conversational_analytics.storage import ChatStore

        provider = OpenAIProvider(config)
        content, input_tokens, output_tokens, provider_calls = _recover_exact(
            provider, args.provider_session_id, args.provider_turn_id
        )
        _validate_recovered_content(content, config.max_message_chars)
        state_path = _state_path()
        stored_results = _read_tool_results(state_path, args.turn_id)
        by_call_id = {row["call_id"]: row for row in stored_results}
        if len(by_call_id) != len(stored_results):
            raise ValueError("local tool result identities are duplicated")
        if {call["call_id"] for call in provider_calls} != set(by_call_id):
            raise ValueError("provider and local tool call sets do not match")
        validated_outputs: list[dict[str, Any]] = []
        for call in provider_calls:
            stored = by_call_id[call["call_id"]]
            if (
                stored["tool_name"] != call["tool_name"]
                or stored["arguments"] != call["arguments"]
                or stored["provider_turn_id"] != args.provider_turn_id
            ):
                raise ValueError("provider call does not match its persisted tool result")
            validated_outputs.append(stored["result"])

        payload: dict[str, Any] = {"references": references_from_results(validated_outputs)}
        chart = chart_from_results(validated_outputs)
        if chart is not None:
            payload["chart"] = chart
        cost = config.usage_cost_usd(input_tokens, output_tokens)
        # Construct the mutable store only after every read-only eligibility
        # and provider check passes. The method rechecks the fence atomically.
        store = ChatStore(config.state_path)
        applied = store.reconcile_failed_provider_turn(
            turn_id=args.turn_id,
            owner_id=args.owner_id,
            conversation_id=args.conversation_id,
            snapshot_version=args.snapshot_version,
            semantic_version=args.semantic_version,
            provider_session_id=args.provider_session_id,
            provider_turn_id=args.provider_turn_id,
            content=content,
            payload=payload,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost=cost,
        )
        if not applied:
            raise ValueError("local turn changed or failed the transactional recovery fence")
        print(
            json.dumps(
                {
                    "mode": "applied",
                    "status": "completed",
                    "usage_complete": True,
                    "provider_calls": 2,
                    "database_write": True,
                    "answer_emitted": False,
                },
                separators=(",", ":"),
            )
        )
        return 0
    except LookupError:
        print("reconciliation unavailable: local target not found", file=sys.stderr)
    except Exception:
        # Avoid provider SDK exception text, answer content, IDs, or config data.
        print("reconciliation unavailable: eligibility or recovery check failed", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(run())
