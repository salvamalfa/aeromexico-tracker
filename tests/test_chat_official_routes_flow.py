"""API → worker → deterministic official tool → persisted presentation, all offline."""

# ruff: noqa: E402
from __future__ import annotations

import json
import re

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")
from fastapi.testclient import TestClient

from src.conversational_analytics.api import create_app
from src.conversational_analytics.config import ChatConfig
from src.conversational_analytics.providers import _openai_prompt
from src.conversational_analytics.providers._openai_references import references_from_results
from src.conversational_analytics.providers.base import ProviderResult
from tests.test_chat_official_routes import PublicSnapshot, map_context


class AdversarialProvider:
    def __init__(self):
        self.outputs = []
        self.contexts = []

    def run_turn(self, **kwargs):
        self.contexts.append(kwargs["context"])
        names = {spec["name"] for spec in kwargs["tool_specs"]}
        assert "query_official_routes" in names
        call = kwargs["call_tool"]
        legacy = call("provider-turn", "wrong-source", "query_routes", {})
        assert legacy["error"]["code"] == "tool_rejected"
        assert "query_official_routes" in legacy["error"]["message"]
        self.outputs.append(legacy)
        if kwargs["context"]["filters"]["map_scope"] == "national":
            rejected = call(
                "provider-turn", "bad-cell", "query_official_routes", {"carrier_keys": ["AEROMEXICO"]}
            )
            assert rejected["error"]["code"] == "tool_rejected"
            self.outputs.append(rejected)
        result = call("provider-turn", "exact-map", "query_official_routes", {})
        self.outputs.append(result)
        # Same provider call is replayed from local storage without a second calculation.
        assert call("provider-turn", "exact-map", "query_official_routes", {}) == result
        return ProviderResult(
            content="Vuelos regulares del trimestre seleccionado. {{"
            + result["display"]["display_id"]
            + "}}",
            references=references_from_results([result]),
            usage_complete=True,
        )

    def cancel(self, _session_id):
        return None

    def delete(self, _session_id):
        return None


def config(tmp_path, monkeypatch):
    monkeypatch.setattr(_openai_prompt, "effective_prompt_sha256", lambda: _openai_prompt.R2_PROMPT_SHA256)
    monkeypatch.setattr(_openai_prompt, "effective_prompt_version", lambda: _openai_prompt.R2_PROMPT_VERSION)
    return ChatConfig(
        state_path=tmp_path / "official.sqlite3",
        prompt_version="r2-proposed",
        enable_official_route_tools=True,
        enable_route_tools=True,
        official_route_dataset_sha256=PublicSnapshot().version,
    )


@pytest.mark.parametrize("scope", ["national", "us", "international"])
@pytest.mark.parametrize("attached", [True, False])
def test_official_card_flows_through_api_worker_storage_and_sources_without_model(
    scope, attached, tmp_path, monkeypatch
):
    snapshot = PublicSnapshot()
    provider = AdversarialProvider()
    context = map_context(snapshot.document, scope)
    if not attached:
        context.pop("card_id")
    app = create_app(config=config(tmp_path, monkeypatch), snapshot=snapshot, provider=provider)
    with TestClient(app, base_url="http://127.0.0.1", client=("127.0.0.1", 50000)) as client:
        health = client.get("/api/chat/health").json()
        assert health["official_route_dataset_version"] == snapshot.version
        assert "official_route_queries" in health["enabled_capabilities"]
        conversation = client.post("/api/chat/conversations").json()["id"]
        admitted = client.post(
            f"/api/chat/conversations/{conversation}/messages",
            json={
                "content": "¿Qué muestra esta tarjeta?",
                "context": context,
                "client_message_id": "official-1",
            },
        )
        assert admitted.status_code == 202, admitted.text
        turn_id = admitted.json()["turn_id"]
        response = client.get(f"/api/chat/turns/{turn_id}/events?after=0")
        assert response.status_code == 200
        event_types = re.findall(r"event: (.+)", response.text)
        assert event_types[-1] == "turn.completed", response.text
        persisted = client.get(f"/api/chat/conversations/{conversation}").json()
        assert provider.contexts == [context]
        assert persisted["turns"][-1]["status"] == "completed"
        message = next(message for message in persisted["messages"] if message["role"] == "assistant")
        sources = message["references"] + [
            source for display in message["displays"] for source in display["sources"]
        ]
        assert any("official-routes.json" in ref["url"] for ref in sources)
        if scope == "us":
            assert any("requested_year=2026" in ref["url"] for ref in sources)
        result = provider.outputs[-1]
        assert result["query"]["scope"] == scope
        assert result["dataset_version"] == snapshot.version
        assert len(json.dumps(result, ensure_ascii=False).encode()) < 16_000
        assert "display" in result
        replay = client.get(f"/api/chat/turns/{turn_id}/events?after=0")
        assert replay.text == response.text
        assert len(provider.contexts) == 1


def test_malformed_official_context_fails_admission_before_provider(tmp_path, monkeypatch):
    snapshot = PublicSnapshot()
    provider = AdversarialProvider()
    app = create_app(config=config(tmp_path, monkeypatch), snapshot=snapshot, provider=provider)
    with TestClient(app, base_url="http://127.0.0.1", client=("127.0.0.1", 50000)) as client:
        conversation = client.post("/api/chat/conversations").json()["id"]
        response = client.post(
            f"/api/chat/conversations/{conversation}/messages",
            json={
                "content": "Reparte AFAC por aerolínea",
                "client_message_id": "bad-cell",
                "context": map_context(snapshot.document, map_carriers=["AEROMEXICO"]),
            },
        )
        assert response.status_code == 422
        assert provider.contexts == []


@pytest.mark.parametrize("filters", [{"map_dataset_version": "0" * 64}, {"map_months": ["2026M07"]}])
def test_stale_map_rejected_before_any_provider_input(filters, tmp_path, monkeypatch):
    snapshot = PublicSnapshot()
    provider = AdversarialProvider()
    app = create_app(config=config(tmp_path, monkeypatch), snapshot=snapshot, provider=provider)
    with TestClient(app, base_url="http://127.0.0.1", client=("127.0.0.1", 50000)) as client:
        conversation = client.post("/api/chat/conversations").json()["id"]
        response = client.post(
            f"/api/chat/conversations/{conversation}/messages",
            json={
                "content": "Este mapa",
                "client_message_id": "stale-map",
                "context": map_context(snapshot.document, **filters),
            },
        )
        assert response.status_code == 422
        assert provider.contexts == []


def test_disabling_feature_rejects_official_chip_without_exposing_legacy_data(tmp_path):
    snapshot = PublicSnapshot()
    provider = AdversarialProvider()
    app = create_app(
        config=ChatConfig(state_path=tmp_path / "disabled.sqlite3"), snapshot=snapshot, provider=provider
    )
    with TestClient(app, base_url="http://127.0.0.1", client=("127.0.0.1", 50000)) as client:
        health = client.get("/api/chat/health").json()
        assert "official_route_queries" not in health["enabled_capabilities"]
        assert "official_route_dataset_version" not in health
        conversation = client.post("/api/chat/conversations").json()["id"]
        response = client.post(
            f"/api/chat/conversations/{conversation}/messages",
            json={
                "content": "Este mapa",
                "client_message_id": "disabled-map",
                "context": map_context(snapshot.document),
            },
        )
        assert response.status_code == 422 and "no está habilitado" in response.text
        assert provider.contexts == []


def test_wrong_dataset_pin_fails_app_startup(tmp_path, monkeypatch):
    snapshot = PublicSnapshot()
    settings = config(tmp_path, monkeypatch)
    from dataclasses import replace

    with pytest.raises(ValueError, match="pin"):
        create_app(
            config=replace(settings, official_route_dataset_sha256="0" * 64),
            snapshot=snapshot,
            provider=AdversarialProvider(),
        )


@pytest.mark.parametrize(
    ("scope", "carriers", "period"),
    [
        ("us", ["VIVA_AEROBUS", "VOLARIS", "AEROMEXICO"], "2026Q3"),
        ("us", ["VOLARIS", "AEROMEXICO"], "2026Q3"),
        ("national", [], "2026Q4"),
    ],
)
def test_stale_months_fail_admission_for_reordered_selection_or_unpublished_quarter(
    scope, carriers, period, tmp_path, monkeypatch
):
    snapshot = PublicSnapshot()
    provider = AdversarialProvider()
    app = create_app(config=config(tmp_path, monkeypatch), snapshot=snapshot, provider=provider)
    months = ["2026M07"] if period == "2026Q4" else []
    context = map_context(snapshot.document, scope, map_carriers=carriers, map_months=months)
    context["period"] = period
    with TestClient(app, base_url="http://127.0.0.1", client=("127.0.0.1", 50000)) as client:
        conversation = client.post("/api/chat/conversations").json()["id"]
        response = client.post(
            f"/api/chat/conversations/{conversation}/messages",
            json={
                "content": "Este mapa",
                "client_message_id": "stale-reordered-map",
                "context": context,
            },
        )
        assert response.status_code == 422 and "meses" in response.text
        assert provider.contexts == []
