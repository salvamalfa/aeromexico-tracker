"""Entity intent and exact named dates cannot be silently replaced by tool args."""

from pathlib import Path
import pytest
from src.conversational_analytics.news_query import resolve_news_query
from src.conversational_analytics.evidence_index import EvidenceIndex

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def pin(monkeypatch):
    monkeypatch.setenv(
        "CHAT_EVIDENCE_APPROVED_INDEX_SHA256",
        "1cd0455ac1944849d567c96f7147c3f393d17333dac2c28b70459e4f7887334f",
    )


@pytest.mark.parametrize(
    "query,company,expected",
    [
        ("noticias de Aeroméxico", None, ["Aeroméxico"]),
        ("noticias de Aeroméxico", "Aeromexico", ["Aeroméxico"]),
        ("noticias de AMX", "AEROMEXICO", ["Aeroméxico"]),
        ("noticias de Viva", "Viva Aerobus", ["Viva"]),
        ("noticias de Viva Aerobús", "VIVA_AEROBUS", ["Viva"]),
        ("noticias de Volaris", "VOLARIS", ["Volaris"]),
        ("noticias sobre combustible", "Aeroméxico", ["Aeroméxico"]),
        ("noticias sobre combustible", "Viva Aerobus", ["Viva"]),
        ("noticias sobre combustible", "Volaris", ["Volaris"]),
        ("noticias sobre combustible", "Future Air", ["Future Air"]),
        ("noticias de Aeroméxico y Volaris", None, ["Aeroméxico", "Volaris"]),
    ],
)
def test_matching_airline_aliases_and_multi_airline_queries_preserve_intent(query, company, expected):
    assert resolve_news_query(query, company=company)["companies"] == expected


@pytest.mark.parametrize("query_company", ["Aeroméxico", "Viva", "Volaris"])
@pytest.mark.parametrize("argument_company", ["Aeroméxico", "Viva Aerobus", "Volaris"])
def test_every_explicit_airline_must_agree_with_the_structured_argument(query_company, argument_company):
    canonical = "Viva" if argument_company == "Viva Aerobus" else argument_company
    index = EvidenceIndex(ROOT / "config/chat/evidence/approved-index.json")
    if query_company == canonical:
        result = index.search_news(f"noticias de {query_company}", company=argument_company)
        assert result["filters"]["companies"] == [canonical]
        assert all(canonical in row["companies"] for row in result["results"])
    else:
        with pytest.raises(ValueError, match="no coincide"):
            index.search_news(f"noticias de {query_company}", company=argument_company)


@pytest.mark.parametrize("company", ["Aeroméxico", "Viva Aerobus", "Volaris"])
def test_single_company_argument_cannot_narrow_an_explicit_multiple_company_request(company):
    with pytest.raises(ValueError, match="no coincide"):
        resolve_news_query("noticias de Aeroméxico y Volaris", company=company)


@pytest.mark.parametrize(
    "bounds", [(None, None), ("2026-07-15", None), (None, "2026-07-15"), ("2026-07-15", "2026-07-15")]
)
def test_named_calendar_day_returns_only_that_day_not_the_entire_month(bounds):
    result = EvidenceIndex(ROOT / "config/chat/evidence/approved-index.json").search_news(
        "noticias del 15 de julio de 2026", start_date=bounds[0], end_date=bounds[1]
    )
    assert result["filters"]["start_date"] == result["filters"]["end_date"] == "2026-07-15"
    assert [r["id"] for r in result["results"]] == ["flightglobal-aeromexico-q2-2026-07-15"]


@pytest.mark.parametrize(
    "bounds", [(None, None), ("2026-07-01", None), (None, "2026-07-31"), ("2026-07-01", "2026-07-31")]
)
@pytest.mark.parametrize(
    "question",
    [
        "noticias del quince de julio de 2026",
        "noticias del primero de julio de 2026",
        "noticias del 1.º de julio de 2026",
        "noticias del 15 al 22 de julio de 2026",
        "noticias de julio 15 de 2026",
        "noticias del 15/julio/2026",
        "noticias del 15/07/2026",
        "noticias del 07-15-2026",
        "noticias de mediados de julio de 2026",
        "noticias de finales de 2026",
        "noticias del 15 de julio",
        "noticias del 32 de julio de 2026",
        "noticias del 29 de febrero de 1900",
    ],
)
def test_unsupported_or_invalid_named_day_precision_is_never_widened_by_arguments(question, bounds):
    with pytest.raises(ValueError):
        resolve_news_query(question, *bounds)


@pytest.mark.parametrize("bounds", [("2026-07-01", None), (None, "2026-07-31"), ("2026-07-01", "2026-07-31")])
def test_monthly_arguments_cannot_replace_an_exact_named_day(bounds):
    with pytest.raises(ValueError, match="no coinciden"):
        resolve_news_query("noticias del 15 de julio de 2026", *bounds)


def test_weekday_agrees_with_exact_date_and_does_not_become_a_keyword():
    result = EvidenceIndex(ROOT / "config/chat/evidence/approved-index.json").search_news(
        "noticias del miércoles 15 de julio de 2026"
    )
    assert [r["id"] for r in result["results"]] == ["flightglobal-aeromexico-q2-2026-07-15"]


@pytest.mark.parametrize(
    "bounds", [(None, None), ("2026-07-15", None), (None, "2026-07-15"), ("2026-07-15", "2026-07-15")]
)
@pytest.mark.parametrize(
    "question",
    [
        "noticias del lunes 15 de julio de 2026",
        "noticias del miércoles",
        "noticias de los lunes de julio de 2026",
    ],
)
def test_weekdays_cannot_override_or_infer_an_exact_publication_date(question, bounds):
    with pytest.raises(ValueError):
        resolve_news_query(question, *bounds)


@pytest.mark.parametrize(
    "question",
    [
        "noticias del 2026-07-15T09:30Z",
        "noticias del 2026-07-15 09:30",
        "noticias del 15 de julio de 2026 a las 09:30",
    ],
)
def test_unsupported_hour_precision_is_not_widened_to_a_day_or_year(question):
    with pytest.raises(ValueError, match="hora no está documentada"):
        resolve_news_query(question)
