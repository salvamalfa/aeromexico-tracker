"""Calendar meaning must survive every nullable tool-argument combination."""

from __future__ import annotations

import pytest

from src.conversational_analytics.news_query import resolve_news_query

BOUNDS = [
    (None, None),
    ("2026-07-01", None),
    (None, "2026-07-31"),
    ("2026-07-01", "2026-07-31"),
    ("2026-06-01", "2026-06-30"),
]


@pytest.mark.parametrize("bounds", BOUNDS)
@pytest.mark.parametrize(
    "question",
    [
        "noticias del último mes sobre combustible",
        "noticias de hace 3 meses sobre combustible",
        "noticias de hace tres meses sobre combustible",
        "noticias del mes anterior sobre combustible",
        "noticias de este año sobre combustible",
        "noticias de ayer sobre combustible",
    ],
)
def test_relative_meaning_is_never_overridden_by_nullable_or_inferred_bounds(question, bounds):
    with pytest.raises(ValueError, match="fechas explícitas"):
        resolve_news_query(question, *bounds)


@pytest.mark.parametrize("bounds", BOUNDS)
@pytest.mark.parametrize(
    "question",
    [
        "noticias de diciembre de 2025 a 2026",
        "noticias de diciembre de 2025 y 2026",
        "noticias de 2025-12 a 2026",
        "noticias de 2025-12-01 a 2026",
        "noticias de 2026-13",
        "noticias de 2026-1-1",
        "noticias de enero sin año",
    ],
)
def test_invalid_or_mixed_query_dates_are_not_hidden_by_valid_arguments(question, bounds):
    with pytest.raises(ValueError):
        resolve_news_query(question, *bounds)


ABSOLUTE = [
    ("noticias en julio de 2026", "2026-07-01", "2026-07-31"),
    ("noticias del 15 de julio de 2026", "2026-07-15", "2026-07-15"),
    ("noticias del día 15 julio 2026", "2026-07-15", "2026-07-15"),
    ("noticias del 1 de enero de 1900", "1900-01-01", "1900-01-01"),
    ("noticias del 15 de julio de 2026 al 22 de julio de 2026", "2026-07-15", "2026-07-22"),
    ("noticias publicadas en 1900", "1900-01-01", "1900-12-31"),
    ("noticias publicadas en 2100", "2100-01-01", "2100-12-31"),
    ("noticias el 1999-12-31", "1999-12-31", "1999-12-31"),
    ("noticias en 2099-12", "2099-12-01", "2099-12-31"),
    ("noticias de diciembre de 2025 a enero de 2026", "2025-12-01", "2026-01-31"),
    ("noticias en 2026", "2026-01-01", "2026-12-31"),
    ("noticias entre 2025 y 2026", "2025-01-01", "2026-12-31"),
    ("noticias en 2026-07", "2026-07-01", "2026-07-31"),
    ("noticias el 2026-07-15", "2026-07-15", "2026-07-15"),
    ("noticias entre 2026-04-01 y 2026-07-31", "2026-04-01", "2026-07-31"),
    ("noticias desde 2026-07-01", "2026-07-01", None),
    ("noticias hasta 2026-06-30", None, "2026-06-30"),
]


@pytest.mark.parametrize("question,start,end", ABSOLUTE)
@pytest.mark.parametrize("mask", [0, 1, 2, 3])
def test_absolute_meaning_is_complete_and_preserved_with_any_nullable_mask(question, start, end, mask):
    result = resolve_news_query(question, start if mask & 1 else None, end if mask & 2 else None)
    assert (result["start_date"], result["end_date"]) == (start, end)
    assert result["date_basis"] == "publication"


@pytest.mark.parametrize(
    "bounds",
    [
        ("2026-06-01", None),
        (None, "2026-08-31"),
        ("2026-06-01", "2026-06-30"),
        ("2026-07-02", "2026-07-31"),
    ],
)
def test_inconsistent_caller_bounds_cannot_silently_change_an_explicit_month(bounds):
    with pytest.raises(ValueError, match="no coinciden"):
        resolve_news_query("noticias publicadas en julio de 2026", *bounds)


@pytest.mark.parametrize(
    "question,bounds",
    [
        ("noticias desde 2026-07-01", (None, "2026-07-31")),
        ("noticias hasta 2026-06-30", ("2026-04-01", None)),
        ("noticias entre julio de 2026", (None, None)),
    ],
)
def test_open_ended_text_cannot_be_narrowed_by_an_unstated_opposite_bound(question, bounds):
    with pytest.raises(ValueError):
        resolve_news_query(question, *bounds)


@pytest.mark.parametrize("bounds", BOUNDS)
def test_keyword_only_query_preserves_valid_structured_date_arguments(bounds):
    result = resolve_news_query("noticias sobre combustible", *bounds)
    assert (result["start_date"], result["end_date"]) == bounds


@pytest.mark.parametrize(
    "bounds",
    [
        ("2026-08-01", "2026-07-01"),
        ("2026-13-01", None),
        (None, "2026-02-30"),
        ("20260701", None),
        ("", None),
    ],
)
def test_structured_bounds_are_validated_independently_of_query_text(bounds):
    with pytest.raises(ValueError):
        resolve_news_query("noticias sobre combustible", *bounds)


@pytest.mark.parametrize("bounds", BOUNDS)
@pytest.mark.parametrize(
    "query", ["noticias del último mes sobre combustible", "noticias de hace tres meses sobre combustible"]
)
def test_evidence_tool_enforces_relative_semantics_before_returning_records(monkeypatch, bounds, query):
    from pathlib import Path
    from src.conversational_analytics.evidence_index import EvidenceIndex

    monkeypatch.setenv(
        "CHAT_EVIDENCE_APPROVED_INDEX_SHA256",
        "1cd0455ac1944849d567c96f7147c3f393d17333dac2c28b70459e4f7887334f",
    )
    index = EvidenceIndex(Path(__file__).resolve().parents[1] / "config/chat/evidence/approved-index.json")
    with pytest.raises(ValueError, match="fechas explícitas"):
        index.search_news(query, start_date=bounds[0], end_date=bounds[1])


@pytest.mark.parametrize("bounds", BOUNDS)
@pytest.mark.parametrize(
    "query",
    [
        "noticias antes de julio de 2026",
        "noticias después de julio de 2026",
        "noticias antes de 2026-07",
        "noticias después de 2026-07-15",
        "noticias anteriores a julio de 2026",
        "noticias posteriores al 15 de julio de 2026",
        "noticias previas a julio de 2026",
        "noticias después del anuncio sobre combustible",
    ],
)
def test_directional_qualifiers_require_explicit_supported_bounds_even_with_caller_dates(query, bounds):
    with pytest.raises(ValueError, match="inicio y fin explícitos"):
        resolve_news_query(query, start_date=bounds[0], end_date=bounds[1])


@pytest.mark.parametrize("bounds", BOUNDS)
@pytest.mark.parametrize(
    "query",
    [
        "noticias a partir de abril de 2026",
        "noticias a partir del 15 de julio de 2026",
        "noticias a partir de 2026-04",
        "noticias de abril de 2026 en adelante",
        "noticias de 2026-04 en adelante",
        "noticias de 2026-04-15 en adelante",
        "noticias a contar de abril de 2026",
        "noticias de abril de 2026 en lo sucesivo",
    ],
)
def test_onward_qualifiers_are_not_narrowed_to_a_single_month(query, bounds):
    with pytest.raises(ValueError, match="inicio y fin explícitos"):
        resolve_news_query(query, start_date=bounds[0], end_date=bounds[1])
