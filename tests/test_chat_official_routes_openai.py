"""The real SDK adapter transports the official tool through a fake session only."""

# ruff: noqa: E402
from __future__ import annotations

import json
import threading

import pytest

pytest.importorskip("openai")

from tests.test_chat_official_routes import PublicSnapshot, map_context, registry
from tests.test_chat_openai import (
    AgentSession,
    AgentSessionRequiresActionEvent,
    FakeClient,
    FakeSessions,
    FakeStream,
    RequiredActionSessionRequiredActionResourceFunctionCall,
    _completed,
    _provider,
    _session_created,
    _text_done,
    _turn_created,
)


@pytest.mark.parametrize("scope", ["national", "us", "international"])
def test_official_tool_roundtrips_real_adapter_with_fake_sdk_events(scope):
    snapshot = PublicSnapshot()
    tools = registry(snapshot)
    context = map_context(snapshot.document, scope)
    action = RequiredActionSessionRequiredActionResourceFunctionCall.model_validate(
        {
            "type": "function_call",
            "turn_id": "turn_provider",
            "call_id": "official-call",
            "name": "query_official_routes",
            "arguments": {
                "period": None,
                "scope": None,
                "region": None,
                "carrier_keys": None,
                "dataset_version": None,
                "route_key": None,
                "top_n": None,
            },
        }
    )
    session = AgentSession.model_construct(
        id="sess_fixture", required_actions=[action], status="requires_action"
    )
    requires_action = AgentSessionRequiresActionEvent.model_construct(
        type="agent.session.requires_action", event_id="official-action", session=session
    )
    fake = FakeSessions(
        create_stream=FakeStream(
            [
                _session_created(),
                _turn_created(),
                requires_action,
                _text_done(text="Vuelos regulares del periodo seleccionado."),
                _completed(),
            ]
        )
    )
    provider = _provider(FakeClient(fake))
    calls = []

    def invoke(turn, call, name, arguments):
        calls.append((turn, call, name))
        return tools.invoke(name, arguments, context)

    result = provider.run_turn(
        session_id=None,
        messages=[{"role": "user", "content": "¿Qué muestra el mapa?", "turn_id": "app-turn"}],
        context=context,
        tool_specs=tools.tool_specs(),
        call_tool=invoke,
        emit=lambda *_: None,
        persist_session=lambda *_: None,
        cancel_event=threading.Event(),
    )
    assert calls == [("turn_provider", "official-call", "query_official_routes")]
    envelope = json.loads(fake.created[0]["input"][0]["content"][0]["text"])
    assert envelope["dashboard_context"] == context
    wire_tool = next(
        tool for tool in fake.created[0]["agent"]["tools"] if tool["name"] == "query_official_routes"
    )
    assert wire_tool["parameters"]["additionalProperties"] is False
    assert "strict" not in wire_tool
    output = json.loads(fake.events.created[0]["events"][0]["output"])
    assert output["dataset_version"] == snapshot.version
    assert output["query"]["scope"] == scope
    assert output["observed_months"] == context["filters"]["map_months"]
    assert any("official-routes.json" in reference["url"] for reference in result.references)
    if scope == "us":
        assert any("requested_year=2026" in reference["url"] for reference in result.references)
    assert result.usage_complete
