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
        "2T de 2026",
        "2T del 2026",
        "2Q de 2026",
        "2Q del 2026",
        "2Tde2026",
        "2Qdel2026",
        "T2de26",
        "Q2de26",
        "2026delT2",
        "2026 de Q2",
        "T2del2026",
        "T 2 en 2026",
        "2026 T 2",
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
        ("noticias de Q100 en 2026", "q100"),
        ("noticias de Q200 en 2026", "q200"),
        ("noticias de Q300 en 2026", "q300"),
        ("noticias de la terminal T 2 en 2026", "t2"),
        ("noticias de la T 2 del AICM en 2026", "t2"),
        ("noticias sobre Q 400 en 2026", "q400"),
        ("noticias sobre Q-400 en 2026", "q400"),
        ("noticias de BTS T100 en 2026", "t100"),
        ("noticias de BTS T 100 en 2026", "t100"),
        ("noticias de BTS T-100 en 2026", "t100"),
    ],
)
def test_airport_terminals_and_aircraft_models_remain_searchable(approved_index, question, term):
    intent = resolve_news_query(question)
    assert term in intent["terms"]
    # None of the three approved records covers these identifiers. Losing
    # their tokens must not turn the request into every record from 2026.
    assert approved_index.search_news(question)["count"] == 0


@pytest.mark.parametrize(
    "question",
    [
        "noticias de T2 en 2026",
        "noticias de 2026 correspondientes a T2",
        "noticias de T 2 en 2026",
        "noticias de 2026 correspondientes a T 2",
    ],
)
def test_ambiguous_year_and_t_label_requires_explicit_dates(question):
    with pytest.raises(ValueError, match="notación trimestral"):
        resolve_news_query(question)


DASHES = ["-", "‐", "‑", "‒", "–", "—", "―", "−"]


@pytest.mark.parametrize("dash", DASHES)
def test_typographic_quarter_identifier_cannot_become_a_year_filter(dash):
    with pytest.raises(ValueError, match="notación trimestral"):
        resolve_news_query(f"noticias publicadas en T{dash}2 de 2026")


@pytest.mark.parametrize("dash", DASHES)
def test_typographic_aircraft_identifier_is_not_an_unfiltered_query(approved_index, dash):
    result = approved_index.search_news(f"noticias de Q{dash}400 en 2026")
    assert result["filters"]["terms"] == ["q400"]
    assert result["count"] == 0


@pytest.mark.parametrize("dash", DASHES)
def test_typographic_terminal_identifier_stays_searchable(approved_index, dash):
    result = approved_index.search_news(f"noticias de la terminal T{dash}2 en 2026")
    assert "t2" in result["filters"]["terms"]
    assert result["count"] == 0


@pytest.mark.parametrize("dash", DASHES)
def test_typographic_date_delimiters_preserve_exact_publication_range(approved_index, dash):
    result = approved_index.search_news(
        f"noticias publicadas entre 2026{dash}04{dash}01 y 2026{dash}06{dash}30"
    )
    assert (result["filters"]["start_date"], result["filters"]["end_date"]) == ("2026-04-01", "2026-06-30")
    assert [row["published_at"] for row in result["results"]] == ["2026-04-30"]


@pytest.mark.parametrize("identifier,term", [("Q.400", "q400"), ("Q_400", "q400"), ("T_2", "t2")])
def test_punctuated_identifiers_keep_a_specific_search_token(approved_index, identifier, term):
    result = approved_index.search_news(f"noticias de la terminal {identifier} en 2026")
    assert term in result["filters"]["terms"]
    assert result["count"] == 0


@pytest.mark.parametrize("separator", ["-", "/", "–", "—", "_", "."])
@pytest.mark.parametrize("letter", ["T", "Q"])
@pytest.mark.parametrize("connector", ["de", "del"])
def test_separator_before_quarter_letter_cannot_drop_the_period(separator, letter, connector):
    with pytest.raises(ValueError, match="notación trimestral"):
        resolve_news_query(f"noticias publicadas en 2{separator}{letter} {connector} 2026")


@pytest.mark.parametrize("notation", ["2 de T de 2026", "2delQdel2026"])
def test_connectors_before_quarter_letter_are_also_closed(notation):
    with pytest.raises(ValueError, match="notación trimestral"):
        resolve_news_query(f"noticias publicadas en {notation}")


@pytest.mark.parametrize("identifier", ["Q400", "T100"])
def test_quantity_before_literal_identifier_is_not_a_quarter(approved_index, identifier):
    result = approved_index.search_news(f"noticias sobre 2 {identifier} en 2026")
    assert identifier.lower() in result["filters"]["terms"]
    assert result["count"] == 0


@pytest.mark.parametrize(
    "question",
    [
        "Busca noticias sobre 2T26.",
        "Busca noticias publicadas en 2026-07 sobre 2T26.",
        "Busca noticias sobre 2T26 publicadas en 2026-07.",
    ],
)
def test_existing_archive_report_topic_is_not_a_publication_quarter(approved_index, question):
    result = approved_index.search_news(question)
    assert result["count"] == 2
    assert {row["published_at"] for row in result["results"]} == {"2026-07-15", "2026-07-22"}


@pytest.mark.parametrize(
    "question",
    [
        "noticias publicadas en 2T26 sobre combustible",
        "noticias publicadas en 2-Tde2026 sobre 2T26",
    ],
)
def test_report_topic_does_not_override_a_publication_period_request(question):
    with pytest.raises(ValueError, match="notación trimestral"):
        resolve_news_query(question)


def test_simple_archive_report_topic_keeps_selected_publication_month(approved_index):
    result = approved_index.search_news("Busca noticias publicadas en 2026-07 sobre combustible 2T26.")
    assert (result["filters"]["start_date"], result["filters"]["end_date"]) == ("2026-07-01", "2026-07-31")


@pytest.mark.parametrize(
    "subject",
    [
        "combustible desde 2T26",
        "el reporte fechado 2026-04-30 y 2T26",
        "lunes negro",
        "combustible que se publicaron en agosto de 2026",
        "combustible que se publicaron en 2T26",
        "combustible con publicación en 2T26",
        "combustible que se publicó en agosto de 2026",
        "combustible que se publique en 2T26",
        "combustible con fecha de publicación en agosto de 2026",
        "combustible con publicación: 2T26",
        "combustible que salieron en agosto de 2026",
    ],
)
def test_archive_subject_cannot_hide_ambiguous_calendar_constraints(subject):
    with pytest.raises(ValueError):
        resolve_news_query(f"Busca noticias publicadas en 2026-07 sobre {subject}.")


@pytest.mark.parametrize(
    "question",
    [
        "noticias sobre Aeroméxico en 2T26",
        "noticias publicadas en 2026-07 sobre 2T26 publicadas en 2T26",
    ],
)
def test_topic_scope_never_hides_another_publication_period(question):
    with pytest.raises(ValueError, match="notación trimestral"):
        resolve_news_query(question)


@pytest.mark.parametrize(
    "question",
    [
        "Busca noticias sobre Q2 challenges.",
        "Busca noticias publicadas en 2026-07 sobre Q2 challenges.",
        "Busca noticias sobre Q2 challenges publicadas en 2026-07.",
    ],
)
def test_approved_headline_quarter_words_remain_searchable(approved_index, question):
    result = approved_index.search_news(question)
    assert [row["id"] for row in result["results"]] == ["flightglobal-aeromexico-q2-2026-07-15"]


@pytest.mark.parametrize("marker", ["T", "Q"])
def test_incomplete_period_marker_cannot_disappear_into_an_unfiltered_year(marker):
    with pytest.raises(ValueError, match="notación trimestral"):
        resolve_news_query(f"noticias publicadas en {marker} de 2026")


@pytest.mark.parametrize(
    "notation",
    [
        "Q2FY26",
        "2QFY26",
        "FY26Q2",
        "T2FY26",
        "2TFY26",
        "FY26T2",
        "Q2FY2026",
        "2QFY2026",
        "FY2026Q2",
        "Q2 FY26",
        "2Q FY26",
        "FY26 Q2",
        "Q2 de FY26",
        "FY26 del Q2",
        "Q2-FY-2026",
    ],
)
@pytest.mark.parametrize("bounds", [{}, {"start_date": "2026-04-01", "end_date": "2026-06-30"}])
def test_fiscal_quarter_period_requires_explicit_iso_request(notation, bounds):
    with pytest.raises(ValueError, match="notación trimestral"):
        resolve_news_query(f"noticias publicadas en {notation}", **bounds)


@pytest.mark.parametrize("notation", ["Q2FY26", "2QFY26", "FY26Q2"])
def test_compact_fiscal_report_subject_stays_a_literal_search(approved_index, notation):
    result = approved_index.search_news(f"noticias publicadas en 2026-07 sobre {notation}")
    assert result["count"] == 0
    assert notation.lower() in result["filters"]["terms"]


@pytest.mark.parametrize("year", ["FY26", "FY2026", "FY-26", "FY 2026"])
@pytest.mark.parametrize("identifier", ["T2", "T 2", "T–2", "T"])
def test_fiscal_year_and_nonstandard_quarter_connector_need_clarification(year, identifier):
    with pytest.raises(ValueError, match="notación trimestral"):
        resolve_news_query(f"noticias publicadas en {year} correspondientes a {identifier}")


@pytest.mark.parametrize("year", ["FY26", "FY2026"])
def test_fiscal_year_does_not_make_explicit_airport_terminal_a_quarter(year):
    result = resolve_news_query(f"noticias sobre T2 del AICM en {year}")
    assert "t2" in result["terms"]
    assert "aicm" in result["terms"]


@pytest.mark.parametrize("year", ["2026", "FY2026", "FY26"])
@pytest.mark.parametrize("subject", ["el AIFA", "el AICM", "la terminal T1", "el aeropuerto de Cancun"])
def test_airport_subject_cannot_exempt_an_unrelated_publication_quarter(year, subject):
    with pytest.raises(ValueError, match="notación trimestral"):
        resolve_news_query(f"noticias publicadas en {year} correspondientes a T2 sobre {subject}")


@pytest.mark.parametrize(
    "question",
    [
        "noticias de 2026 T2 del AICM",
        "noticias de 2026 sobre la terminal T2",
        "noticias de la terminal T2 en 2026",
        "noticias de la AICM T2 en 2026",
    ],
)
def test_only_the_locally_attributed_terminal_token_is_exempt(question):
    intent = resolve_news_query(question)
    assert "t2" in intent["terms"]
    assert (intent["start_date"], intent["end_date"]) == ("2026-01-01", "2026-12-31")


@pytest.mark.parametrize(
    "question",
    [
        "noticias publicadas en FY2026 correspondientes a T2 sobre terminal T1",
        "noticias sobre terminal T1 publicadas en FY2026 correspondientes a T2",
    ],
)
def test_terminal_exception_does_not_exempt_another_quarter_token(question):
    with pytest.raises(ValueError, match="notación trimestral"):
        resolve_news_query(question)


@pytest.mark.parametrize(
    "terminal",
    [
        "T2 en el AICM",
        "T2 de la terminal del AICM",
        "T2 en el AIFA",
        "T2 en el aeropuerto de Cancun",
        "T2 en la terminal del AICM",
        "terminal (T2)",
        "terminal: T2",
        "AICM (T2)",
        "T2 (AICM)",
        "terminal aerea numero T2",
    ],
)
def test_local_terminal_prepositions_articles_and_wrappers_remain_searchable(approved_index, terminal):
    question = f"noticias de {terminal} en 2026"
    intent = resolve_news_query(question)
    assert "t2" in intent["terms"]
    assert (intent["start_date"], intent["end_date"]) == ("2026-01-01", "2026-12-31")
    assert approved_index.search_news(question)["count"] == 0


@pytest.mark.parametrize(
    "description",
    [
        ", la terminal del AICM",
        " (la terminal del AICM)",
        ", el AICM",
        " (el aeropuerto de Cancun)",
        " de la terminal del AICM",
        " en la terminal del AICM",
    ],
)
def test_terminal_apposition_article_does_not_require_a_preposition(description):
    intent = resolve_news_query(f"noticias de T2{description} en 2026")
    assert "t2" in intent["terms"]
    assert (intent["start_date"], intent["end_date"]) == ("2026-01-01", "2026-12-31")


@pytest.mark.parametrize("connector", ["en", "del"])
def test_selected_publication_month_preserves_report_quarter_in_subject(approved_index, connector):
    result = approved_index.search_news(
        f"Busca noticias publicadas en 2026-07 sobre resultados de Aeroméxico {connector} 2T26"
    )
    assert [row["id"] for row in result["results"]] == ["flightglobal-aeromexico-q2-2026-07-15"]
    assert (result["filters"]["start_date"], result["filters"]["end_date"]) == ("2026-07-01", "2026-07-31")


@pytest.mark.parametrize(
    "terminal",
    [
        "aeropuerto T2",
        "aeropuertos T2",
        "el aeropuerto (T2)",
        "T2, una terminal del AICM",
        "T2 en un aeropuerto",
        "T2 (una terminal del AICM)",
        "T2, unas terminales del AICM",
        "T2 en unos aeropuertos",
    ],
)
def test_airport_prefix_and_indefinite_terminal_appositions_remain_literal(terminal):
    intent = resolve_news_query(f"noticias de {terminal} en 2026")
    assert "t2" in intent["terms"]
    assert (intent["start_date"], intent["end_date"]) == ("2026-01-01", "2026-12-31")


@pytest.mark.parametrize(
    "period,bounds",
    [
        ("julio de 2026", ("2026-07-01", "2026-07-31")),
        ("2026", ("2026-01-01", "2026-12-31")),
    ],
)
def test_named_month_or_year_before_subject_also_anchors_publication(approved_index, period, bounds):
    result = approved_index.search_news(
        f"noticias publicadas en {period} sobre resultados de Aeroméxico en 2T26"
    )
    assert [row["id"] for row in result["results"]] == ["flightglobal-aeromexico-q2-2026-07-15"]
    assert (result["filters"]["start_date"], result["filters"]["end_date"]) == bounds


@pytest.mark.parametrize(
    "verb", ["salieron", "aparecieron", "se difundieron", "se emitieron", "se divulgaron"]
)
@pytest.mark.parametrize("period", ["2T26", "agosto de 2026"])
def test_relative_publication_clause_keeps_quarter_and_calendar_constraints_visible(verb, period):
    with pytest.raises(ValueError):
        resolve_news_query(f"Busca noticias publicadas en 2026-07 sobre combustible que {verb} en {period}")


@pytest.mark.parametrize("verb", ["pasó", "ocurrió"])
def test_interrogative_topic_at_its_start_stays_searchable(approved_index, verb):
    result = approved_index.search_news(f"Busca noticias publicadas en 2026-07 sobre qué {verb} en 2T26")
    assert result["count"] == 2
    assert (result["filters"]["start_date"], result["filters"]["end_date"]) == ("2026-07-01", "2026-07-31")


@pytest.mark.parametrize(
    "opening,closing",
    [
        (" (", ")"),
        (" — ", ""),
        (": ", ""),
        ("; ", ""),
        (" [", "]"),
        (" {", "}"),
        (' "', '"'),
        (" '", "'"),
    ],
)
def test_wrapped_relative_clause_preserves_quarter_constraint(opening, closing):
    with pytest.raises(ValueError, match="notación trimestral"):
        resolve_news_query(
            f"Busca noticias publicadas en 2026-07 sobre combustible{opening}que salieron en 2T26{closing}"
        )


@pytest.mark.parametrize("verb", ["pasó", "ocurrió"])
def test_wrapped_interrogative_topic_stays_literal(approved_index, verb):
    result = approved_index.search_news(f"Busca noticias publicadas en 2026-07 sobre (¿qué {verb} en 2T26?)")
    assert result["count"] == 2
    assert (result["filters"]["start_date"], result["filters"]["end_date"]) == ("2026-07-01", "2026-07-31")


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
