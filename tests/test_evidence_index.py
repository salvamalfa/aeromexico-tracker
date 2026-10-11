from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.conversational_analytics.evidence_index import EvidenceIndex, EvidenceIndexError
from src.conversational_analytics.tools.evidence import dispatch_evidence_tool, evidence_tool_specs

FIXTURE = Path("tests/fixtures/chat_evidence/index.json")


def test_report_search_is_deterministic_filtered_and_cited() -> None:
    index = EvidenceIndex(FIXTURE)
    result = index.search_reports("Combustible aumentó", "Aeroméxico", "2026Q2")
    assert result["count"] == 1
    row = result["results"][0]
    assert (row["company"], row["period"], row["page"]) == ("Aeroméxico", "2026Q2", 12)
    assert row["citation"]["source_sha256"] == "a" * 64
    assert row["citation"]["url"].startswith("https://www.sec.gov/")
    assert index.search_reports("Combustible aumentó", "Volaris", "2026Q2")["count"] == 0
    assert index.search_reports("Combustible aumentó", "Aeroméxico", "2025Q4")["count"] == 0


def test_unapproved_record_is_never_searchable() -> None:
    result = EvidenceIndex(FIXTURE).search_reports("precio combustible", "Aeroméxico", "2026Q2")
    assert [row["id"] for row in result["results"]] == ["report-approved"]


def test_news_search_returns_bounded_ficha_and_date_citation() -> None:
    index = EvidenceIndex(FIXTURE)
    result = index.search_news("combustible costos", "2026-06-01", "2026-06-30", "Aeroméxico")
    assert result["count"] == 1
    row = result["results"][0]
    assert row["published_at"] == "2026-06-15"
    assert row["description"] == "Nota sobre precios del combustible en el sector aéreo."
    assert "body" not in row and "full_text" not in row
    assert row["citation"]["source_sha256"] == "c" * 64
    assert index.search_news("combustible", "2026-07-01", "2026-07-31", "Aeroméxico")["count"] == 0


def test_news_tool_schemas_are_closed_and_dispatch_rejects_extra_arguments() -> None:
    specs = evidence_tool_specs()
    assert {item["name"] for item in specs} == {"search_reports", "search_news"}
    assert all(item["parameters"]["additionalProperties"] is False for item in specs)
    result = dispatch_evidence_tool(
        "search_reports", {"query": "combustible", "extra": True}, EvidenceIndex(FIXTURE)
    )
    assert result == {"error": "argumentos inválidos"}


def test_invalid_source_host_and_unbounded_excerpt_are_rejected(tmp_path: Path) -> None:
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    approved = payload["records"][0]
    approved["source"]["url"] = "https://example.com/filing"
    path = tmp_path / "index.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(EvidenceIndexError, match="lista HTTPS permitida"):
        EvidenceIndex(path).search_reports("combustible", "Aeroméxico", "2026Q2")
