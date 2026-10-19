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


@pytest.mark.parametrize(
    "noun",
    [
        "crédito",
        "créditos",
        "pensiones",
        "pensamiento",
        "opinión",
        "opiniones",
        "consideraciones",
        "estimaciones",
        "esperanza",
        "parecido",
        "creído",
    ],
)
def test_cognitive_stem_nouns_cannot_hide_a_relative_period(noun):
    with pytest.raises(ValueError):
        resolve_news_query(f"Busca noticias publicadas en 2026-07 sobre por qué el {noun} que salió en 2T26")


@pytest.mark.parametrize(
    "verb",
    [
        "crees",
        "creerías",
        "creías",
        "creí",
        "creyeron",
        "piensas",
        "pensaste",
        "opinas",
        "consideraron",
        "estimarían",
        "supones",
        "supusieron",
        "supondrías",
        "esperabas",
        "parecía",
        "parezcan",
    ],
)
def test_admitted_finite_cognitive_forms_keep_report_quarter_in_subject(verb):
    intent = resolve_news_query(
        f"Busca noticias publicadas en 2026-07 sobre por qué {verb} que cayeron resultados en 2T26"
    )
    assert "2t26" in intent["terms"]
    assert (intent["start_date"], intent["end_date"]) == ("2026-07-01", "2026-07-31")


@pytest.mark.parametrize("phrase", ["se ha creído", "ha parecido", "habían pensado", "hemos estimado"])
def test_cognitive_participle_requires_its_auxiliary(phrase):
    intent = resolve_news_query(
        f"Busca noticias publicadas en 2026-07 sobre por qué {phrase} que cayeron resultados en 2T26"
    )
    assert "2t26" in intent["terms"]
    assert (intent["start_date"], intent["end_date"]) == ("2026-07-01", "2026-07-31")


@pytest.mark.parametrize(
    "noun",
    [
        "el parecer",
        "la espera",
        "la estima",
        "el pienso",
        "mi parecer",
        "su estima",
        "esa espera",
        'el "parecer"',
    ],
)
def test_nominal_context_does_not_absorb_relative_quarter(noun):
    with pytest.raises(ValueError):
        resolve_news_query(f"Busca noticias publicadas en 2026-07 sobre por qué {noun} que salió en 2T26")


@pytest.mark.parametrize(
    "pronoun,verb", [("él", "espera"), ("tú", "estimas"), ("él", "cree"), ("tú", "piensas")]
)
def test_explicit_personal_pronoun_keeps_cognitive_prelude_and_original_search_terms(pronoun, verb):
    intent = resolve_news_query(
        f"Busca noticias publicadas en 2026-07 sobre por qué {pronoun} {verb} que cayeron resultados en 2T26"
    )
    assert "2t26" in intent["terms"]
    assert "usted" not in intent["terms"]
    assert (intent["start_date"], intent["end_date"]) == ("2026-07-01", "2026-07-31")


@pytest.mark.parametrize("noun", ["el nuevo parecer", "la antigua espera", "mi gran estima"])
def test_modified_nominal_phrase_cannot_be_a_cognitive_prelude(noun):
    with pytest.raises(ValueError):
        resolve_news_query(f"Busca noticias publicadas en 2026-07 sobre por qué {noun} que salió en 2T26")


@pytest.mark.parametrize(
    "actor,verb", [("los analistas", "creen"), ("Aeroméxico", "supone"), ("el experto", "cree")]
)
def test_admitted_cognitive_subjects_keep_the_report_topic(actor, verb):
    intent = resolve_news_query(
        f"Busca noticias publicadas en 2026-07 sobre por qué {actor} {verb} que cayeron resultados en 2T26"
    )
    assert "2t26" in intent["terms"]
    assert (intent["start_date"], intent["end_date"]) == ("2026-07-01", "2026-07-31")


@pytest.mark.parametrize(
    "actor,company",
    [
        ("AMXConnect", "Aeroméxico Connect"),
        ("AeroméxicoConnect", "Aeroméxico Connect"),
        ("Viva Aerobus", "Viva"),
    ],
)
def test_cognitive_company_subject_reuses_existing_entity_aliases(actor, company):
    intent = resolve_news_query(
        f"Busca noticias publicadas en 2026-07 sobre por qué {actor} cree que cayeron resultados en 2T26"
    )
    assert intent["companies"] == [company]
    assert "2t26" in intent["terms"]
    assert (intent["start_date"], intent["end_date"]) == ("2026-07-01", "2026-07-31")


@pytest.mark.parametrize(
    "actor",
    [
        "un analista",
        "una analista",
        "unos analistas",
        "unas analistas",
        "la experta",
        "una directiva",
        "las inversoras",
        "unas pasajeras",
        "un medio",
        "una fuente",
        "un inversor",
    ],
)
def test_existing_cognitive_subject_classes_admit_indefinites_gender_and_number(actor):
    intent = resolve_news_query(
        f"Busca noticias publicadas en 2026-07 sobre por qué {actor} cree que cayeron resultados en 2T26"
    )
    assert "2t26" in intent["terms"]
    assert (intent["start_date"], intent["end_date"]) == ("2026-07-01", "2026-07-31")


@pytest.mark.parametrize("noun", ["un parecer", "una espera", "unas estimas"])
def test_indefinite_article_does_not_admit_nominal_homographs(noun):
    with pytest.raises(ValueError):
        resolve_news_query(f"Busca noticias publicadas en 2026-07 sobre por qué {noun} que salió en 2T26")


@pytest.mark.parametrize(
    "actor,companies",
    [
        ("el Grupo Aeroméxico", ["Aeroméxico"]),
        ("la AeroméxicoConnect", ["Aeroméxico Connect"]),
        ("la Viva Aerobus", ["Viva"]),
        ("el AMX", ["Aeroméxico"]),
        ("la Volaris", ["Volaris"]),
        ("analistas", []),
    ],
)
def test_optional_article_applies_to_existing_company_aliases_and_subject_roles(actor, companies):
    intent = resolve_news_query(
        f"Busca noticias publicadas en 2026-07 sobre por qué {actor} cree que cayeron resultados en 2T26"
    )
    assert intent["companies"] == companies
    assert "2t26" in intent["terms"]
    assert (intent["start_date"], intent["end_date"]) == ("2026-07-01", "2026-07-31")


@pytest.mark.parametrize(
    "label",
    ["2T26", "2-T26", "2 T de 2026", "2Q del 2026", "T2 de 2026", "Q2/2026", "2026-Q2", "FY26 Q2", "Q2 FY26", "2T FY2026"],
)
def test_topic_quarter_variants_keep_only_the_explicit_publication_month(label):
    intent = resolve_news_query(f"noticias publicadas en 2026-07 sobre resultados en {label}")
    assert (intent["start_date"], intent["end_date"]) == ("2026-07-01", "2026-07-31")


@pytest.mark.parametrize("label", ["2-T26", "T2 de 2026", "Q2 FY26", "2026-Q2"])
@pytest.mark.parametrize("cue", ["publicados", "salieron", "aparecieron", "difundieron", "emitieron", "divulgaron"])
def test_topic_release_cues_keep_separate_quarter_constraints_visible(label, cue):
    with pytest.raises(ValueError, match="notación trimestral"):
        resolve_news_query(f"noticias publicadas en 2026-07 sobre resultados que {cue} en {label}")
