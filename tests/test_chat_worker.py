from __future__ import annotations

import threading
from pathlib import Path

from src.conversational_analytics.config import ChatConfig
from src.conversational_analytics.providers.base import ProviderResult
from src.conversational_analytics.storage import ChatStore
from src.conversational_analytics.worker import TurnWorker


class Snapshot:
    version = "snapshot-v1"
    semantic_version = "semantic-v1"

    def catalog(self):
        return {}


class Registry:
    def tool_specs(self):
        return [{"name": "query_metrics", "parameters": {}}]

    def invoke(self, name, arguments, context=None):
        assert name == "query_metrics"
        return {"rows": [{"display_value": 84.9}], "references": []}


class DeterministicProvider:
    def __init__(self):
        self.calls = 0
        self.cancelled = []

    def run_turn(self, **kwargs):
        self.calls += 1
        result = kwargs["call_tool"]("provider-turn-1", "call-1", "query_metrics", {"periods": ["2026Q2"]})
        kwargs["emit"]("message.delta", {"text": str(result["rows"][0]["display_value"])})
        return ProviderResult("84.9", input_tokens=4, output_tokens=2, usage_complete=True)

    def cancel(self, session_id):
        self.cancelled.append(session_id)

    def delete(self, session_id):
        pass


def test_worker_persists_tool_answer_events_and_usage(tmp_path: Path):
    store = ChatStore(tmp_path / "chat.sqlite3")
    conv = store.create_conversation("alice", "snapshot-v1", "semantic-v1")
    turn, _ = store.submit_turn(
        "alice", conv["id"], "ask", "client-1", {}, reserved_tokens=100, reserved_cost_usd=0.01
    )
    claim = store.claim_turn()
    provider = DeterministicProvider()
    worker = TurnWorker(store, ChatConfig(state_path=tmp_path / "chat.sqlite3"), provider, Snapshot())
    worker._registry = Registry()
    worker._execute_turn(claim)
    record = store.get_turn("alice", turn["id"])
    assert record["status"] == "completed"
    assert record["usage_complete"] == 1
    assert record["reserved_tokens"] == 0
    assert provider.calls == 1
    assert store.usage("alice")["input_tokens"] == 4
    event_types = [event["type"] for event in store.list_events("alice", turn["id"])]
    assert event_types[-2:] == ["message.completed", "turn.completed"]
    assert store.get_tool_result(turn["id"], "call-1")["rows"][0]["display_value"] == 84.9


class BlockingProvider(DeterministicProvider):
    def __init__(self):
        super().__init__()
        self.started = threading.Event()

    def run_turn(self, **kwargs):
        self.started.set()
        kwargs["cancel_event"].wait(2)
        raise InterruptedError("cancelled")


def test_worker_cancellation_is_terminal_without_completion(tmp_path: Path):
    store = ChatStore(tmp_path / "chat.sqlite3")
    conv = store.create_conversation("alice", "snapshot-v1", "semantic-v1")
    turn, _ = store.submit_turn("alice", conv["id"], "ask", "client-1", {})
    claim = store.claim_turn()
    provider = BlockingProvider()
    worker = TurnWorker(store, ChatConfig(state_path=tmp_path / "chat.sqlite3"), provider, Snapshot())
    worker._registry = Registry()
    thread = threading.Thread(target=worker._execute_turn, args=(claim,))
    thread.start()
    assert provider.started.wait(1)
    assert store.request_cancel("alice", turn["id"]) == "cancelled"
    worker.cancel(turn["id"])
    thread.join(2)
    assert not thread.is_alive()
    assert store.get_turn("alice", turn["id"])["status"] == "cancelled"
    assert "turn.completed" not in [e["type"] for e in store.list_events("alice", turn["id"])]


def test_worker_refuses_stale_data_or_semantic_snapshot(tmp_path: Path):
    store = ChatStore(tmp_path / "chat.sqlite3")
    conv = store.create_conversation("alice", "old-snapshot", "semantic-v1")
    turn, _ = store.submit_turn("alice", conv["id"], "ask", "client-1", {})
    claim = store.claim_turn()
    provider = DeterministicProvider()
    worker = TurnWorker(store, ChatConfig(state_path=tmp_path / "chat.sqlite3"), provider, Snapshot())
    worker._execute_turn(claim)
    assert store.get_turn("alice", turn["id"])["error_code"] == "snapshot_changed"
    assert provider.calls == 0


def test_worker_does_not_call_provider_for_cancelled_claim(tmp_path: Path):
    store = ChatStore(tmp_path / "chat.sqlite3")
    conv = store.create_conversation("alice", "snapshot-v1", "semantic-v1")
    turn, _ = store.submit_turn("alice", conv["id"], "ask", "client-1", {})
    claim = store.claim_turn()
    assert store.request_cancel("alice", turn["id"]) == "cancelled"
    provider = DeterministicProvider()
    worker = TurnWorker(store, ChatConfig(state_path=tmp_path / "chat.sqlite3"), provider, Snapshot())
    worker._execute_turn(claim)
    assert provider.calls == 0
