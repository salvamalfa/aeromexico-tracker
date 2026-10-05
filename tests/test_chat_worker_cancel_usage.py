from __future__ import annotations

import threading

from test_chat_worker_limits import Registry, _claimed_turn, _worker

from src.conversational_analytics.storage import ChatStore


def test_cancel_racing_with_confirmed_usage_books_once_and_keeps_answer_suppressed(tmp_path):
    class Provider:
        supports_input_authorization = True

        def __init__(self):
            self.started = threading.Event()
            self.interruptions = 0

        def run_turn(self, **kwargs):
            kwargs["persist_session"]("provider-session")
            self.started.set()
            assert kwargs["cancel_event"].wait(timeout=1)
            interrupted = InterruptedError("turn cancelled")
            interrupted.usage = (31, 19)
            self.interruptions += 1
            raise interrupted

        def cancel(self, _session_id):
            return None

    db = tmp_path / "cancel-usage.sqlite3"
    store = ChatStore(db)
    _, turn, claim = _claimed_turn(store, reserved_tokens=150_000)
    provider = Provider()
    worker = _worker(store, db, provider, max_seconds=2)
    worker._registry = Registry({})
    record_usage = store.record_terminal_usage
    recorded = []

    def counted_record(turn_id, input_tokens, output_tokens, cost):
        recorded.append((turn_id, input_tokens, output_tokens, cost))
        return record_usage(turn_id, input_tokens, output_tokens, cost)

    store.record_terminal_usage = counted_record
    thread = threading.Thread(target=worker._execute_turn, args=(claim,))
    thread.start()
    assert provider.started.wait(timeout=1)
    assert store.request_cancel("alice", turn["id"]) == "cancelled"
    worker.cancel(turn["id"])
    thread.join(timeout=1)

    assert not thread.is_alive()
    assert provider.interruptions == 1
    assert len(recorded) == 1
    usage = store.usage("alice")
    assert (usage["input_tokens"], usage["output_tokens"], usage["turn_count"]) == (31, 19, 1)
    assert usage["usage_incomplete_turns"] == 0
    with store._connect() as connection:
        assert store._usage_hold_totals_db(connection) == (0, 0.0)
    events = [event["type"] for event in store.list_events("alice", turn["id"])]
    assert "message.completed" not in events
    assert events.count("turn.cancelled") == 1
