"""Visible News selection fills only omitted mock query dimensions."""
import pytest
from src.conversational_analytics.providers.mock import MockProvider
from src.conversational_analytics.news_query import resolve_news_query

SPECS = {"get_data_catalog": {}, "search_news": {}}
CONTEXT = {"tab": "news", "entity": "AEROMEXICO", "period": "2026M04"}

def intent(question, context=CONTEXT):
    selection, clarification = MockProvider()._select_tool(question, context, SPECS)
    assert clarification is None
    name, args = selection
    assert name == "search_news"
    return resolve_news_query(args["query"], args["start_date"], args["end_date"], args["company"])

@pytest.mark.parametrize("question", ["Muéstrame noticias", "combustible"])
def test_omitted_company_and_dates_follow_the_visible_month(question):
    result = intent(question)
    assert result["companies"] == ["Aeroméxico"]
    assert (result["start_date"], result["end_date"]) == ("2026-04-01", "2026-04-30")

def test_explicit_airline_and_date_override_conflicting_visible_selection():
    result = intent("Noticias de Volaris publicadas el 22 de julio de 2026")
    assert result["companies"] == ["Volaris"]
    assert result["start_date"] == result["end_date"] == "2026-07-22"

def test_explicit_company_retains_the_omitted_visible_month():
    result = intent("Noticias de Viva")
    assert result["companies"] == ["Viva"]
    assert result["start_date"] == "2026-04-01"

def test_explicit_connect_is_never_replaced_by_the_parent():
    assert intent("Noticias de Aeroméxico Connect")["companies"] == ["Aeroméxico Connect"]

def test_explicit_all_companies_is_not_restricted_by_the_visible_airline():
    assert intent("Noticias de todas las aerolíneas")["companies"] == []

def test_non_news_tab_does_not_supply_a_metric_period_to_news():
    result = intent("Muéstrame noticias", {**CONTEXT, "tab": "economy"})
    assert result["companies"] == []
    assert result["start_date"] is None and result["end_date"] is None

def test_an_unsupported_explicit_date_still_requires_clarification():
    with pytest.raises(ValueError):
        intent("Noticias después de abril de 2026")
