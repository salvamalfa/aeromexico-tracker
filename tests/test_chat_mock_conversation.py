"""Offline API-to-worker conversation tests using the verified site snapshot."""

from __future__ import annotations

import json
import re
import uuid
from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")
from fastapi.testclient import TestClient

from src.conversational_analytics.config import ChatConfig
from src.conversational_analytics.data.snapshot import Snapshot
from src.conversational_analytics.providers.mock import MockProvider

ROOT = Path(__file__).resolve().parents[1]


class _RecordingMockProvider:
    def __init__(self, snapshot: Snapshot):
        self.delegate = MockProvider(snapshot)
        self.message_histories: list[list[dict[str, Any]]] = []

    def run_turn(self, **kwargs: Any):
        self.message_histories.append([dict(message) for message in kwargs["messages"]])
        return self.delegate.run_turn(**kwargs)

    def cancel(self, session_id: str) -> None:
        self.delegate.cancel(session_id)

    def delete(self, session_id: str) -> None:
        self.delegate.delete(session_id)


def _events(body: str) -> list[dict[str, Any]]:
    parsed = []
    for frame in re.split(r"\r?\n\r?\n", body):
        if not frame.strip() or frame.startswith(":"):
            continue
        fields = {}
        for line in frame.splitlines():
            if ":" in line:
                key, value = line.split(":", 1)
                fields[key] = value.lstrip()
        if "data" in fields:
            parsed.append({"type": fields.get("event", "message"), **json.loads(fields["data"])})
    return parsed


def _new_turn(client: TestClient, conversation_id: str, content: str, context: dict[str, Any]) -> str:
    response = client.post(
        f"/api/chat/conversations/{conversation_id}/messages",
        json={"content": content, "client_message_id": f"mock-e2e-{uuid.uuid4().hex}", "context": context},
    )
    assert response.status_code == 202, response.text
    return response.json()["turn_id"]


def _completed_events(client: TestClient, turn_id: str) -> list[dict[str, Any]]:
    response = client.get(f"/api/chat/turns/{turn_id}/events?after=0")
    assert response.status_code == 200
    events = _events(response.text)
    assert events[-1]["type"] == "turn.completed"
    return events


def _app(tmp_path: Path, snapshot: Snapshot, provider: _RecordingMockProvider):
    from src.conversational_analytics.api import create_app

    return create_app(
        config=ChatConfig(state_path=tmp_path / "mock-conversation.sqlite3"),
        snapshot=snapshot,
        provider=provider,
    )


def test_conversation_compare_has_stable_delta_sign_and_persists_history(tmp_path: Path) -> None:
    snapshot = Snapshot(ROOT / "site")
    provider = _RecordingMockProvider(snapshot)
    app = _app(tmp_path, snapshot, provider)
    context = {"tab": "economy", "period": "2026Q2", "entity": "AEROMEXICO"}
    questions = (
        "Compara el factor de ocupación de Aeroméxico entre 2026Q2 y 2026Q1.",
        "Compara el factor de ocupación de Aeroméxico entre 2026Q1 y 2026Q2.",
    )

    with TestClient(app, base_url="http://127.0.0.1", client=("127.0.0.1", 50000)) as client:
        conversation = client.post("/api/chat/conversations")
        assert conversation.status_code == 201
        conversation_id = conversation.json()["id"]
        comparisons = []

        for question in questions:
            turn_id = _new_turn(client, conversation_id, question, context)
            events = _completed_events(client, turn_id)
            tool_events = [event for event in events if event["type"] == "tool.completed"]
            assert len(tool_events) == 1
            assert tool_events[0]["name"] == "compare_metrics"
            comparison = tool_events[0]["result"]["comparison"]
            assert comparison["previous"]["period"] == "2026Q1"
            assert comparison["current"]["period"] == "2026Q2"
            expected_delta = comparison["current"]["value"] - comparison["previous"]["value"]
            assert comparison["absolute_delta"] == pytest.approx(expected_delta)
            assert comparison["percentage_point_delta"] == pytest.approx(expected_delta * 100)
            assert comparison["relative_change_percent"] == pytest.approx(
                expected_delta / abs(comparison["previous"]["value"]) * 100
            )
            assert expected_delta > 0
            comparisons.append(
                (
                    comparison["previous"]["value"],
                    comparison["current"]["value"],
                    comparison["absolute_delta"],
                    comparison["percentage_point_delta"],
                    comparison["relative_change_percent"],
                )
            )

        assert comparisons[0] == pytest.approx(comparisons[1])
        assert len(provider.message_histories) == 2
        second_history = provider.message_histories[1]
        assert [message["role"] for message in second_history].count("user") == 2
        assert [message["role"] for message in second_history].count("assistant") == 1
        assert any(message["content"] == questions[0] for message in second_history)
        conversation_state = client.get(f"/api/chat/conversations/{conversation_id}").json()
        assert [message["role"] for message in conversation_state["messages"]].count("assistant") == 2
        assert len(conversation_state["turns"]) == 2


def test_conversation_series_keeps_missing_values_null_and_uses_source_references(
    tmp_path: Path,
) -> None:
    snapshot = Snapshot(ROOT / "site")
    provider = _RecordingMockProvider(snapshot)
    app = _app(tmp_path, snapshot, provider)
    context = {
        "tab": "reading",
        "period": "2019M01",
        "entity": "AEROMEXICO",
        "filters": {"segment": "total"},
    }
    question = "Muestra la serie de pasajeros AFAC total de Aeroméxico entre 2019M01 y 2019M03."

    with TestClient(app, base_url="http://127.0.0.1", client=("127.0.0.1", 50000)) as client:
        conversation = client.post("/api/chat/conversations")
        assert conversation.status_code == 201
        conversation_id = conversation.json()["id"]
        turn_id = _new_turn(client, conversation_id, question, context)
        events = _completed_events(client, turn_id)

        tool_events = [event for event in events if event["type"] == "tool.completed"]
        assert len(tool_events) == 1
        assert tool_events[0]["name"] == "get_time_series"
        result = tool_events[0]["result"]
        rows = result["rows"]
        assert [row["period"] for row in rows] == ["2019M01", "2019M02", "2019M03"]
        assert all(row["availability"] == "missing" for row in rows)
        assert all(row["value"] is None and row["display_value"] is None for row in rows)
        assert result["chart"]["series"][0]["y"] == [None, None, None]
        assert result["references"]
        allowed_urls = {ref["url"] for row in rows for ref in row["source_references"]}
        assert set(ref["url"] for ref in result["references"]) <= allowed_urls
        assert all(url.startswith("https://") for url in allowed_urls)

        message_event = next(event for event in events if event["type"] == "message.completed")
        assert message_event["chart"]["series"][0]["y"] == [None, None, None]
        assert message_event["references"] == result["references"]
        assert message_event["content"].count("sin dato publicado") == 3
        assert "0 pasajeros" not in message_event["content"]
