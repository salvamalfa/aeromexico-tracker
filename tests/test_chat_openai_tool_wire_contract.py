"""Offline regression for the Agents API's rejected function strict field."""

from __future__ import annotations

import copy
import json

import pytest

openai = pytest.importorskip("openai")
httpx = pytest.importorskip("httpx")

from openai.types.beta.agent_tool_param import AgentToolConfigParamFunction

from src.conversational_analytics.model_settings import agent_configuration
from src.conversational_analytics.providers._openai_runtime_helpers import (
    _strict_schema,
    validate_tool_specs,
)
from src.conversational_analytics.providers.openai import OpenAIProviderError
from src.conversational_analytics.tools.business_metrics import business_metric_tool_specs
from src.conversational_analytics.tools.evidence import evidence_tool_specs
from src.conversational_analytics.tools.registry import ROUTE_TOOL_SPECS, ToolRegistry


def _all_specs():
    return (
        ToolRegistry._make_specs()
        + copy.deepcopy(ROUTE_TOOL_SPECS)
        + business_metric_tool_specs()
        + evidence_tool_specs()
    )


def test_all_thirteen_tools_match_sdk_contract_on_actual_wire():
    raw = _all_specs()
    original = copy.deepcopy(raw)
    tools = validate_tool_specs(raw)
    captured = []

    def receive(request):
        captured.append(json.loads(request.content))
        return httpx.Response(
            200, headers={"content-type": "text/event-stream"}, content=b""
        )

    with openai.OpenAI(
        api_key="offline-test-placeholder",
        http_client=httpx.Client(transport=httpx.MockTransport(receive)),
    ) as client:
        stream = client.beta.agents.sessions.create(
            agent=agent_configuration("gpt-6.1-sol", "Offline contract", tools, "low", "medium"),
            environment={"type": "none"},
            input="Offline contract",
            stream=True,
        )
        stream.close()

    assert len(captured) == 1
    emitted = captured[0]["agent"]["tools"]
    assert len(emitted) == 13
    assert [tool["name"] for tool in emitted] == [tool["name"] for tool in raw]
    for source, tool in zip(raw, emitted, strict=True):
        assert "strict" not in tool
        assert set(tool) <= set(AgentToolConfigParamFunction.__annotations__)
        assert tool["description"] == source["description"]
        assert tool["parameters"] == _strict_schema(source["parameters"])
        assert tool["parameters"]["additionalProperties"] is False
        assert set(tool["parameters"]["required"]) == set(tool["parameters"]["properties"])
    assert raw == original


def test_wire_omission_preserves_explicit_strict_validation():
    specs = _all_specs()
    specs[0]["strict"] = True
    assert "strict" not in validate_tool_specs(specs)[0]
    specs[0]["strict"] = False
    with pytest.raises(OpenAIProviderError, match="validación estricta"):
        validate_tool_specs(specs)
