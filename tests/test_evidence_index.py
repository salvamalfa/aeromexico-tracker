from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator

from src.conversational_analytics.data.snapshot import Snapshot
from src.conversational_analytics.evidence_index import (
    APPROVED_INDEX_SHA256_ENV,
    EvidenceIndex,
    EvidenceIndexError,
    candidate_content_sha256,
    canonical_index_sha256,
)
from src.conversational_analytics.providers._openai_references import references_from_results
from src.conversational_analytics.tools.evidence import dispatch_evidence_tool, evidence_tool_specs
from src.conversational_analytics.tools.registry import ToolRegistry

FIXTURE = Path("tests/fixtures/chat_evidence/index.json")


@pytest.fixture(autouse=True)
def _pin_synthetic_fixture(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    monkeypatch.setenv(APPROVED_INDEX_SHA256_ENV, canonical_index_sha256(payload))


def _write_index(path: Path, payload: dict[str, Any], monkeypatch: pytest.MonkeyPatch) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")
    monkeypatch.setenv(APPROVED_INDEX_SHA256_ENV, canonical_index_sha256(payload))


def _refresh_receipt(record: dict[str, Any]) -> None:
    receipt = record["review"]["receipt"]
    excerpt = record.get("excerpt", record.get("description"))
    receipt["candidate_id"] = record["id"]
    receipt["source_sha256"] = record["source"]["sha256"]
    receipt["excerpt_sha256"] = hashlib.sha256(excerpt.encode("utf-8")).hexdigest()
    receipt["candidate_content_sha256"] = candidate_content_sha256(record)


def _padded(prefix: str, size: int) -> str:
    return prefix + ("x" * (size - len(prefix)))


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


def test_unfiltered_report_results_keep_each_records_own_period_and_citation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    second = next(row for row in payload["records"] if row["id"] == "report-approved-page-13")
    second["period"] = "2025Q4"
    second["review"]["receipt"]["candidate_content_sha256"] = candidate_content_sha256(second)
    index_path = tmp_path / "periods-index.json"
    _write_index(index_path, payload, monkeypatch)

    hits = EvidenceIndex(index_path).search_reports("combustible")["results"]
    assert {row["id"]: (row["period"], row["citation"]["label"]) for row in hits} == {
        "report-approved": ("2026Q2", "Reporte Aeroméxico 2026Q2, p. 12"),
        "report-approved-page-13": ("2025Q4", "Reporte Aeroméxico 2025Q4, p. 13"),
    }


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


def test_contract_maximum_field_lengths_remain_searchable_at_exact_boundaries(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    report = next(row for row in payload["records"] if row["id"] == "report-approved")
    report["id"] = "r" * 120
    report["company"] = "A" * 100
    report["section"] = _padded("combustible ", 240)
    report["excerpt"] = _padded("combustible ", 480)
    report["source"]["id"] = "s" * 120
    report["source"]["url"] = "https://www.sec.gov/" + ("u" * (1000 - len("https://www.sec.gov/")))
    _refresh_receipt(report)

    news = next(row for row in payload["records"] if row["id"] == "news-approved")
    news["id"] = "n" * 120
    news["publisher"] = "P" * 120
    news["title"] = _padded("costos ", 300)
    news["description"] = _padded("costos ", 320)
    news["companies"] = ["C" * 100 for _ in range(10)]
    news["topics"] = ["t" * 80 for _ in range(20)]
    news["brief_quote"] = ""
    news["source"]["id"] = "i" * 120
    news["source"]["url"] = "https://www.sec.gov/" + ("v" * (1000 - len("https://www.sec.gov/")))
    _refresh_receipt(news)
    payload["records"] = [
        record for record in payload["records"]
        if record.get("review", {}).get("decision") == "owner_approved"
    ]

    schema = json.loads(Path("contracts/chat/evidence-index.schema.json").read_text(encoding="utf-8"))
    assert list(Draft202012Validator(schema).iter_errors(payload)) == []
    index_path = tmp_path / "boundary-index.json"
    _write_index(index_path, payload, monkeypatch)
    index = EvidenceIndex(index_path)

    report_hit = index.search_reports("combustible")["results"][0]
    assert len(report_hit["id"]) == 120
    assert len(report_hit["company"]) == 100
    assert len(report_hit["section"]) == 240
    assert len(report_hit["excerpt"]) == 480
    assert len(report_hit["citation"]["url"]) == 1000
    assert len(report_hit["citation"]["source_id"]) == 120

    news_hit = index.search_news("costos")["results"][0]
    assert len(news_hit["id"]) == 120
    assert len(news_hit["publisher"]) == 120
    assert len(news_hit["title"]) == 300
    assert len(news_hit["description"]) == 320
    assert len(news_hit["companies"]) == 10 and all(len(item) == 100 for item in news_hit["companies"])
    assert len(news_hit["topics"]) == 20 and all(len(item) == 80 for item in news_hit["topics"])
    assert news_hit["brief_quote"] == ""
    assert len(news_hit["citation"]["url"]) == 1000
    assert len(news_hit["citation"]["source_id"]) == 120


@pytest.mark.parametrize(
    ("record_id", "field_path", "value", "search_kind", "query"),
    [
        ("report-approved", ("section",), "s" * 241, "report", "combustible"),
        ("report-approved", ("section",), _padded("combustible ", 240) + " ", "report", "combustible"),
        ("report-approved", ("section",), "", "report", "combustible"),
        ("report-approved", ("period",), "2026Q22", "report", "combustible"),
        ("news-approved", ("title",), "t" * 301, "news", "combustible"),
        ("news-approved", ("companies",), ["c" * 101], "news", "combustible"),
        ("news-approved", ("companies",), ["C"] * 11, "news", "combustible"),
        ("news-approved", ("topics",), ["t" * 81], "news", "combustible"),
        ("news-approved", ("topics",), ["T"] * 21, "news", "combustible"),
        ("news-approved", ("brief_quote",), "q" * 201, "news", "combustible"),
    ],
)
def test_over_contract_search_fields_are_rejected(
    record_id: str,
    field_path: tuple[str, ...],
    value: Any,
    search_kind: str,
    query: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    record = next(row for row in payload["records"] if row["id"] == record_id)
    target = record
    for key in field_path[:-1]:
        target = target[key]
    target[field_path[-1]] = value
    _refresh_receipt(record)
    payload["records"] = [
        item for item in payload["records"]
        if item.get("review", {}).get("decision") == "owner_approved"
    ]
    schema = json.loads(Path("contracts/chat/evidence-index.schema.json").read_text(encoding="utf-8"))
    assert list(Draft202012Validator(schema).iter_errors(payload))
    index_path = tmp_path / f"over-contract-{record_id}-{field_path[0]}.json"
    _write_index(index_path, payload, monkeypatch)
    index = EvidenceIndex(index_path)
    with pytest.raises(EvidenceIndexError):
        if search_kind == "report":
            index.search_reports(query)
        else:
            index.search_news(query)


def test_registry_evidence_hits_reach_provider_references_with_exact_urls(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class Capabilities:
        enable_evidence_tools = True
        enable_route_tools = False
        enable_business_metric_tools = False

    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    index_path = tmp_path / "config/chat/evidence/approved-index.json"
    index_path.parent.mkdir(parents=True)
    index_path.write_text(json.dumps(payload), encoding="utf-8")
    monkeypatch.setenv(APPROVED_INDEX_SHA256_ENV, canonical_index_sha256(payload))
    snapshot = Snapshot(Path("tests/fixtures/chat/site"))
    snapshot.project_root = tmp_path
    registry = ToolRegistry(snapshot, Capabilities())
    assert registry.evidence_index_sha256 == hashlib.sha256(index_path.read_bytes()).hexdigest()
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


def test_invalid_source_host_and_unbounded_excerpt_are_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    approved = payload["records"][0]
    approved["source"]["url"] = "https://example.com/filing"
    path = tmp_path / "index.json"
    _write_index(path, payload, monkeypatch)
    with pytest.raises(EvidenceIndexError, match="lista HTTPS permitida"):
        EvidenceIndex(path)


def test_receipt_must_bind_candidate_source_and_excerpt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    approved = payload["records"][0]
    approved["review"]["receipt"]["source_sha256"] = "f" * 64
    path = tmp_path / "index.json"
    _write_index(path, payload, monkeypatch)
    result = EvidenceIndex(path).search_reports("combustible", "Aeroméxico", "2026Q2")
    assert "report-approved" not in [row["id"] for row in result["results"]]


def test_receipt_must_bind_all_semantic_citation_and_search_metadata(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
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
        _write_index(path, payload, monkeypatch)
        evidence_index = EvidenceIndex(path)
        if kind == "report":
            result = evidence_index.search_reports("combustible", limit=5)
        else:
            result = evidence_index.search_news("combustible", limit=5)
        assert record_id not in [match["id"] for match in result["results"]]


def test_nonempty_index_requires_external_canonical_pin_and_rejects_local_rehash(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    index_path = tmp_path / "approved-index.json"
    index_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    monkeypatch.delenv(APPROVED_INDEX_SHA256_ENV)
    with pytest.raises(EvidenceIndexError, match="debe fijar"):
        EvidenceIndex(index_path)

    pin = canonical_index_sha256(payload)
    monkeypatch.setenv(APPROVED_INDEX_SHA256_ENV, pin)
    assert EvidenceIndex(index_path).search_reports("combustible")["count"] == 2

    # Whitespace and key order do not alter the canonical object hash.
    index_path.write_text(json.dumps(payload, ensure_ascii=False, indent=4), encoding="utf-8")
    assert EvidenceIndex(index_path).search_reports("combustible")["count"] == 2

    forged = json.loads(json.dumps(payload))
    forged_record = forged["records"][0]
    forged_excerpt = "Texto manipulado con combustible."
    forged_record["excerpt"] = forged_excerpt
    forged_receipt = forged_record["review"]["receipt"]
    forged_receipt["excerpt_sha256"] = hashlib.sha256(forged_excerpt.encode("utf-8")).hexdigest()
    forged_receipt["candidate_content_sha256"] = candidate_content_sha256(forged_record)
    # A contributor can recalculate every local receipt field and file hash,
    # but cannot replace the externally supplied pin.
    index_path.write_text(json.dumps(forged), encoding="utf-8")
    with pytest.raises(EvidenceIndexError, match="no coincide"):
        EvidenceIndex(index_path)


@pytest.mark.parametrize(
    ("field", "value"),
    [("owner_id", "contributor"), ("approved_at", "2026-99-99T00:00:00Z")],
)
def test_unknown_owner_or_invalid_approval_date_is_not_approved_even_with_pin(
    field: str, value: str, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    report = next(row for row in payload["records"] if row["id"] == "report-approved")
    report["review"][field] = value
    report["review"]["receipt"][field] = value
    path = tmp_path / "untrusted-owner.json"
    _write_index(path, payload, monkeypatch)

    result = EvidenceIndex(path).search_reports("aumentó", "Aeroméxico", "2026Q2")
    assert "report-approved" not in [row["id"] for row in result["results"]]


def test_empty_runtime_index_loads_without_external_pin(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(APPROVED_INDEX_SHA256_ENV, raising=False)
    index = EvidenceIndex("config/chat/evidence/approved-index.json")
    assert index.records == []
    assert index.search_reports("combustible")["count"] == 0


def test_registry_fails_before_registering_tools_for_rehashed_forged_index(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    class Capabilities:
        enable_evidence_tools = True
        enable_route_tools = False
        enable_business_metric_tools = False

    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    payload["records"][0]["excerpt"] = "A locally rehashed forged approval."
    index_path = tmp_path / "config/chat/evidence/approved-index.json"
    index_path.parent.mkdir(parents=True)
    index_path.write_text(json.dumps(payload), encoding="utf-8")
    monkeypatch.setenv(APPROVED_INDEX_SHA256_ENV, canonical_index_sha256(
        json.loads(FIXTURE.read_text(encoding="utf-8"))
    ))

    snapshot = Snapshot(Path("tests/fixtures/chat/site"))
    snapshot.project_root = tmp_path
    with pytest.raises(EvidenceIndexError, match="no coincide"):
        ToolRegistry(snapshot, Capabilities())


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
