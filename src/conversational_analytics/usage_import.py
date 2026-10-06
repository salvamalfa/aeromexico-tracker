"""Validate and import a private, token-only external usage ledger."""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import sys
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from ._storage_external_usage import MAX_SQLITE_INTEGER
from .storage import ChatStore

MAX_LEDGER_BYTES = 2_000_000
ROOT_KEYS = {"version", "entries"}
COMMON_KEYS = {"accounting_id", "owner_id", "usage_date", "status"}
KNOWN_KEYS = COMMON_KEYS | {"input_tokens", "output_tokens", "estimated_cost_usd"}
UNKNOWN_KEYS = COMMON_KEYS | {
    "reserved_tokens",
    "reserved_cost_usd",
    "input_tokens",
    "output_tokens",
    "estimated_cost_usd",
}


class LedgerError(ValueError):
    """Safe validation error with no source values in its message."""


def _object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise LedgerError("duplicate JSON key")
        result[key] = value
    return result


def _strict_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and 0 <= value <= MAX_SQLITE_INTEGER


def _finite_nonnegative(value: Any) -> bool:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return False
    try:
        return math.isfinite(value) and value >= 0
    except (OverflowError, TypeError, ValueError):
        return False


def validate_ledger(raw: Any, *, today: date | None = None) -> list[dict[str, Any]]:
    if (
        not isinstance(raw, dict)
        or set(raw) != ROOT_KEYS
        or type(raw.get("version")) is not int
        or raw["version"] != 1
    ):
        raise LedgerError("invalid ledger envelope")
    entries = raw.get("entries")
    if not isinstance(entries, list) or not entries:
        raise LedgerError("ledger entries must be a nonempty list")
    today = today or datetime.now(UTC).date()
    validated: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in entries:
        if not isinstance(item, dict):
            raise LedgerError("invalid ledger entry")
        status = item.get("status")
        allowed = KNOWN_KEYS if status == "known" else UNKNOWN_KEYS if status == "unknown" else set()
        if not allowed or not set(item) <= allowed or not COMMON_KEYS <= set(item):
            raise LedgerError("invalid ledger entry fields")
        for key in ("accounting_id", "owner_id"):
            value = item.get(key)
            if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_.:-]{1,200}", value):
                raise LedgerError("invalid ledger identity")
        accounting_id = item["accounting_id"]
        if accounting_id in seen:
            raise LedgerError("duplicate accounting id in batch")
        seen.add(accounting_id)
        try:
            day = date.fromisoformat(item["usage_date"])
        except (TypeError, ValueError):
            raise LedgerError("invalid usage date") from None
        if not isinstance(item["usage_date"], str) or day.isoformat() != item["usage_date"] or day > today:
            raise LedgerError("invalid usage date")
        entry = {k: item[k] for k in COMMON_KEYS}
        if status == "known":
            if set(item) != KNOWN_KEYS:
                raise LedgerError("known usage fields are required")
            if not _strict_int(item["input_tokens"]) or not _strict_int(item["output_tokens"]):
                raise LedgerError("invalid token count")
            if item["input_tokens"] + item["output_tokens"] > MAX_SQLITE_INTEGER:
                raise LedgerError("invalid token count")
            if not _finite_nonnegative(item["estimated_cost_usd"]):
                raise LedgerError("invalid estimated cost")
            entry.update(
                {
                    "input_tokens": item["input_tokens"],
                    "output_tokens": item["output_tokens"],
                    "estimated_cost_usd": float(item["estimated_cost_usd"]),
                }
            )
        else:
            for key in ("input_tokens", "output_tokens", "estimated_cost_usd"):
                if key in item and item[key] is not None:
                    raise LedgerError("unknown usage cannot include confirmed usage")
            tokens = item.get("reserved_tokens")
            cost = item.get("reserved_cost_usd")
            if not _strict_int(tokens) or tokens < 150_000 or not _finite_nonnegative(cost):
                raise LedgerError("invalid unknown usage reservation")
            entry.update({"reserved_tokens": tokens, "reserved_cost_usd": float(cost)})
        validated.append(entry)
    _validate_batch_aggregates(validated)
    return validated


def _validate_batch_aggregates(entries: list[dict[str, Any]]) -> None:
    days: dict[str, list[int | float]] = {}
    hold_tokens = 0
    hold_cost = 0.0
    for entry in entries:
        if entry["status"] == "known":
            values = days.setdefault(entry["usage_date"], [0, 0, 0.0])
            values[0] += entry["input_tokens"]
            values[1] += entry["output_tokens"]
            values[2] += entry["estimated_cost_usd"]
            if (
                values[0] > MAX_SQLITE_INTEGER
                or values[1] > MAX_SQLITE_INTEGER
                or values[0] + values[1] > MAX_SQLITE_INTEGER
                or not _finite_nonnegative(values[2])
            ):
                raise LedgerError("aggregate daily usage exceeds safe numeric range")
        else:
            hold_tokens += entry["reserved_tokens"]
            hold_cost += entry["reserved_cost_usd"]
            if hold_tokens > MAX_SQLITE_INTEGER or not _finite_nonnegative(hold_cost):
                raise LedgerError("aggregate usage holds exceed safe numeric range")


def read_ledger(path: str | Path) -> list[dict[str, Any]]:
    source = Path(path)
    try:
        if source.stat().st_size > MAX_LEDGER_BYTES:
            raise LedgerError("ledger file is too large")
        raw = json.loads(source.read_text(encoding="utf-8"), object_pairs_hook=_object)
    except LedgerError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError):
        raise LedgerError("ledger file could not be read") from None
    return validate_ledger(raw)


def safe_summary(
    entries: list[dict[str, Any]], stats: dict[str, int], *, applied: bool
) -> dict[str, int | bool]:
    known = [entry for entry in entries if entry["status"] == "known"]
    return {
        "applied": applied,
        "entries": len(entries),
        **stats,
        "known_input_tokens": sum(entry["input_tokens"] for entry in known),
        "known_output_tokens": sum(entry["output_tokens"] for entry in known),
        # Any unknown row pauses every chat admission until it is reconciled.
        "unknown_blocks_admission": len(known) < len(entries),
    }


def import_main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="python -m src.conversational_analytics import-usage")
    parser.add_argument("--file", required=True, help="private version 1 token-only JSON ledger")
    parser.add_argument("--state-path", required=True, help="explicit chat SQLite path")
    parser.add_argument("--apply", action="store_true", help="write the validated batch; default is dry-run")
    parser.add_argument(
        "--allow-admission-block",
        action="store_true",
        help="required to apply unknown rows: they pause all chat admission until reconciled",
    )
    args = parser.parse_args(argv)
    try:
        entries = read_ledger(args.file)
        if args.apply and not args.allow_admission_block:
            # Only unknown rows new to this database add a block; re-listing an
            # unknown row that is already stored (or reconciling one) does not.
            state_path = Path(args.state_path)
            if state_path.exists():
                new_unknown = ChatStore(state_path).external_usage_import(entries, apply=False)["new_unknown"]
            else:
                new_unknown = sum(entry["status"] == "unknown" for entry in entries)
            if new_unknown:
                print(
                    "Usage import refused: new unknown rows would pause all chat admission; "
                    "reconcile them first or pass --allow-admission-block.",
                    file=sys.stderr,
                )
                return 2
        if args.apply:
            state_path = Path(args.state_path)
            old_umask = os.umask(0o077)
            try:
                if not state_path.exists():
                    state_path.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
                    store = ChatStore(state_path)
                    try:
                        state_path.chmod(0o600)
                    except OSError:
                        pass
                else:
                    store = ChatStore(state_path)
                stats = store.external_usage_import(entries, apply=True)
            finally:
                os.umask(old_umask)
        else:
            known = sum(entry["status"] == "known" for entry in entries)
            stats = {
                "would_import_known": known,
                "would_import_unknown": len(entries) - known,
                "database_checked": 0,
            }
    except (LedgerError, ValueError):
        print("Usage import rejected; check the private ledger format and conflicts.", file=sys.stderr)
        return 2
    except Exception:
        print("Usage import failed; no source details were recorded.", file=sys.stderr)
        return 2
    print(json.dumps(safe_summary(entries, stats, applied=args.apply), sort_keys=True))
    return 0
