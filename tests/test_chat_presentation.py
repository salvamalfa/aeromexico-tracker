from __future__ import annotations

import json
from pathlib import Path

from src.conversational_analytics.config import ChatConfig
from src.conversational_analytics.data.snapshot import Snapshot
from src.conversational_analytics.presentation import DisplayRegistry, make_displays
from src.conversational_analytics.providers._openai_helpers import references_from_results
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
    metric_label = next(
        item["label"] for item in catalog["metrics"]["metrics"] if item["id"] == "market_share"
    )
    assert display["title"] == metric_label
    assert next(column for column in display["columns"] if column["key"] == "value")["unit"] == "fraction"
    assert display["rows"][0]["period"] == "2T26"


def test_fallback_value_kind_comes_from_metric_definition_and_candidate_gate_stays_closed() -> None:
    snapshot = Snapshot(SITE)
    registry = ToolRegistry(snapshot)
    result = registry.invoke(
        "query_metrics",
        {
            "metric_ids": ["unit_margin_cents_per_km"],
            "entity_ids": ["AEROMEXICO"],
            "periods": ["2026Q2"],
        },
    )
    display = make_displays(result, "query_metrics", "call-margin", snapshot.catalog())["display"]
    assert display["value_kind"] == "calculated"
    value_column = next(column for column in display["columns"] if column["key"] == "value")
    assert value_column["label"] == "Valor (¢ USD/ASK-km)"

    # Older metric catalog snapshots may omit the calculation annotation.
    legacy_catalog = {"metrics": {"metrics": [{"id": "unit_margin_cents_per_km", "label": "Margen unitario"}]}}
    legacy_result = {
        "rows": [{"metric_id": "unit_margin_cents_per_km", "entity_id": "AEROMEXICO", "period": "2026Q2", "value": 0.43, "unit": "cents/ASK-km"}]
    }
    assert make_displays(legacy_result, "query_metrics", "legacy-margin", legacy_catalog)["display"]["value_kind"] == "calculated"

    candidate = {
        "rows": [
            {
                "metric_id": "candidate_metric",
                "period": "2026Q2",
                "value": None,
                "availability": "approval_required",
                "approval_gate": "closed",
                "value_kind": "candidate_unapproved",
                "unit": "USD",
            }
        ],
    }
    closed_catalog = {
        "metrics": {
            "metrics": [
                {"id": "candidate_metric", "label": "Candidato", "review_status": "candidate_unapproved"}
            ]
        }
    }
    closed_display = make_displays(candidate, "query_business_metrics", "call-candidate", closed_catalog)
    assert "display" not in closed_display
    assert "displays" not in closed_display
    # Candidate data may be serialized as text, including financial-looking
    # strings, so the gate suppresses the whole display instead of parsing it.
    candidate["rows"][0]["value"] = "100 pasajeros"
    assert "display" not in make_displays(candidate, "query_business_metrics", "call-candidate-text", closed_catalog)
    candidate["rows"][0]["value"] = "$1,200 USD"
    assert "display" not in make_displays(candidate, "query_business_metrics", "call-candidate-currency", closed_catalog)
    candidate["rows"][0]["value"] = 100
    assert "display" not in make_displays(candidate, "query_business_metrics", "call-candidate-value", closed_catalog)

    assert (
        DisplayRegistry().add(
            {
                "display_id": "tabla:candidate_value",
                "kind": "table",
                "title": "Candidato",
                "value_kind": "candidate_unapproved",
                "columns": [{"key": "value", "label": "Valor"}],
                "rows": [{"value": 100}],
            }
        )
        is None
    )


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


def test_numeric_markdown_table_is_removed_only_with_a_valid_display_marker() -> None:
    registry = DisplayRegistry()
    registry.add({
        "display_id": "tabla:verified",
        "kind": "table",
        "title": "Dato verificado",
        "value_kind": "reported",
        "columns": [{"key": "value", "label": "Valor"}],
        "rows": [{"value": 84.9}],
    })
    content = "Dato: 84.9% {{tabla:missing}} {{tabla:verified}}\n\n| Métrica | Valor |\n\n| --- | ---: |\n\n| Factor | 99.9% |\n\n| Estado | Nota |\n| --- | --- |\n| Margen | calculado |"
    sanitized, displays, _ = registry.finalize(content)
    assert "99.9%" not in sanitized
    assert "{{tabla:missing}}" not in sanitized
    assert "| Estado | Nota |" in sanitized
    assert "| Margen | calculado |" in sanitized
    assert len(displays) == 1

    # Escaped pipes use the same cell grammar as the browser. A numeric row
    # after an escaped delimiter must not evade suppression.
    escaped = "{{tabla:verified}}\n\n| Factor \\| ajustado | Valor |\n| --- | ---: |\n| Ocupación | 99.9% |"
    escaped_sanitized, _, _ = registry.finalize(escaped)
    assert "99.9%" not in escaped_sanitized

    # Legacy R1 content has no valid marker, so its Markdown table stays intact.
    legacy, _, _ = DisplayRegistry().finalize("| Métrica | Valor |\n| --- | ---: |\n| Factor | 99.9% |")
    assert "99.9%" in legacy


def test_shared_markdown_table_corpus_matches_server_suppression_grammar() -> None:
    cases_path = Path(__file__).parents[1] / "web/src/views/chat/markdown_table_cases.json"
    cases = json.loads(cases_path.read_text(encoding="utf-8"))
    registry = DisplayRegistry()
    registry.add({
        "display_id": "tabla:corpus",
        "kind": "table",
        "title": "Tabla validada",
        "value_kind": "reported",
        "columns": [{"key": "value", "label": "Valor"}],
        "rows": [{"value": 1}],
    })
    for case in cases:
        markdown = f"{{{{tabla:corpus}}}}\n\n{case['markdown']}"
        sanitized, _, _ = registry.finalize(markdown)
        table_text = "\n".join(case["markdown"].splitlines())
        assert (table_text not in sanitized) is case["value_bearing"], case["name"]


def test_mixed_metric_query_keeps_each_value_unit_explicit() -> None:
    mixed = {
        "rows": [
            {"metric_id": "unit_margin_cents_per_km", "metric_label": "Margen unitario", "entity_id": "AEROMEXICO", "period": "2026Q2", "value": 0.435, "unit": "USD_cents_per_ASK_km"},
            {"metric_id": "revenue", "metric_label": "Ingresos", "entity_id": "AEROMEXICO", "period": "2026Q2", "value": 1479, "unit": "USD_millions"},
            {"metric_id": "load_factor_reported", "metric_label": "Factor de ocupación", "entity_id": "AEROMEXICO", "period": "2026Q2", "value": 0.849, "unit": "fraction"},
        ]
    }
    display = make_displays(mixed, "query_metrics", "mixed-units")["display"]
    assert {column["key"] for column in display["columns"]} >= {"value", "unit", "metric"}
    assert [row["unit"] for row in display["rows"]] == ["USD_cents_per_ASK_km", "USD_millions", "fraction"]
    assert [row["value"] for row in display["rows"]] == [0.435, 1479, 0.849]


def test_missing_cells_remain_null_and_duplicate_source_labels_are_combined() -> None:
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
        {"label": "AFAC, estadística mensual, junio 2026 · AFAC duplicada", "url": "https://www.gob.mx/afac/source"},
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


def test_display_without_value_kind_is_labeled_unknown_not_reported() -> None:
    display = DisplayRegistry().add(
        {
            "display_id": "tabla:unknown_kind",
            "kind": "table",
            "title": "Tipo ausente",
            "columns": [{"key": "value", "label": "Valor"}],
            "rows": [{"value": 12}],
        }
    )
    assert display is not None
    assert display["value_kind"] == "unknown"


def test_verified_financial_and_reporting_sources_survive_but_unknown_hosts_do_not() -> None:
    display = DisplayRegistry().add(
        {
            "display_id": "tabla:verified_sources",
            "kind": "table",
            "title": "Fuentes verificadas",
            "columns": [{"key": "value", "label": "Valor"}],
            "rows": [{"value": 1}],
            "value_kind": "reported",
            "sources": [
                {"label": "Aeroméxico IR", "url": "https://ir.aeromexico.com/report-q2.pdf"},
                {"label": "Viva InvestorCloud", "url": "https://cdn.investorcloud.net/viva/report-q2.pdf"},
                {"label": "FlightGlobal", "url": "https://www.flightglobal.com/news/article.html"},
                {
                    "label": "BMV · Aeroméxico 2026Q2",
                    "url": "https://www.bmv.com.mx/docs-pub/ifrsxbrl/ifrsxbrl_1573911_2026-02_1.zip#member=am_q2.json",
                },
                {
                    "label": "BMV unverified fragment",
                    "url": "https://www.bmv.com.mx/docs-pub/ifrsxbrl/ifrsxbrl_1573911_2026-02_1.zip#other=am_q2.json",
                },
                {
                    "label": "BMV encoded fragment",
                    "url": "https://www.bmv.com.mx/docs-pub/ifrsxbrl/ifrsxbrl_1573911_2026-02_1.zip#member%3Dam_q2.json",
                },
                {
                    "label": "BMV noncanonical fragment",
                    "url": "https://www.bmv.com.mx/docs-pub/ifrsxbrl/ifrsxbrl_1573911_2026-02_1.zip#Member=am_q2.json",
                },
                {"label": "Unverified", "url": "https://example.org/article"},
            ],
        }
    )

    assert display is not None
    assert [source["label"] for source in display["sources"]] == [
        "Aeroméxico IR",
        "Viva InvestorCloud",
        "FlightGlobal",
        "BMV · Aeroméxico 2026Q2 · miembro ZIP am_q2.json",
    ]
    bmv = display["sources"][-1]
    assert bmv["url"] == "https://www.bmv.com.mx/docs-pub/ifrsxbrl/ifrsxbrl_1573911_2026-02_1.zip"
    references = references_from_results(
        [
            {
                "source_references": [
                    {"label": source["label"], "url": source["url"]} for source in display["sources"]
                ]
                + [{"label": "Unverified", "url": "https://example.org/article"}]
            }
        ]
    )
    assert {reference["url"] for reference in references} == {
        "https://ir.aeromexico.com/report-q2.pdf",
        "https://cdn.investorcloud.net/viva/report-q2.pdf",
        "https://www.flightglobal.com/news/article.html",
        "https://www.bmv.com.mx/docs-pub/ifrsxbrl/ifrsxbrl_1573911_2026-02_1.zip",
    }


def test_same_source_url_keeps_distinct_member_labels() -> None:
    registry = DisplayRegistry()
    registry.add(
        {
            "display_id": "tabla:two_members",
            "kind": "table",
            "title": "Dos miembros BMV",
            "columns": [{"key": "value", "label": "Valor"}],
            "rows": [{"value": 1}],
            "value_kind": "reported",
            "sources": [
                {
                    "label": "Reporte · miembro ZIP q1.json",
                    "url": "https://www.bmv.com.mx/docs-pub/ifrsxbrl/package.zip",
                }
            ],
        }
    )
    _, displays, references = registry.finalize(
        "{{tabla:two_members}}",
        [
            {
                "label": "Reporte · miembro ZIP q2.json",
                "url": "https://www.bmv.com.mx/docs-pub/ifrsxbrl/package.zip",
            }
        ],
    )
    assert len(displays) == 1
    assert references == []
    assert displays[0]["sources"] == [{
        "label": "Reporte · miembro ZIP q2.json · Reporte · miembro ZIP q1.json",
        "url": "https://www.bmv.com.mx/docs-pub/ifrsxbrl/package.zip",
    }]


def test_provider_references_deduplicate_by_url_and_keep_distinct_page_labels() -> None:
    references = references_from_results([
        {"references": [
            {"label": "Reporte Aeroméxico 2026Q2, p. 12", "url": "https://www.sec.gov/report"},
            {"label": "Reporte Aeroméxico 2026Q2, p. 13", "url": "https://www.sec.gov/report"},
        ]}
    ])
    assert references == [{
        "label": "Reporte Aeroméxico 2026Q2, p. 12; Reporte Aeroméxico 2026Q2, p. 13",
        "url": "https://www.sec.gov/report",
    }]


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
