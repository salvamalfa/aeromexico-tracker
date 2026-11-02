"""Every explicit subject is required; aliases within one subject are alternatives."""

import pytest

from src.conversational_analytics.news_query import news_match, resolve_news_query


@pytest.mark.parametrize("identifier", ["T2", "T 2", "T-2"])
def test_identifier_and_airport_are_both_required_and_share_normalization(identifier):
    intent = resolve_news_query(f"noticias de {identifier} del AICM")
    assert news_match(intent, "Nuevos horarios en AICM", "Cambio general", [], []) == 0
    assert news_match(intent, "Acceso a T 2 en el AICM", "Cambio de acceso", [], []) > 0
    assert news_match(intent, "Acceso a T2 en AIFA", "Cambio de acceso", [], []) == 0


def test_distinct_topics_are_required_but_their_aliases_are_alternatives():
    intent = resolve_news_query("noticias de TRÁFICO y capacidad de Viva")
    assert news_match(intent, "Viva ajusta oferta", "Menos pasajeros y asientos", ["Viva"], ["capacity"]) > 0
    assert news_match(intent, "Viva ajusta oferta", "Oferta de asientos", ["Viva"], ["capacity"]) == 0


def test_free_keywords_are_conjunctive_and_explicit_airlines_are_a_union():
    intent = resolve_news_query("noticias de Viva y Volaris sobre motores Pratt Whitney")
    for airline in ("Viva", "Volaris"):
        assert news_match(intent, "Motores Pratt & Whitney", "Inspecciones", [airline], ["fleet"]) > 0
    assert news_match(intent, "Motores Pratt", "Inspecciones", ["Viva"], ["fleet"]) == 0
    assert news_match(intent, "Motores Pratt Whitney", "Inspecciones", ["Aeroméxico"], ["fleet"]) == 0
