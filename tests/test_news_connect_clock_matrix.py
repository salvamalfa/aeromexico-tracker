"""Specific operators and undocumented worded times cannot broaden into brand/day evidence."""

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
    "query",
    [
        "noticias de Aeroméxico Connect",
        "noticias de AEROMEXICO   CONNECT",
        "noticias de Aeromexico_Connect",
        "noticias de AeromexicoConnect",
        "noticias de AMX Connect",
        "noticias de AMX-Connect",
        "noticias de Connect sobre combustible",
    ],
)
def test_connect_request_does_not_include_generic_aeromexico_records(query):
    result = EvidenceIndex(ROOT / "config/chat/evidence/approved-index.json").search_news(query)
    assert result["filters"]["companies"] == ["Aeroméxico Connect"]
    assert result["count"] == 0 and result["results"] == []


@pytest.mark.parametrize("company", [None, "Aeroméxico Connect", "AEROMEXICO_CONNECT", "Connect"])
def test_connect_structured_aliases_remain_operator_specific(company):
    result = EvidenceIndex(ROOT / "config/chat/evidence/approved-index.json").search_news(
        "noticias de Aeroméxico Connect", company=company
    )
    assert result["filters"]["companies"] == ["Aeroméxico Connect"] and result["count"] == 0


@pytest.mark.parametrize(
    "query,company",
    [("noticias de Aeroméxico Connect", "Aeroméxico"), ("noticias de Aeroméxico", "Aeroméxico Connect")],
)
def test_parent_and_connect_arguments_cannot_replace_each_other(query, company):
    with pytest.raises(ValueError, match="no coincide"):
        resolve_news_query(query, company=company)


def test_parent_and_connect_are_separate_in_an_explicit_union():
    result = resolve_news_query("noticias de Aeroméxico y Aeroméxico Connect")
    assert set(result["companies"]) == {"Aeroméxico", "Aeroméxico Connect"}
    result = EvidenceIndex(ROOT / "config/chat/evidence/approved-index.json").search_news(
        "noticias de Aeroméxico"
    )
    assert result["count"] == 2 and all(r["companies"] == ["Aeroméxico"] for r in result["results"])


@pytest.mark.parametrize(
    "suffix",
    [
        "a las nueve",
        "a primera hora",
        "a las cero horas",
        "a las cero",
        "a las 9am",
        "a las 9p.m.",
        "a las 09h30",
        "a las tres y media",
        "a la una",
        "a las 9",
        "a mediodía",
        "al mediodía",
        "a medianoche",
        "por la tarde",
        "en la noche",
        "de madrugada",
        "antes de las once",
        "después de las veintitrés",
    ],
)
@pytest.mark.parametrize(
    "bounds", [(None, None), ("2026-07-15", None), (None, "2026-07-15"), ("2026-07-15", "2026-07-15")]
)
def test_worded_publication_times_require_clarification_with_any_argument_mask(suffix, bounds):
    with pytest.raises(ValueError, match="hora no está documentada"):
        resolve_news_query("noticias del 15 de julio de 2026 " + suffix, *bounds)


def test_non_time_reference_to_airlines_is_not_mistaken_for_an_hour():
    result = EvidenceIndex(ROOT / "config/chat/evidence/approved-index.json").search_news(
        "noticias del 15 de julio de 2026 sobre combustible a las aerolíneas"
    )
    assert [r["id"] for r in result["results"]] == ["flightglobal-aeromexico-q2-2026-07-15"]
