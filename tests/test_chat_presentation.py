from __future__ import annotations

import json
from pathlib import Path

from src.conversational_analytics.config import ChatConfig
from src.conversational_analytics.data.snapshot import Snapshot
from src.conversational_analytics.presentation import DisplayRegistry, make_displays
from src.conversational_analytics.providers.base import ProviderResult
from src.conversational_analytics.storage import ChatStore
from src.conversational_analytics.tools.registry import ToolRegistry
from src.conversational_analytics.worker import TurnWorker

SITE = Path(__file__).parent / "fixtures/chat/site"


def test_market_table_cells_are_the_published_market_json_values() -> None:
    snapshot = Snapshot(SITE)
    registry = ToolRegistry(snapshot)
    result = registry.invoke(
        "query_metrics",
        {
            "metric_ids": ["market_share"],
            "entity_ids": ["VOLARIS", "VIVA_AEROBUS", "AEROMEXICO"],
            "periods": ["2026Q2"],
            "segment": "total",
        },
    )
    catalog = snapshot.catalog()
    enriched = make_displays(result, "query_metrics", "call-market-share", catalog)
    display = enriched["display"]
    market = json.loads((SITE / "data/v1/market.json").read_text())
    quarter = next(item for item in market["quarters"] if item["period_id"] == "2026Q2")
    published = quarter["segments"]["total"]["carriers"]
    displayed = {row["entity"]: row["value"] for row in display["rows"]}
    for entity_id in ("VOLARIS", "VIVA_AEROBUS", "AEROMEXICO"):
        label = next(item["label"] for item in catalog["entities"]["entities"] if item["id"] == entity_id)
        assert displayed[label] == published[entity_id]["share"]
    assert display["rows"][0]["period"] == "2T26"


def test_unknown_and_other_turn_markers_are_removed_without_artifacts() -> None:
    registry = DisplayRegistry()
    registry.add(
        {
            "display_id": "tabla:only_this_turn",
            "kind": "table",
            "title": "Tabla",
            "columns": [{"key": "value", "label": "Valor"}],
            "rows": [{"value": 1}],
            "value_kind": "reported",
        }
    )
    content, displays, references = registry.finalize(
        "Resultado {{tabla:only_this_turn}} {{tabla:old_turn}} {{grafica:missing}}"
    )
    assert content == "Resultado {{tabla:only_this_turn}}  "
    assert [display["display_id"] for display in displays] == ["tabla:only_this_turn"]
    assert references == []
    another_turn = DisplayRegistry()
    content, displays, _ = another_turn.finalize("{{tabla:only_this_turn}}")
    assert content == ""
    assert displays == []


def test_missing_cells_remain_null_and_source_urls_are_deduplicated() -> None:
    result = {
        "rows": [
            {
                "metric_id": "market_share",
                "entity_id": "VOLARIS",
                "period": "2026Q2",
                "period_label": "2T26",
                "value": None,
                "unit": "fraction",
                "value_kind": "reported",
            }
        ],
        "references": [
            {"label": "AFAC, estadística mensual, junio 2026", "url": "https://www.gob.mx/afac/source"},
            {"label": "AFAC duplicada", "url": "https://www.gob.mx/afac/source"},
        ],
    }
    enriched = make_displays(result, "query_metrics", "call-missing")
    assert enriched["display"]["rows"][0]["value"] is None
    assert enriched["display"]["sources"] == [
        {"label": "AFAC, estadística mensual, junio 2026", "url": "https://www.gob.mx/afac/source"}
    ]


def test_invalid_display_shape_is_not_registered() -> None:
    registry = DisplayRegistry()
    assert (
        registry.add(
            {
                "display_id": "tabla:bad",
                "kind": "table",
                "title": "Tabla",
                "value_kind": "reported",
                "columns": [{"key": "value", "label": "Valor"}],
                "rows": [{"value": float("nan")}],
            }
        )
        is None
    )
    content, displays, _ = registry.finalize("{{tabla:bad}}")
    assert content == ""
    assert displays == []


def test_route_tool_contract_accepts_observed_and_missing_display_objects() -> None:
    registry = DisplayRegistry()
    route_result = {
        "display": {
            "display_id": "tabla:rutas_aeromexico_2026Q2",
            "kind": "table",
            "title": "Rutas por aerolínea",
            "columns": [{"key": "route", "label": "Ruta"}, {"key": "value", "label": "Pasajeros"}],
            "rows": [{"route": "MEX-LAX", "value": 123, "value_kind": "observed"}],
            "value_kind": "observed",
            "source": {
                "label": "Dashboard público · 2T26",
                "url": "https://salvamalfa.github.io/aeromexico-tracker/data/v1/routes.json",
            },
        },
    }
    enriched = registry.add_tool_result(route_result, "query_routes", "route-call")
    assert enriched["display"]["value_kind"] == "observed"
    assert enriched["display"]["rows"][0]["value"] == 123
    missing = registry.add(
        {
            "display_id": "tabla:rutas_aeromexico_missing",
            "kind": "table",
            "title": "Rutas",
            "columns": [{"key": "value", "label": "Pasajeros"}],
            "rows": [],
            "value_kind": "missing",
        }
    )
    assert missing is not None
    assert missing["rows"] == []


def test_worker_persists_only_marked_turn_displays_with_no_extra_provider_call(tmp_path: Path) -> None:
    class DisplaySnapshot:
        version = "snapshot-v1"
        semantic_version = "semantic-v1"

        @staticmethod
        def catalog() -> dict:
            return {}

    class Registry:
        @staticmethod
        def tool_specs() -> list[dict]:
            return []

        @staticmethod
        def invoke(name: str, args: dict, context: dict) -> dict:
            return {
                "rows": [
                    {
                        "metric_id": "market_share",
                        "entity_id": "VOLARIS",
                        "period": "2026Q2",
                        "period_label": "2T26",
                        "value": 0.366615816786413,
                        "unit": "fraction",
                        "value_kind": "reported",
                    }
                ],
                "references": [
                    {
                        "label": "AFAC, estadística mensual, junio 2026",
                        "url": "https://www.gob.mx/afac/source",
                    }
                ],
            }

    class Provider:
        calls = 0

        def run_turn(self, **kwargs):
            self.calls += 1
            output = kwargs["call_tool"]("provider-turn", "tool-call", "query_metrics", {})
            marker = output["display"]["display_id"]
            return ProviderResult(
                f"Market share: {{{{{marker}}}}}",
                input_tokens=10,
                output_tokens=5,
                usage_complete=True,
            )

        @staticmethod
        def cancel(session_id: str):
            return None

        @staticmethod
        def delete(session_id: str):
            return None

    snapshot = DisplaySnapshot()
    store = ChatStore(tmp_path / "chat.sqlite3")
    conversation = store.create_conversation("alice", snapshot.version, snapshot.semantic_version)
    turn, _ = store.submit_turn("alice", conversation["id"], "ask", "message-1", {}, reserved_tokens=100)
    provider = Provider()
    worker = TurnWorker(store, ChatConfig(state_path=tmp_path / "chat.sqlite3"), provider, snapshot)
    worker._registry = Registry()
    worker._execute_turn(store.claim_turn())

    events = store.list_events("alice", turn["id"])
    completed = next(event["data"] for event in events if event["type"] == "message.completed")
    history = store.get_conversation("alice", conversation["id"])
    assert provider.calls == 1
    marker = f"{{{{{completed['displays'][0]['display_id']}}}}}"
    assert completed["content"] == f"Market share: {marker}"
    assert completed["displays"][0]["rows"][0]["value"] == 0.366615816786413
    assert history["messages"][-1]["displays"] == completed["displays"]
