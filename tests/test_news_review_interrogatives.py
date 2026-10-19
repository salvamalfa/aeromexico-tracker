"""Interrogative and relative clauses in bounded Spanish news search."""

import pytest

from src.conversational_analytics.news_query import resolve_news_query


@pytest.mark.parametrize(
    "prefix", ["por qué", "para qué", "a qué", "de qué", "con qué", "en qué", "(¿por qué", "¿por qué"]
)
def test_compound_interrogative_prefix_is_part_of_the_topic(prefix):
    intent = resolve_news_query(
        f"Busca noticias publicadas en 2026-07 sobre {prefix} cayeron los resultados en 2T26"
    )
    assert "2t26" in intent["terms"]
    assert (intent["start_date"], intent["end_date"]) == ("2026-07-01", "2026-07-31")


@pytest.mark.parametrize("period", ["2T26", "agosto de 2026"])
def test_interrogative_prefix_does_not_hide_later_relative_publication_clause(period):
    with pytest.raises(ValueError):
        resolve_news_query(
            f"Busca noticias publicadas en 2026-07 sobre por qué cayeron los resultados que salieron en {period}"
        )


@pytest.mark.parametrize(
    "prelude",
    [
        "crees que",
        "piensas que",
        "opinas que",
        "consideras que",
        "creerías que",
        "supones que",
        "crees que piensas que",
    ],
)
def test_interrogative_cognitive_prelude_keeps_its_complement_in_the_topic(prelude):
    intent = resolve_news_query(
        f"Busca noticias publicadas en 2026-07 sobre por qué {prelude} cayeron los resultados en 2T26"
    )
    assert "2t26" in intent["terms"]
    assert (intent["start_date"], intent["end_date"]) == ("2026-07-01", "2026-07-31")


@pytest.mark.parametrize("period", ["2T26", "agosto de 2026"])
def test_cognitive_prelude_does_not_hide_a_later_publication_relative(period):
    with pytest.raises(ValueError):
        resolve_news_query(
            f"Busca noticias publicadas en 2026-07 sobre por qué crees que cayeron los resultados que salieron en {period}"
        )


@pytest.mark.parametrize(
    "prelude",
    [
        "se cree que",
        "crees tú que",
        "tú crees que",
        "no se cree que",
        "se cree realmente que",
        "según los analistas se cree que",
        "crees, tú, que",
        "ustedes consideran que",
        "ella piensa que",
        "ya no supones tú que",
        "se ha creído que",
        "los expertos, realmente, creen que",
    ],
)
def test_cognitive_prelude_accepts_local_pronouns_clitics_and_modifiers(prelude):
    intent = resolve_news_query(
        f"Busca noticias publicadas en 2026-07 sobre por qué {prelude} cayeron los resultados en 2T26"
    )
    assert "2t26" in intent["terms"]
    assert (intent["start_date"], intent["end_date"]) == ("2026-07-01", "2026-07-31")


@pytest.mark.parametrize("period", ["2T26", "agosto de 2026"])
def test_modified_cognitive_prelude_cannot_skip_another_relative_clause(period):
    with pytest.raises(ValueError):
        resolve_news_query(
            f"Busca noticias publicadas en 2026-07 sobre por qué se cree que cayeron los resultados que salieron en {period}"
        )


@pytest.mark.parametrize(
    "clause",
    [
        "los analistas piensan en noticias que salieron",
        "los analistas consideran noticias que salieron",
        "los analistas consideran las noticias que salieron",
        "los expertos opinan sobre notas que salieron",
        "los analistas esperan noticias que salieron",
    ],
)
@pytest.mark.parametrize("period", ["2T26", "agosto de 2026"])
def test_cognitive_prelude_does_not_consume_a_nominal_object_relative(clause, period):
    with pytest.raises(ValueError):
        resolve_news_query(f"Busca noticias publicadas en 2026-07 sobre por qué {clause} en {period}")


@pytest.mark.parametrize("modifier", ["de verdad", "en realidad", "tal vez"])
def test_fixed_postverbal_adverbs_remain_part_of_cognitive_prelude(modifier):
    intent = resolve_news_query(
        f"Busca noticias publicadas en 2026-07 sobre por qué crees {modifier} que cayeron resultados en 2T26"
    )
    assert "2t26" in intent["terms"]
    assert (intent["start_date"], intent["end_date"]) == ("2026-07-01", "2026-07-31")


@pytest.mark.parametrize("adverb", ["quizá", "quizás", "quiza", "quizas"])
def test_singular_and_plural_quiza_adverb_family_stays_in_cognitive_prelude(adverb):
    intent = resolve_news_query(
        f"Busca noticias publicadas en 2026-07 sobre por qué crees {adverb} que cayeron resultados en 2T26"
    )
    assert "2t26" in intent["terms"]
    assert (intent["start_date"], intent["end_date"]) == ("2026-07-01", "2026-07-31")


@pytest.mark.parametrize("period", ["2T26", "agosto de 2026"])
def test_quiza_does_not_hide_a_later_publication_relative(period):
    with pytest.raises(ValueError):
        resolve_news_query(
            f"Busca noticias publicadas en 2026-07 sobre por qué crees quizá que cayeron resultados que salieron en {period}"
        )
