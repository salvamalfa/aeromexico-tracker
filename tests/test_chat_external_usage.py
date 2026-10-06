from __future__ import annotations

import json
import math
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from src.conversational_analytics.storage import AdmissionDenied, ChatStore
from src.conversational_analytics.usage_import import (
    MAX_SQLITE_INTEGER,
    LedgerError,
    import_main,
    validate_ledger,
)


def known(identity: str = "org-workload-1", owner: str = "alice", day: str | None = None) -> dict:
    return {
        "accounting_id": identity,
        "owner_id": owner,
        "usage_date": day or datetime.now(UTC).date().isoformat(),
        "status": "known",
        "input_tokens": 100,
        "output_tokens": 20,
        "estimated_cost_usd": 0.5,
    }


def unknown(identity: str = "org-workload-pending", owner: str = "alice", day: str = "2026-10-03") -> dict:
    return {
        "accounting_id": identity,
        "owner_id": owner,
        "usage_date": day,
        "status": "unknown",
        "reserved_tokens": 150_000,
        "reserved_cost_usd": 0.38,
    }


def ledger(*entries: dict) -> dict:
    return {"version": 1, "entries": list(entries)}


def test_import_known_is_idempotent_and_not_double_counted(tmp_path: Path) -> None:
    store = ChatStore(tmp_path / "state.sqlite3")
    entry = known()
    store.external_usage_import([entry], apply=True)
    assert store.external_usage_import([entry], apply=True)["unchanged"] == 1
    assert store.usage("alice")["input_tokens"] == 100
    assert store.usage("alice")["output_tokens"] == 20
    with store._connect() as db:
        store._add_usage_db(db, "alice", 7, 3, 0.1)
    totals = store.usage("alice")
    assert (totals["input_tokens"], totals["output_tokens"], totals["estimated_cost_usd"]) == (107, 23, 0.6)


def test_unknown_blocks_all_new_admission_and_reconciles_once(tmp_path: Path) -> None:
    store = ChatStore(tmp_path / "state.sqlite3")
    store.external_usage_import([unknown()], apply=True)
    for owner in ("alice", "bob"):
        conversation = store.create_conversation(owner, "v1")
        with pytest.raises(AdmissionDenied, match="external usage"):
            store.submit_turn(owner, conversation["id"], "ask", f"m-{owner}", {})
    assert store.usage()["usage_incomplete_turns"] == 1
    reconciled = known(day="2026-10-03")
    reconciled["accounting_id"] = "org-workload-pending"
    store.external_usage_import([reconciled], apply=True)
    assert store.external_usage_import([reconciled], apply=True)["unchanged"] == 1
    assert store.usage()["usage_incomplete_turns"] == 0
    with store._connect() as db:
        assert store._usage_hold_totals_db(db) == (0, 0.0)
        assert store._external_usage_totals_db(db, "2026-10-03", "alice") == (100, 20, 0.5)


def test_worker_claim_pauses_pending_turn_on_late_unknown_import_then_claims_same_turn(
    tmp_path: Path,
) -> None:
    store = ChatStore(tmp_path / "state.sqlite3")
    conversation = store.create_conversation("alice", "v1")
    pending, _ = store.submit_turn("alice", conversation["id"], "ask", "queued-before-import", {})
    store.external_usage_import([unknown("late-org-hold")], apply=True)
    assert store.claim_turn() is None
    assert store.get_turn("alice", pending["id"])["status"] == "pending"
    assert [event["type"] for event in store.list_events("alice", pending["id"])] == ["turn.queued"]

    reconciled = known("late-org-hold", day="2026-10-03")
    store.external_usage_import([reconciled], apply=True)
    claimed = store.claim_turn()
    assert claimed and claimed["id"] == pending["id"] and claimed["status"] == "running"
    assert store.claim_turn() is None


def test_prior_day_unknown_hold_persists_through_conversation_retention(tmp_path: Path) -> None:
    store = ChatStore(tmp_path / "state.sqlite3")
    store.external_usage_import([unknown()], apply=True)
    old = store.create_conversation("alice", "v1")
    with store._connect() as db:
        old_date = (datetime.now(UTC) - timedelta(days=10)).isoformat()
        db.execute("UPDATE conversations SET updated_at=? WHERE id=?", (old_date, old["id"]))
    assert store.cleanup_expired(1) == 1
    with store._connect() as db:
        assert db.execute("SELECT COUNT(*) FROM external_usage WHERE status='unknown'").fetchone()[0] == 1
    next_day = store.create_conversation("bob", "v1")
    with pytest.raises(AdmissionDenied):
        store.submit_turn("bob", next_day["id"], "ask", "blocked", {})


@pytest.mark.parametrize(
    "mutate",
    [
        lambda x: x.update(input_tokens=True),
        lambda x: x.update(output_tokens=-1),
        lambda x: x.update(estimated_cost_usd=math.inf),
        lambda x: x.update(unexpected="secret"),
        lambda x: x.update(usage_date="2099-01-01"),
    ],
)
def test_known_schema_rejects_bool_bad_values_unknown_fields_and_future_dates(mutate) -> None:
    entry = known()
    mutate(entry)
    with pytest.raises(LedgerError):
        validate_ledger(ledger(entry))


def test_sqlite_integer_bounds_and_huge_cost_are_rejected_before_database_mutation(
    tmp_path: Path, capsys
) -> None:
    too_large = known("too-large")
    too_large["input_tokens"] = 1 << 63
    with pytest.raises(LedgerError):
        validate_ledger(ledger(too_large))
    too_large_cost = known("huge-cost")
    too_large_cost["estimated_cost_usd"] = 10**10000
    with pytest.raises(LedgerError):
        validate_ledger(ledger(too_large_cost))

    source = tmp_path / "oversized-integer.json"
    source.write_text(json.dumps(ledger(known("would-be-partial"), too_large)))
    fresh_state = tmp_path / "never-created" / "chat.sqlite3"
    assert import_main(["--file", str(source), "--state-path", str(fresh_state), "--apply"]) == 2
    assert not fresh_state.exists()
    assert "too-large" not in capsys.readouterr().err

    existing_state = tmp_path / "existing.sqlite3"
    store = ChatStore(existing_state)
    store.external_usage_import([known("already-present")], apply=True)
    assert import_main(["--file", str(source), "--state-path", str(existing_state), "--apply"]) == 2
    with store._connect() as db:
        ids = [
            row[0] for row in db.execute("SELECT accounting_id FROM external_usage ORDER BY accounting_id")
        ]
    assert ids == ["already-present"]


def test_batch_known_totals_reject_individually_valid_rows_before_db_creation(tmp_path: Path) -> None:
    source = tmp_path / "same-day-overflow.json"
    half_plus_one = MAX_SQLITE_INTEGER // 2 + 1
    first = known("owner-a-near-limit", "alice", "2026-10-03")
    second = known("owner-b-near-limit", "bob", "2026-10-03")
    first.update(input_tokens=half_plus_one, output_tokens=0, estimated_cost_usd=0.0)
    second.update(input_tokens=half_plus_one, output_tokens=0, estimated_cost_usd=0.0)
    assert first["input_tokens"] <= MAX_SQLITE_INTEGER
    assert second["input_tokens"] <= MAX_SQLITE_INTEGER
    source.write_text(json.dumps(ledger(first, second)))
    state = tmp_path / "untouched" / "chat.sqlite3"
    assert import_main(["--file", str(source), "--state-path", str(state), "--apply"]) == 2
    assert not state.exists()

    combined = [
        known("owner-c-combined", "carol", "2026-10-03"),
        known("owner-d-combined", "dave", "2026-10-03"),
    ]
    for item in combined:
        item.update(
            input_tokens=MAX_SQLITE_INTEGER // 2,
            output_tokens=MAX_SQLITE_INTEGER // 2,
            estimated_cost_usd=0.0,
        )
    with pytest.raises(LedgerError):
        validate_ledger(ledger(*combined))


def test_persisted_historical_usage_daily_and_external_totals_are_checked_atomically(
    tmp_path: Path,
) -> None:
    store = ChatStore(tmp_path / "state.sqlite3")
    day = "2026-10-03"
    prior = known("prior-near-limit", "alice", day)
    prior.update(input_tokens=MAX_SQLITE_INTEGER - 200, output_tokens=0, estimated_cost_usd=0.2)
    store.external_usage_import([prior], apply=True)
    with store._connect() as db:
        db.execute(
            "INSERT INTO usage_daily(usage_date,owner_id,input_tokens,output_tokens,"
            "estimated_cost_usd,turn_count) "
            "VALUES(?,?,?,?,?,1)",
            (day, "bob", 100, 0, 0.1),
        )
    first_new = known("would-fit-by-itself", "carol", day)
    first_new.update(input_tokens=50, output_tokens=0, estimated_cost_usd=0.1)
    second_new = known("would-overflow-historical-day", "dave", day)
    second_new.update(input_tokens=51, output_tokens=0, estimated_cost_usd=0.1)
    with pytest.raises(ValueError, match="safe numeric range"):
        store.external_usage_import([first_new, second_new], apply=True)
    with store._connect() as db:
        rows = db.execute("SELECT accounting_id FROM external_usage ORDER BY accounting_id").fetchall()
        assert [row[0] for row in rows] == ["prior-near-limit"]


def test_known_and_unknown_aggregate_costs_must_remain_finite(tmp_path: Path) -> None:
    same_day = [known("huge-a", "alice", "2026-10-03"), known("huge-b", "bob", "2026-10-03")]
    for item in same_day:
        item.update(input_tokens=0, output_tokens=0, estimated_cost_usd=1e308)
    with pytest.raises(LedgerError):
        validate_ledger(ledger(*same_day))

    store = ChatStore(tmp_path / "known-cost-state.sqlite3")
    day = "2026-10-03"
    with store._connect() as db:
        db.execute(
            "INSERT INTO usage_daily(usage_date,owner_id,input_tokens,output_tokens,"
            "estimated_cost_usd,turn_count) "
            "VALUES(?,?,?,?,?,1)",
            (day, "alice", 0, 0, 1e308),
        )
    incoming_cost = known("known-cost-overflow", "bob", day)
    incoming_cost.update(input_tokens=0, output_tokens=0, estimated_cost_usd=1e308)
    with pytest.raises(ValueError, match="safe numeric range"):
        store.external_usage_import([incoming_cost], apply=True)
    with store._connect() as db:
        assert db.execute("SELECT COUNT(*) FROM external_usage").fetchone()[0] == 0

    holds = [unknown("hold-a", "alice"), unknown("hold-b", "bob")]
    for item in holds:
        item["reserved_tokens"] = 150_000
        item["reserved_cost_usd"] = 1e308
    with pytest.raises(LedgerError):
        validate_ledger(ledger(*holds))


def test_unknown_holds_sum_across_turns_and_external_rows_before_commit(tmp_path: Path) -> None:
    store = ChatStore(tmp_path / "state.sqlite3")
    conversation = store.create_conversation("alice", "v1")
    store.submit_turn(
        "alice", conversation["id"], "ask", "reserved-local", {}, reserved_tokens=200, reserved_cost_usd=0.2
    )
    first = unknown("external-near-limit")
    first.update(reserved_tokens=MAX_SQLITE_INTEGER - 200, reserved_cost_usd=0.1)
    store.external_usage_import([first], apply=True)
    extra = unknown("external-overflow")
    with pytest.raises(ValueError, match="safe numeric range"):
        store.external_usage_import([extra], apply=True)
    with store._connect() as db:
        assert db.execute("SELECT COUNT(*) FROM external_usage").fetchone()[0] == 1

    cost_store = ChatStore(tmp_path / "cost-state.sqlite3")
    first_cost = unknown("hold-cost-a")
    first_cost["reserved_cost_usd"] = 1e308
    cost_store.external_usage_import([first_cost], apply=True)
    second_cost = unknown("hold-cost-b", "bob")
    second_cost["reserved_cost_usd"] = 1e308
    with pytest.raises(ValueError, match="safe numeric range"):
        cost_store.external_usage_import([second_cost], apply=True)


def test_unknown_requires_absent_or_null_confirmed_usage_and_minimum_hold() -> None:
    entry = unknown()
    entry["input_tokens"] = None
    assert validate_ledger(ledger(entry))[0]["status"] == "unknown"
    entry["input_tokens"] = 0
    with pytest.raises(LedgerError):
        validate_ledger(ledger(entry))
    entry = unknown()
    entry["reserved_tokens"] = True
    with pytest.raises(LedgerError):
        validate_ledger(ledger(entry))


def test_duplicate_ids_conflicts_and_batch_failure_are_atomic(tmp_path: Path) -> None:
    store = ChatStore(tmp_path / "state.sqlite3")
    with pytest.raises(LedgerError):
        validate_ledger(ledger(known("same"), known("same", "bob")))
    store.external_usage_import([known("fixed")], apply=True)
    fresh = known("fresh")
    conflicting = known("fixed")
    conflicting["input_tokens"] += 1
    with pytest.raises(ValueError, match="known ledger record conflict"):
        store.external_usage_import([fresh, conflicting], apply=True)
    with store._connect() as db:
        fresh_count = db.execute(
            "SELECT COUNT(*) FROM external_usage WHERE accounting_id='fresh'"
        ).fetchone()[0]
        assert fresh_count == 0


def test_owner_date_identity_is_immutable_and_known_cannot_roll_back(tmp_path: Path) -> None:
    store = ChatStore(tmp_path / "state.sqlite3")
    row = unknown("convert")
    store.external_usage_import([row], apply=True)
    updated = known("convert", day=row["usage_date"])
    store.external_usage_import([updated], apply=True)
    with pytest.raises(ValueError):
        store.external_usage_import([unknown("convert", day=row["usage_date"])], apply=True)
    moved = known("convert", owner="bob", day=row["usage_date"])
    with pytest.raises(ValueError, match="identity conflict"):
        store.external_usage_import([moved], apply=True)


def test_dry_run_does_not_create_database_and_cli_errors_are_generic(tmp_path: Path, capsys) -> None:
    source = tmp_path / "private.json"
    source.write_text(json.dumps(ledger(known())))
    state = tmp_path / "not-created" / "chat.sqlite3"
    assert import_main(["--file", str(source), "--state-path", str(state)]) == 0
    output = capsys.readouterr().out
    assert '"applied": false' in output and '"known_input_tokens": 100' in output
    assert not state.exists()
    bad = tmp_path / "bad.json"
    bad.write_text('{"version":1,"entries":[],"secret":"do-not-print"}')
    assert import_main(["--file", str(bad), "--state-path", str(state)]) == 2
    captured = capsys.readouterr()
    assert "do-not-print" not in captured.err and "secret" not in captured.err


def test_cli_apply_uses_explicit_state_path_and_private_new_database(tmp_path: Path, capsys) -> None:
    source = tmp_path / "ledger.json"
    source.write_text(json.dumps(ledger(known("cli-row"))))
    state = tmp_path / "private-leaf" / "chat.sqlite3"
    assert import_main(["--file", str(source), "--state-path", str(state), "--apply"]) == 0
    assert state.exists() and state.stat().st_mode & 0o777 == 0o600
    assert state.parent.stat().st_mode & 0o777 == 0o700
    assert '"applied": true' in capsys.readouterr().out
    with ChatStore(state)._connect() as db:
        imported = db.execute("SELECT COUNT(*) FROM external_usage WHERE accounting_id='cli-row'").fetchone()[
            0
        ]
        assert imported == 1


def test_usage_daily_external_budget_is_enforced_by_owner_and_global(tmp_path: Path) -> None:
    store = ChatStore(tmp_path / "state.sqlite3")
    row = known("today", "alice")
    store.external_usage_import([row], apply=True)
    alice = store.create_conversation("alice", "v1")
    with pytest.raises(AdmissionDenied, match="token budget"):
        store.submit_turn(
            "alice",
            alice["id"],
            "ask",
            "alice-over",
            {},
            reserved_tokens=1,
            user_token_budget=120,
            global_token_budget=1000,
        )
    bob = store.create_conversation("bob", "v1")
    with pytest.raises(AdmissionDenied, match="token budget"):
        store.submit_turn(
            "bob",
            bob["id"],
            "ask",
            "global-over",
            {},
            reserved_tokens=1,
            user_token_budget=1000,
            global_token_budget=120,
        )


def test_cli_refuses_unknown_rows_unless_admission_block_is_explicit(tmp_path: Path, capsys) -> None:
    source = tmp_path / "ledger.json"
    source.write_text(json.dumps(ledger(unknown("eval-unknown"))))
    state = tmp_path / "chat.sqlite3"

    assert import_main(["--file", str(source), "--state-path", str(state)]) == 0
    assert '"unknown_blocks_admission": true' in capsys.readouterr().out

    assert import_main(["--file", str(source), "--state-path", str(state), "--apply"]) == 2
    assert "pause all chat admission" in capsys.readouterr().err
    assert not state.exists()

    assert (
        import_main(["--file", str(source), "--state-path", str(state), "--apply", "--allow-admission-block"])
        == 0
    )
    with ChatStore(state)._connect() as db:
        assert db.execute("SELECT COUNT(*) FROM external_usage WHERE status='unknown'").fetchone()[0] == 1


def test_cli_relisting_a_stored_unknown_row_needs_no_admission_block_flag(tmp_path: Path) -> None:
    state = tmp_path / "chat.sqlite3"
    pending = unknown("eval-pending")
    ChatStore(state).external_usage_import([pending], apply=True)
    source = tmp_path / "ledger.json"
    # A cumulative ledger: the stored unknown row plus a newly confirmed one.
    source.write_text(json.dumps(ledger(pending, known("eval-done", day=pending["usage_date"]))))

    assert import_main(["--file", str(source), "--state-path", str(state), "--apply"]) == 0
