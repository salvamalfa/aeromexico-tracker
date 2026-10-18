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
def test_shared_card_retains_company_and_topic_filters_from_every_source(approved_index, reverse):
    rows = grouped_records(approved_index)
    cards = project(rows[::-1] if reverse else rows)
    assert len(cards) == 1
    assert cards[0]["companies"] == ["Aeroméxico", "Aeroméxico Connect"]
    assert cards[0]["topics"] == ["capacidad", "combustible"]
    assert len(cards[0]["sources"]) == 2
    approved_index.records = rows[::-1] if reverse else rows
    result = approved_index.search_news("noticias de Aeroméxico Connect en julio de 2026")
    assert result["count"] == 1
    assert result["matching_ids"] == [cards[0]["id"]]
    assert "Aeroméxico Connect" in cards[0]["companies"]


@pytest.mark.parametrize("reverse", [False, True])
def test_secondary_story_source_cannot_bypass_company_validation(approved_index, reverse):
    rows = grouped_records(approved_index)
    rows[1]["companies"] = ["Unknown airline"]
    with pytest.raises(ValueError, match="Unknown company"):
        project(rows[::-1] if reverse else rows)


@pytest.mark.parametrize(
    "notation", ["2026Q2", "Q2 2026", "2T26", "2T2026", "2026T2", "Q22026", "Q2", "2026Q5", "0T26"]
)
@pytest.mark.parametrize("bounds", [{}, {"start_date": "2026-04-01", "end_date": "2026-06-30"}])
def test_compact_publication_quarter_never_becomes_an_unbounded_or_topic_search(notation, bounds):
    with pytest.raises(ValueError, match="notación trimestral"):
        resolve_news_query(f"noticias publicadas en {notation}", **bounds)


def test_explicit_publication_quarter_dates_keep_july_outside_results(approved_index):
    result = approved_index.search_news("noticias publicadas entre 2026-04-01 y 2026-06-30")
    assert result["count"] == 1
    assert [row["published_at"] for row in result["results"]] == ["2026-04-30"]
