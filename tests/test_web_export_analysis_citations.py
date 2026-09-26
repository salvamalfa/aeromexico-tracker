"""Unit tests for the P6a citation export in ``src.web_export.analysis``.

``_claim_citations``/``_citations_by_claim`` are a pure-function port of
``src.analysis_agent.reader_ui.py::cite()``'s selection and href/title
construction (see ``web/README.md`` "Citations"). These tests build their
own tiny, synthetic package/calculations/draft — no local warehouse or
``analysis_runs/`` ledger needed — and assert the same filters, numbering
and public-only fields ``cite()`` itself enforces before anything reaches
the published page.
"""

from __future__ import annotations

from typing import Any

from src.web_export import analysis as web_analysis


def _package_and_calculations() -> tuple[dict[str, Any], dict[str, Any]]:
    package = {
        "period_id": "2026Q2",
        "sources": [
            {"artifact_id": "a1", "source_url": "https://www.sec.gov/example#other"},
            {"artifact_id": "a2", "source_url": "https://example.com/not-allowed"},
        ],
        "excerpts": [
            {"excerpt_id": "e1", "artifact_id": "a1", "text": "12.3 | 45.6"},
            {"excerpt_id": "e2", "artifact_id": "a1", "text": "Sin separador"},
            {"excerpt_id": "e3", "artifact_id": "a2", "text": "78.9"},
        ],
        "metrics": [
            {"metric_id": "m1", "excerpt_id": "e1", "artifact_id": "a1", "record_id": "r1"},
            {"metric_id": "m2", "excerpt_id": "e2", "artifact_id": "a1", "record_id": "r2"},
            {"metric_id": "m3", "excerpt_id": "e3", "artifact_id": "a2", "record_id": "r3"},
        ],
    }
    calculations = {
        "nodes": [
            {
                "calculation_id": "c_eligible", "period_id": "2026Q2", "key": "rask_cents_per_km",
                "unit": "cents_USD_per_ASK", "value": 5.5, "formula": "Reported normalized value",
                "formatted_value": "ignored", "input_ids": ["m1"],
            },
            {
                "calculation_id": "c_ask", "period_id": "2026Q2", "key": "ask",
                "unit": "seat_km", "value": 123.0, "formula": "some other formula",
                "formatted_value": "ignored", "input_ids": ["m2"],
            },
            {
                "calculation_id": "c_ineligible_formula", "period_id": "2026Q2", "key": "total_revenue",
                "unit": "USD", "value": 10.0, "formula": "fixture", "formatted_value": "ignored",
                "input_ids": ["m1"],
            },
            {
                "calculation_id": "c_wrong_period", "period_id": "2025Q2", "key": "rask_cents_per_km",
                "unit": "cents_USD_per_ASK", "value": 5.5, "formula": "Reported normalized value",
                "formatted_value": "ignored", "input_ids": ["m1"],
            },
            {
                "calculation_id": "c_untrusted_host", "period_id": "2026Q2", "key": "rask_cents_per_km",
                "unit": "cents_USD_per_ASK", "value": 9.9, "formula": "Reported normalized value",
                "formatted_value": "ignored", "input_ids": ["m3"],
            },
            {
                "calculation_id": "c_two_leaves", "period_id": "2026Q2", "key": "rask_cents_per_km",
                "unit": "cents_USD_per_ASK", "value": 1.0, "formula": "Reported normalized value",
                "formatted_value": "ignored", "input_ids": ["m1", "m2"],
            },
        ],
    }
    return package, calculations


def test_claim_citations_selects_only_eligible_bindings_with_public_fields() -> None:
    package, calculations = _package_and_calculations()
    claim = {
        "bindings": {
            "eligible": {"calculation_id": "c_eligible"},
            "period_label": {"calculation_id": "c_eligible", "presentation": "period_label"},
            "wrong_formula": {"calculation_id": "c_ineligible_formula"},
            "wrong_period": {"calculation_id": "c_wrong_period"},
            "untrusted_host": {"calculation_id": "c_untrusted_host"},
            "two_leaves": {"calculation_id": "c_two_leaves"},
        }
    }
    numbers: dict[str, int] = {}
    citations = web_analysis._claim_citations(claim, package, calculations, numbers)
    assert len(citations) == 1
    citation = citations[0]
    assert set(citation) == {"label", "href", "title", "value"}
    assert citation["label"] == "1"
    assert citation["href"] == "https://www.sec.gov/example#:~:text=12.3,45.6"
    assert citation["title"] == "Reporte original · 12.3: 45.6"
    assert citation["value"] == "5.50 centavos de dólar por asiento-kilómetro ofrecido"


def test_claim_citations_reuses_the_same_label_for_the_same_href() -> None:
    package, calculations = _package_and_calculations()
    claim_a = {"bindings": {"x": {"calculation_id": "c_eligible"}}}
    claim_b = {"bindings": {"x": {"calculation_id": "c_eligible"}}}
    numbers: dict[str, int] = {}
    first = web_analysis._claim_citations(claim_a, package, calculations, numbers)
    second = web_analysis._claim_citations(claim_b, package, calculations, numbers)
    assert first[0]["label"] == second[0]["label"] == "1"


def test_claim_citations_ask_key_is_eligible_regardless_of_formula() -> None:
    package, calculations = _package_and_calculations()
    claim = {"bindings": {"x": {"calculation_id": "c_ask"}}}
    citations = web_analysis._claim_citations(claim, package, calculations, {})
    assert len(citations) == 1
    assert citations[0]["title"].endswith("millones de asientos-milla; convertido a asientos-kilómetro.")


def _record(private_keys: list[str] | None = None) -> dict[str, Any]:
    return {
        "draft": {
            "summary_claim_ids": ["summary_claim"],
            "reader_private_section_keys": private_keys or [],
            "sections": [
                {"key": "public_section", "title": "Público", "claim_ids": ["public_claim"]},
                {"key": "private_section", "title": "Privado", "claim_ids": ["private_claim"]},
            ],
            "claims": [
                {"claim_id": "summary_claim", "bindings": {"x": {"calculation_id": "c_ask"}}},
                {"claim_id": "public_claim", "bindings": {"x": {"calculation_id": "c_eligible"}}},
                {"claim_id": "private_claim", "bindings": {"x": {"calculation_id": "c_eligible"}}},
            ],
        }
    }


def test_citations_by_claim_numbers_summary_before_sections_and_skips_private() -> None:
    package, calculations = _package_and_calculations()
    result = web_analysis._citations_by_claim(_record(["private_section"]), package, calculations)
    assert result["summary_claim"][0]["label"] == "1"
    assert result["public_claim"][0]["label"] == "2"
    assert "private_claim" not in result


def test_export_period_attaches_citations_and_section_claim_ids(monkeypatch) -> None:
    package, calculations = _package_and_calculations()
    record = _record(["private_section"])
    authorized = {
        "claims": [
            {"claim_id": cid, "type": "observed_fact", "text": "t", "calculation_ids": [], "evidence_ids": []}
            for cid in ("summary_claim", "public_claim", "private_claim")
        ],
        "sections": [
            {"title": "Público", "paragraphs": ["p"]},
            {"title": "Privado", "paragraphs": ["p"]},
        ],
    }
    monkeypatch.setattr(web_analysis, "_load_record", lambda period_id, version: record)
    monkeypatch.setattr(web_analysis.flow, "consumer_payload", lambda r, root: authorized)
    monkeypatch.setattr(web_analysis.flow, "verified_inputs", lambda r: (package, calculations, {}))

    result = web_analysis.export_period("2026Q2", "v1")

    assert [s["title"] for s in result["sections"]] == ["Público"]
    assert result["sections"][0]["claim_ids"] == ["public_claim"]
    citations_by_claim = {c["claim_id"]: c["citations"] for c in result["claims"]}
    assert citations_by_claim["summary_claim"][0]["label"] == "1"
    assert citations_by_claim["public_claim"][0]["label"] == "2"
    assert citations_by_claim["private_claim"] == []


def test_allowed_citation_hosts_matches_reader_ui_cite() -> None:
    """Keep the duplicated allow-list in sync (see analysis.py's comment)."""

    import inspect

    from src.analysis_agent import reader_ui

    source = inspect.getsource(reader_ui.refine)
    for host in web_analysis.ALLOWED_CITATION_HOSTS:
        assert f'"{host}"' in source
