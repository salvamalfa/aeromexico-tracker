"""Regression coverage for the exact-head review, without changing approved inputs."""

from copy import deepcopy

import pytest

from src.conversational_analytics.evidence_index import EvidenceIndex
from src.conversational_analytics.news_projection import project
from src.conversational_analytics.news_query import resolve_news_query


@pytest.fixture
def approved_index(monkeypatch):
    monkeypatch.setenv(
        "CHAT_EVIDENCE_APPROVED_INDEX_SHA256",
        "1cd0455ac1944849d567c96f7147c3f393d17333dac2c28b70459e4f7887334f",
    )
    return EvidenceIndex("config/chat/evidence/approved-index.json")


def grouped_records(index):
    original = next(row for row in index.records if row.get("kind") == "news")
    result = []
    for identifier, companies, topics in [
        ("parent", ["Aeroméxico"], ["combustible"]),
        ("operator", ["Aeroméxico Connect"], ["capacidad"]),
    ]:
        row = deepcopy(original)
        row.update(
            id=identifier,
            story_id="shared",
            companies=companies,
            topics=topics,
            published_at="2026-07-01",
            review_status="owner_approved",
        )
        row["source"]["url"] = f"https://www.flightglobal.com/regression-{identifier}"
        result.append(row)
    return result


@pytest.mark.parametrize("reverse", [False, True])
def test_shared_card_retains_topics_with_consistent_company_attribution(approved_index, reverse):
    rows = grouped_records(approved_index)
    rows[1]["companies"] = ["Aeroméxico"]
    cards = project(rows[::-1] if reverse else rows)
    assert len(cards) == 1
    assert cards[0]["companies"] == ["Aeroméxico"]
    assert cards[0]["topics"] == ["capacidad", "combustible"]
    assert len(cards[0]["sources"]) == 2
    approved_index.records = rows[::-1] if reverse else rows
    result = approved_index.search_news("noticias de Aeroméxico sobre capacidad en julio de 2026")
    assert result["count"] == 1
    assert result["matching_ids"] == [cards[0]["id"]]
    assert "Aeroméxico" in cards[0]["companies"]


@pytest.mark.parametrize("reverse", [False, True])
def test_conflicting_story_operators_fail_closed_in_archive_and_chat(approved_index, reverse):
    rows = grouped_records(approved_index)
    rows = rows[::-1] if reverse else rows
    with pytest.raises(ValueError, match="Conflicting company attribution"):
        project(rows)
    approved_index.records = rows
    with pytest.raises(ValueError, match="Conflicting company attribution"):
        approved_index.search_news("noticias de Aeroméxico Connect sobre combustible")


@pytest.mark.parametrize("reverse", [False, True])
def test_secondary_story_source_cannot_bypass_company_validation(approved_index, reverse):
    rows = grouped_records(approved_index)
    rows[1]["companies"] = ["Unknown airline"]
    with pytest.raises(ValueError, match="Unknown company"):
        project(rows[::-1] if reverse else rows)


@pytest.mark.parametrize(
    "notation",
    [
        "2026Q2",
        "2026 Q2",
        "2026-Q2",
        "Q2 2026",
        "Q2 de 2026",
        "Q22026",
        "Q2/2026",
        "2T26",
        "2Q26",
        "2Q2026",
        "2 T26",
        "2T2026",
        "2026T2",
        "2026 T2",
        "2026-T2",
        "T2 2026",
        "T2 de 2026",
        "T22026",
        "T2/2026",
        "2026 de T2",
        "2026 del T2",
        "T2 del 2026",
        "Q2",
        "2026Q5",
        "0T26",
    ],
)
@pytest.mark.parametrize("bounds", [{}, {"start_date": "2026-04-01", "end_date": "2026-06-30"}])
def test_compact_publication_quarter_never_becomes_an_unbounded_or_topic_search(notation, bounds):
    with pytest.raises(ValueError, match="notación trimestral"):
        resolve_news_query(f"noticias publicadas en {notation}", **bounds)


def test_explicit_publication_quarter_dates_keep_july_outside_results(approved_index):
    result = approved_index.search_news("noticias publicadas entre 2026-04-01 y 2026-06-30")
    assert result["count"] == 1
    assert [row["published_at"] for row in result["results"]] == ["2026-04-30"]


@pytest.mark.parametrize(
    "question,term",
    [
        ("noticias de la T2 del AICM", "t2"),
        ("noticias de T1 y T2", "t1"),
        ("noticias publicadas en T2 del AICM", "t2"),
        ("noticias sobre Q400", "q400"),
        ("noticias de Q400 en 2026", "q400"),
        ("noticias de la T2 del AICM en 2026", "t2"),
        ("noticias de la terminal T2 en 2026", "t2"),
    ],
)
def test_airport_terminals_and_aircraft_models_remain_searchable(question, term):
    intent = resolve_news_query(question)
    assert term in intent["terms"]


@pytest.mark.parametrize("question", ["noticias de T2 en 2026", "noticias de 2026 correspondientes a T2"])
def test_ambiguous_year_and_t_label_requires_explicit_dates(question):
    with pytest.raises(ValueError, match="notación trimestral"):
        resolve_news_query(question)
