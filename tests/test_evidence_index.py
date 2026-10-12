from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.conversational_analytics.evidence_index import EvidenceIndex, EvidenceIndexError
from src.conversational_analytics.data.snapshot import Snapshot
from src.conversational_analytics.providers._openai_references import references_from_results
from src.conversational_analytics.tools.evidence import dispatch_evidence_tool, evidence_tool_specs
from src.conversational_analytics.tools.registry import ToolRegistry

FIXTURE = Path("tests/fixtures/chat_evidence/index.json")


def test_report_search_is_deterministic_filtered_and_cited() -> None:
    index = EvidenceIndex(FIXTURE)
    result = index.search_reports("aumentó", "Aeroméxico", "2026Q2")
    assert result["count"] == 1
    row = result["results"][0]
    assert (row["company"], row["period"], row["section"], row["page"]) == (
        "Aeroméxico", "2026Q2", "Combustible", 12
    )
    assert row["citation"]["source_sha256"] == "a" * 64
    assert row["citation"]["url"].startswith("https://www.sec.gov/")
    assert index.search_reports("aumentó", "Volaris", "2026Q2")["count"] == 0
    assert index.search_reports("aumentó", "Aeroméxico", "2025Q4")["count"] == 0


def test_each_report_hit_keeps_its_own_page_in_filtered_and_unfiltered_search() -> None:
    index = EvidenceIndex(FIXTURE)
    all_hits = index.search_reports("combustible", limit=5)["results"]
    assert [(row["id"], row["page"], row["citation"]["label"]) for row in all_hits] == [
        ("report-approved", 12, "Reporte Aeroméxico 2026Q2, p. 12"),
        ("report-approved-page-13", 13, "Reporte Aeroméxico 2026Q2, p. 13"),
    ]
    filtered = index.search_reports("combustible", "Aeroméxico", "2026Q2")["results"]
    assert [row["page"] for row in filtered] == [12, 13]


def test_unapproved_record_is_never_searchable() -> None:
    result = EvidenceIndex(FIXTURE).search_reports("movimientos", "Aeroméxico", "2026Q2")
    assert result["count"] == 0


def test_news_search_returns_bounded_ficha_and_date_citation() -> None:
    index = EvidenceIndex(FIXTURE)
    result = index.search_news("combustible costos", "2026-06-01", "2026-06-30", "Aeroméxico")
    assert result["count"] == 1
    row = result["results"][0]
    assert row["published_at"] == "2026-06-15"
    assert row["description"] == "Nota sobre precios del combustible en el sector aéreo."
    assert "body" not in row and "full_text" not in row
    assert row["citation"]["source_sha256"] == "c" * 64
    assert row["references"] == [{
        "label": "Fuente pública fixture · Combustible y aerolíneas (2026-06-15)",
        "url": "https://www.sec.gov/Archives/edgar/data/1/news.htm",
    }]
    assert index.search_news("combustible", "2026-07-01", "2026-07-31", "Aeroméxico")["count"] == 0


def test_registry_evidence_hits_reach_provider_references_with_exact_urls() -> None:
    class Capabilities:
        enable_evidence_tools = True
        enable_route_tools = False
        enable_business_metric_tools = False

    registry = ToolRegistry(Snapshot(Path("tests/fixtures/chat/site")), Capabilities())
    registry._evidence_index = EvidenceIndex(FIXTURE)
    report = registry.invoke(
        "search_reports", {"query": "aumentó", "company": "Aeroméxico", "period": "2026Q2", "limit": 5}
    )
    news = registry.invoke(
        "search_news", {
            "query": "combustible costos", "start_date": "2026-06-01", "end_date": "2026-06-30",
            "company": "Aeroméxico", "limit": 5,
        }
    )
    refs = references_from_results([report, news])
    assert refs == [
        {
            "label": "Reporte Aeroméxico 2026Q2, p. 12",
            "url": "https://www.sec.gov/Archives/edgar/data/1/fixture.htm",
        },
        {
            "label": "Fuente pública fixture · Combustible y aerolíneas (2026-06-15)",
            "url": "https://www.sec.gov/Archives/edgar/data/1/news.htm",
        },
    ]


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
        EvidenceIndex(path)


def test_receipt_must_bind_candidate_source_and_excerpt(tmp_path: Path) -> None:
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    approved = payload["records"][0]
    approved["review"]["receipt"]["source_sha256"] = "f" * 64
    path = tmp_path / "index.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    result = EvidenceIndex(path).search_reports("combustible", "Aeroméxico", "2026Q2")
    assert "report-approved" not in [row["id"] for row in result["results"]]


def test_receipt_must_bind_all_semantic_citation_and_search_metadata(tmp_path: Path) -> None:
    mutations = [
        ("report-approved", ("page",), 99, "report"),
        ("report-approved", ("company",), "Volaris", "report"),
        ("report-approved", ("period",), "2025Q2", "report"),
        (
            "report-approved", ("source", "url"),
            "https://www.sec.gov/Archives/edgar/data/1/other.htm", "report",
        ),
        ("report-approved", ("section",), "Ingresos", "report"),
        ("news-approved", ("title",), "Titular modificado", "news"),
        ("news-approved", ("published_at",), "2026-06-16", "news"),
        ("news-approved", ("topics",), ["otro tema"], "news"),
        ("news-approved", ("companies",), ["Volaris"], "news"),
    ]
    for case_number, (record_id, keys, value, kind) in enumerate(mutations):
        payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
        row = next(item for item in payload["records"] if item["id"] == record_id)
        target = row
        for key in keys[:-1]:
            target = target[key]
        target[keys[-1]] = value
        path = tmp_path / f"index-{case_number}.json"
        path.write_text(json.dumps(payload), encoding="utf-8")
        evidence_index = EvidenceIndex(path)
        if kind == "report":
            result = evidence_index.search_reports("combustible", limit=5)
        else:
            result = evidence_index.search_news("combustible", limit=5)
        assert record_id not in [match["id"] for match in result["results"]]


def test_real_report_candidates_stay_closed_and_are_not_an_approved_index() -> None:
    candidate_path = Path("config/chat/evidence/candidates/reports-candidate.json")
    payload = json.loads(candidate_path.read_text(encoding="utf-8"))
    assert payload["status"] == "candidate_closed"
    assert len(payload["records"]) == 7
    assert all(row["review"]["receipt"] is None for row in payload["records"])
    assert all(len(row["excerpt"]) <= 480 and row["page"] >= 1 for row in payload["records"])
    assert {row["company"] for row in payload["records"]} == {"Aeroméxico", "Volaris", "Viva Aerobus"}
    volaris = [row for row in payload["records"] if row["company"] == "Volaris"]
    assert all(row["source"]["identity_status"] == "byte_identity_mismatch_pending_review" for row in volaris)
    assert (
        EvidenceIndex("config/chat/evidence/approved-index.json").search_reports("combustible")["count"] == 0
    )


def test_real_news_candidates_are_bounded_hash_pinned_and_pending() -> None:
    paths = sorted(Path("config/chat/evidence/candidates/news").glob("news-*.json"))
    candidates = [
        record for path in paths for record in json.loads(path.read_text(encoding="utf-8"))["records"]
    ]
    assert len(candidates) == 3
    assert all(row["review"]["receipt"] is None for row in candidates)
    assert all(len(row["description"]) <= 320 and len(row["source_sha256"]) == 64 for row in candidates)
    assert all(row["url"].startswith("https://www.flightglobal.com/") for row in candidates)


def test_f27_case_uses_all_three_cited_layers_without_approval_claims() -> None:
    case_path = Path("config/chat/evidence/candidates/f2-7-explanation-cases.json")
    case = json.loads(case_path.read_text(encoding="utf-8"))["cases"][0]
    report_ids = {
        row["candidate_id"]
        for row in json.loads(Path("config/chat/evidence/candidates/reports-candidate.json").read_text())[
            "records"
        ]
    }
    news_ids = {
        row["candidate_id"]
        for path in Path("config/chat/evidence/candidates/news").glob("news-*.json")
        for row in json.loads(path.read_text(encoding="utf-8"))["records"]
    }
    assert set(case["evidence_layers"]["reported_data"]) <= report_ids
    assert set(case["evidence_layers"]["company_attribution"]) <= report_ids
    assert set(case["evidence_layers"]["news_context"]) <= news_ids
    assert case["review"] == {"status": "owner_review_required", "receipt": None}
