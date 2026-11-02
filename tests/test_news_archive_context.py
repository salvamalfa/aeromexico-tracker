"""The complete news archive has no implicit global-quarter publication cut."""

from src.conversational_analytics.providers.mock import _news_arguments


def test_unfiltered_archive_does_not_invent_publication_dates():
    arguments = _news_arguments("Muestra las noticias", {"tab": "news", "period": "", "entity": "INDUSTRY"})
    assert arguments["start_date"] is None
    assert arguments["end_date"] is None
    assert arguments["company"] is None


def test_explicit_october_dates_survive_the_selected_financial_quarter():
    question = "Noticias publicadas entre 2026-10-01 y 2026-10-31"
    arguments = _news_arguments(question, {"tab": "news", "period": "2026Q3", "entity": "INDUSTRY"})
    assert arguments["query"] == question
    # The tool's query resolver, rather than the financial selection, owns
    # explicit dates in the question.
    from src.conversational_analytics.news_query import resolve_news_query

    resolved = resolve_news_query(
        arguments["query"], arguments["start_date"], arguments["end_date"], arguments["company"]
    )
    assert resolved["start_date"] == "2026-10-01"
    assert resolved["end_date"] == "2026-10-31"
