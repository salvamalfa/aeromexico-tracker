"""Bounded Spanish news intent extraction; never generates facts or approvals."""

from __future__ import annotations

import calendar
from datetime import date
import re
import unicodedata

MONTHS = dict(
    zip(
        ("enero febrero marzo abril mayo junio julio agosto septiembre octubre noviembre diciembre").split(),
        range(1, 13),
    )
)
ENTITIES = {
    "Aeroméxico": ("aeromexico", "amx", "grupo aeromexico"),
    "Aeroméxico Connect": (
        "aeromexico connect",
        "aeromexico_connect",
        "aeromexicoconnect",
        "amx connect",
        "amxconnect",
        "connect",
    ),
    "Viva": ("viva", "viva aerobus", "viva_aerobus"),
    "Volaris": ("volaris",),
}
WEEKDAYS = {
    name: number
    for number, name in enumerate(("lunes", "martes", "miercoles", "jueves", "viernes", "sabado", "domingo"))
}
TOPICS = {
    "alianzas": ("alianza", "alianzas", "acuerdo", "acuerdos"),
    "regulación": ("regulacion", "regulatorio", "regulatoria"),
    "financiamiento": ("financiamiento", "liquidez", "credito", "deuda"),
    "capital": ("capital", "recompra", "recompras"),
    "tráfico": ("trafico", "pasajeros", "demanda"),
    "capacidad": ("capacidad", "asientos"),
    "red": ("red", "rutas", "ruta"),
    "programación": ("programacion", "programadas", "programados"),
    "resultados": ("resultados", "financieros"),
    "calendario": ("calendario", "llamada"),
    "flota": ("flota", "aviones", "aeronaves"),
    "combustible": ("combustible",),
}
STOP = set(
    "que cuales cual paso ocurrio noticias noticia fichas ficha historias historia sobre de del la las el los en y o con para por al entre hasta desde durante publicadas publicados publicado muestra muestrame mostrar busca buscar quiero ver dame dime cuentame todas todos mas recientes ultimas ultimos aprobado aprobadas aprobados cita citas fuentes fuente favor me se su sus un una hubo cambios cambio mes meses ano anos".split()
)
STOP.update("es son ser esta estan hay ultima ultimo reciente".split())
STOP.update(
    "fue fueron ha han habia como cuando donde acerca publico publicaron publica publicaciones publicacion notas nota dijo reporto informo comunico anuncio anuncios anuncia anunciaron principales".split()
)


# One bounded vocabulary is shared by topic boundaries and explicit filters.
# It does not infer arbitrary predicates or Spanish sentence structure.
PUBLICATION_CUES = (
    r"\b(?:publica\w*|publico|publique\w*|sal(?:io|ieron|en|ga|gan|dran?|drian?)"
    r"|aparec\w*|aparez\w*|difund\w*|emit\w*|divulg\w*)\b"
)


def norm(value: str) -> str:
    return re.sub(
        r"\s+",
        " ",
        "".join(c for c in unicodedata.normalize("NFD", value.lower()) if unicodedata.category(c) != "Mn"),
    ).strip()


def entity_text(value: str) -> str:
    # Resolve the specific compound before matching a parent brand. Explicit
    # conjunctions remain words and therefore retain a two-entity request.
    return re.sub(r"\b(?:aeromexico|amx)[\W_]+connect\b(?:\s*[)\]}])?", "aeromexico_connect", norm(value))


def topic_key(value: str) -> str:
    text = norm(value)
    return next((norm(key) for key, aliases in TOPICS.items() if text in aliases or text == norm(key)), text)


def _publication_scope(text: str) -> str:
    """Keep explicit archive topic text out of publication-period extraction."""
    characters = list(text)
    for marker in re.finditer(r"\bsobre\b", text):
        start = marker.end()
        # Only quarter labels within the subject are exempt from period
        # detection. Keep all calendar constraints visible, including an
        # additional publication clause expressed with another verb/noun.
        selected_period = bool(
            re.search(r"\b\d{4}\b", text[:marker.start()])
            or re.search(PUBLICATION_CUES + r".*\b\d{4}\b", text[start:])
        )
        # With an explicitly selected archive period, "en 2T26" can name
        # the report's subject. Other calendar constraints remain visible;
        # a publication verb always starts a separate period clause.
        boundary = PUBLICATION_CUES + r"|\b(?:desde|hasta|entre|durante" + ("" if selected_period else "|en") + r")\b"
        # A small release vocabulary marks a potentially separate publication
        # constraint. The rest of the subject is literal topic text; no
        # cognition, actor, pronoun or relative-clause grammar is inferred.
        following = re.search(boundary, text[start:])
        end = start + following.start() if following else len(text)
        # Topic quarter labels use the same three orders as period guards.
        # Consume the complete label so its year cannot become a second
        # publication filter. Literal numbered identifiers remain searchable.
        join = r"[\W_]*(?:(?:de|del)[\W_]*)?"
        year = r"(?:fy[\W_]*)?\d{2}(?:\d{2})?"
        full_year = r"(?:\d{4}|fy[\W_]*\d{2}(?:\d{2})?)"
        short_year = r"(?:[\W_]+(?:(?:de|del)[\W_]*)?|(?:de|del)[\W_]*)" + year
        quarter = (
            full_year + join + r"[qt][1-4]"
            + r"|[qt][1-4](?:" + join + full_year + r"|" + short_year + r")?"
            + r"|[1-4]" + join + r"[tq](?:" + join + year + r")?"
        )
        spans = [
            (start + match.start(), start + match.end())
            for match in re.finditer(r"\b(?:" + quarter + r")\b", text[start:end])
        ]
        for first, last in spans:
            characters[first:last] = " " * (last - first)
    # An airport elsewhere in the question cannot turn an unrelated period
    # into a terminal. Exempt only a T token with its own explicit context.
    for token in re.finditer(r"\bt[1-4]\b", text):
        before, after = text[:token.start()], text[token.end():]
        terminal = re.search(r"\b(?:terminal(?:es)?(?:\s+(?:aerea|aereas|numero|num))*|aicm|aifa|aeropuerto(?:s)?)[\W_]*$", before)
        airport = re.match(r"[\W_]*(?:(?:de|del|en)\s+)?(?:(?:el|la|los|las|un|una|unos|unas)\s+)?(?:aicm|aifa|aeropuerto(?:s)?|terminal(?:es)?)\b", after)
        if terminal or airport:
            characters[token.start():token.end()] = " " * len(token.group())
    return "".join(characters)

def _news_input_text(question: str) -> str:
    # Keep numbered identifiers intact for both temporal guards and text
    # search: T 2 / Q 400 must not disappear as one letter plus a number.
    text = "".join(
        "-" if unicodedata.category(char) == "Pd" or char == "−" else char
        for char in entity_text(question)
    )
    text = re.sub(r"\b([qt])[\W_]+(\d+)\b", r"\1\2", text)
    return text


def resolve_news_query(question: str, start_date=None, end_date=None, company=None) -> dict:
    text = _news_input_text(question)
    # Compact quarter labels are not publication dates or free-text topics.
    # Require explicit endpoints until quarter precision has its own contract.
    separator = r"[\W_]*(?:(?:de|del)[\W_]*)?"
    quarter_year = r"(?:fy[\W_]*)?\d{2}(?:\d{2})?"
    fiscal_year = r"fy[\W_]*\d{2}(?:\d{2})?"
    explicit_year = r"(?:\d{4}|" + fiscal_year + r")"
    # A short year after T/Q needs a separator or connector: T100 and Q400
    # are literal identifiers, while T1 de 00 and Q4/00 request a period.
    separated_year = r"(?:[\W_]+(?:(?:de|del)[\W_]*)?|(?:de|del)[\W_]*)" + quarter_year
    prefix_period = r"[qt]\s*\d(?:" + separator + explicit_year + r"|" + separated_year + r")"
    # The archive's existing topic tag (e.g. "sobre 2T26") describes report
    # content. Keep it searchable without treating it as publication dates.
    # Preserve the stressed ú through cue classification: pública/público
    # have a different root from publica/publicó. The one-character marker
    # keeps offsets aligned; restore normal text before calendar extraction.
    cue_text = _news_input_text(unicodedata.normalize("NFC", question).replace("ú", "\ue000").replace("Ú", "\ue000"))
    cue_period_text = _publication_scope(cue_text)
    period_text = cue_period_text.replace("\ue000", "u")
    ambiguous_t_period = (
        re.search(r"\b" + explicit_year + r"\b", period_text)
        and re.search(r"\b[qt](?:[1-4])?\b", period_text)
    )
    if ambiguous_t_period or re.search(
        r"\b(?:" + explicit_year + separator + r"[qt]\s*\d|" + prefix_period
        + r"|q\s*\d|\d" + separator + r"[qt](?:" + separator + quarter_year + r")?)\b",
        period_text,
    ):
        raise ValueError(
            "Indica inicio y fin de publicación como fechas ISO YYYY-MM-DD; la notación trimestral compacta no está admitida."
        )
    companies = [
        name
        for name, aliases in ENTITIES.items()
        if any(
            re.search(
                r"\b" + re.escape(alias) + r"\b",
                text,
            )
            for alias in aliases
        )
    ]
    if company:
        company_key = entity_text(company).strip("()[]{} .,:;/—–-_")
        selected = next(
            (
                name
                for name, aliases in ENTITIES.items()
                if company_key in aliases or company_key == norm(name)
            ),
            company,
        )
        if companies and set(companies) != {selected}:
            raise ValueError(
                "La aerolínea indicada no coincide con las aerolíneas explícitas de la consulta."
            )
        companies = [selected]
    semantic_text, text = text, period_text
    years = re.findall(r"\b(\d{4})\b", text)
    months = [MONTHS[m] for m in re.findall(r"\b(" + "|".join(MONTHS) + r")\b", text)]
    iso_months = re.findall(r"\b(\d{4})-(0[1-9]|1[0-2])(?!-\d{2})\b", text)
    iso_dates = re.findall(r"\b\d{4}-\d{2}-\d{2}\b", text)
    if re.search(
        r"\b\d{4}-\d{2}-\d{2}[t ]\d{1,2}:\d{2}|\b(?:a las|antes de las|despues de las|entre las)\s+\d{1,2}:\d{2}",
        text,
    ):
        raise ValueError("Solo se filtra fecha diaria de publicación; la hora no está documentada.")
    if re.search(r"\bhoras?\b|\b\d{1,2}(?::\d{2})?\s*(?:a\.?m\.?|p\.?m\.?)\b|\b\d{1,2}h(?:\d{2})?\b", text):
        raise ValueError("Solo se filtra fecha diaria de publicación; la hora no está documentada.")
    hour_words = r"(?:\d{1,2}|cero|un[oa]?|dos|tres|cuatro|cinco|seis|siete|ocho|nueve|diez|once|doce|trece|catorce|quince|dieci\w*|veinte|veinti\w*|veinticuatro)"
    if re.search(
        r"\b(?:a|antes de|despues de|hasta|desde|entre)\s+(?:la|las)\s+"
        + hour_words
        + r"\b|\b(?:mediodia|medianoche)\b|\b(?:de|por|en|durante)\s+(?:la\s+)?(?:manana|tarde|noche|madrugada)\b",
        text,
    ):
        raise ValueError("Solo se filtra fecha diaria de publicación; la hora no está documentada.")
    if re.search(
        r"\b(?:antes|despues)\b|\b(?:anterior(?:es)?|posterior(?:es)?|previo[as]?|previa[as]?)\s+(?:a|al)\b|\ba\s+(?:partir|contar)\s+de(?:l)?\b|\ben\s+(?:adelante|lo\s+sucesivo)\b",
        text,
    ):
        raise ValueError(
            "Indica inicio y fin explícitos como fechas explícitas de publicación; ese calificador direccional no está admitido."
        )
    month_names = "|".join(MONTHS)
    named_days = re.findall(r"\b(\d{1,2})\s+(?:de\s+)?(" + month_names + r")\s+(?:de\s+)?(\d{4})\b", text)
    day_word = r"(?:\d{1,2}(?:[º°]|\.[º°])?|primer[oa]?|uno|dos|tres|cuatro|cinco|seis|siete|ocho|nueve|diez|once|doce|trece|catorce|quince|dieci\w*|veinte|veinti\w*|treinta(?:\s+y\s+uno)?)"
    named_day_precision = bool(
        re.search(
            r"\b"
            + day_word
            + r"(?:\s+(?:de\s+)?|[/-])(?:"
            + month_names
            + r")\b|\b(?:"
            + month_names
            + r")(?:\s+|[/-])"
            + day_word
            + r"\b",
            text,
        )
    )
    if re.search(r"\b\d{1,2}[/-]\d{1,2}[/-]\d{4}\b", text):
        raise ValueError("Usa fecha ISO YYYY-MM-DD para un día exacto.")
    if named_day_precision and (
        not named_days
        or len(named_days) != len(months)
        or len(named_days) != len(years)
        or len(named_days) > 2
        or len(re.findall(r"\b\d{1,2}\b", text)) != len(named_days)
    ):
        raise ValueError("Usa fechas ISO YYYY-MM-DD para ambos días exactos.")
    if re.search(
        r"\b(?:principios|mediados|finales|comienzos|fin)\s+de\s+(?:" + month_names + r"|\d{4})\b", text
    ):
        raise ValueError("Indica fechas explícitas para ese intervalo parcial.")
    # A list names discrete publication windows. Converting its endpoints to
    # a continuous interval would silently include unrequested dates/months.
    temporal_points = (
        (named_days, r"\d{1,2}\s+(?:de\s+)?(?:" + month_names + r")\s+(?:de\s+)?\d{4}")
        if named_days else
        (iso_dates, r"\d{4}-\d{2}-\d{2}") if iso_dates else
        (iso_months, r"\d{4}-(?:0[1-9]|1[0-2])(?!-\d{2})") if iso_months else
        (months, r"(?:" + month_names + r")(?:\s+(?:de\s+)?\d{4})?") if months else
        (years, r"\d{4}")
    )
    points, endpoint = temporal_points
    if len(points) > 1:
        point = r"(?:el\s+)?" + endpoint
        between = r"\bentre\s+(?:los\s+(?:meses|anos|dias)\s+de\s+)?" + point + r"\s+y\s+" + point + r"\b"
        span = r"\b" + point + r"(?:\s+(?:a|al|hasta)\s+|\s*[-–—]\s*)" + point + r"\b"
        if len(points) != 2 or not (re.search(between, text) or re.search(span, text)):
            raise ValueError(
                "Indica un intervalo explícito de publicación con inicio y fin explícitos; no se admiten listas de fechas o meses separados."
            )
    supplied_start, supplied_end = start_date, end_date
    for value in (supplied_start, supplied_end):
        if value is not None:
            if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
                raise ValueError("Indica fechas explícitas YYYY-MM-DD.")
            date.fromisoformat(value)
    if supplied_start and supplied_end and supplied_start > supplied_end:
        raise ValueError("El inicio no puede ser posterior al fin.")
    # Query meaning is validated independently of nullable caller arguments.
    start_date = end_date = None
    # A malformed ISO-like token must not fall through to a broad year filter.
    for token in re.findall(r"\b\d{4}(?:-\d+)+\b", text):
        if not re.fullmatch(r"\d{4}-\d{2}(?:-\d{2})?", token):
            raise ValueError("Usa fechas YYYY-MM-DD o meses YYYY-MM explícitos.")
        date.fromisoformat(token + "-01" if len(token) == 7 else token)
    relative = re.search(
        r"\b(?:ultim[oa]s?|este|esta|estos|estas|anterior(?:es)?)\s+(?:(?:\d+|un|una|uno|dos|tres|cuatro|cinco|seis|siete|ocho|nueve|diez|quince|treinta)\s+)?(?:minutos?|horas?|dias?|semanas?|quincenas?|mes(?:es)?|bimestres?|trimestres?|cuatrimestres?|semestres?|anos?|ejercicios?)\b|\b(?:minutos?|horas?|dias?|semanas?|quincenas?|mes(?:es)?|bimestres?|trimestres?|cuatrimestres?|semestres?|anos?|ejercicios?)\s+(?:pasad[oa]s?|anterior(?:es)?)\b",
        text,
    )
    relative_quantity = re.search(
        r"\b(?:hace|dentro\s+de|pasad[oa]s?|proxim[oa]s?)\s+(?:\w+\s+){0,12}(?:minutos?|horas?|dias?|semanas?|quincenas?|mes(?:es)?|bimestres?|trimestres?|cuatrimestres?|semestres?|anos?|ejercicios?)\b",
        text,
    )
    units = re.findall(
        r"\b(?:minutos?|horas?|dias?|semanas?|quincenas?|mes(?:es)?|bimestres?|trimestres?|cuatrimestres?|semestres?|anos?|ejercicios?)\b",
        text,
    )
    absolute = bool(iso_dates or iso_months or months or years)
    if (
        relative
        or relative_quantity
        or (units and not absolute)
        or re.search(r"\b(?:anteayer|antier|anoche|ayer|hoy|manana)\b", text)
    ):
        raise ValueError("Indica fechas explícitas; no se infiere el periodo de una noticia.")
    complex_units = set(units) - {"dia", "dias", "mes", "meses", "ano", "anos"}
    if (
        (complex_units and (len(iso_dates) or len(named_days)) != 2)
        or (set(units) & {"mes", "meses"} and not (months or iso_months or iso_dates))
        or (set(units) & {"dia", "dias"} and not (iso_dates or named_days))
    ):
        raise ValueError("Indica fechas explícitas de inicio y fin para ese periodo.")
    if named_days:
        points = [date(int(year), MONTHS[month], int(day)).isoformat() for day, month, year in named_days]
        start_date, end_date = points[0], points[-1]
    elif iso_dates:
        if len(iso_dates) > 2 or len(years) != len(iso_dates):
            raise ValueError("Indica ambos extremos con fechas explícitas de la misma precisión.")
        start_date, end_date = iso_dates[0], iso_dates[-1]
    elif iso_months:
        if len(iso_months) > 2 or len(years) != len(iso_months):
            raise ValueError("Indica ambos extremos con meses y años explícitos.")
        first, last = iso_months[0], iso_months[-1]
        start_date = date(int(first[0]), int(first[1]), 1).isoformat()
        end_date = date(
            int(last[0]), int(last[1]), calendar.monthrange(int(last[0]), int(last[1]))[1]
        ).isoformat()
    elif months:
        pairs = re.findall(r"\b(" + "|".join(MONTHS) + r")\s+(?:de\s+)?(\d{4})\b", text)
        if len(months) > 2:
            raise ValueError("Indica un mes o un intervalo explícito de dos meses.")
        if len(pairs) == len(months):
            if len(years) != len(pairs) or set(years) != {year for _, year in pairs}:
                raise ValueError("Indica el mes y año de ambos extremos; hay un año sin asociar.")
            first_year, last_year = int(pairs[0][1]), int(pairs[-1][1])
        elif len(set(years)) == 1:
            first_year = last_year = int(years[0])
        else:
            raise ValueError("Indica el año de cada extremo del intervalo.")
        start_date = date(first_year, months[0], 1).isoformat()
        end_date = date(last_year, months[-1], calendar.monthrange(last_year, months[-1])[1]).isoformat()
    elif years:
        endpoints = list(dict.fromkeys(years))
        if len(endpoints) > 2:
            raise ValueError("Indica un año o un intervalo de dos años explícitos.")
        start_date, end_date = f"{endpoints[0]}-01-01", f"{endpoints[-1]}-12-31"
    elif re.search(r"\b(pasado|pasada|ayer|hoy)\b", text):
        raise ValueError("Indica fechas explícitas; no se infiere el periodo de una noticia.")
    intrinsic = bool(iso_dates or iso_months or months or years)
    periods = len(named_days) or len(iso_dates) or len(iso_months) or len(months) or len(years)
    if intrinsic:
        since = bool(re.search(r"\bdesde\b", text))
        until = bool(re.search(r"\bhasta\b", text))
        if re.search(r"\bentre\b", text) and periods != 2:
            raise ValueError("Indica ambos extremos explícitos del intervalo.")
        if periods == 1:
            if since and not until:
                end_date = None
            elif until and not since:
                start_date = None
        if (supplied_start is not None and supplied_start != start_date) or (
            supplied_end is not None and supplied_end != end_date
        ):
            raise ValueError(
                "Los límites no coinciden con las fechas de publicación expresadas; indica inicio y fin explícitos."
            )
    else:
        start_date, end_date = supplied_start, supplied_end
    for value in (start_date, end_date):
        if value:
            date.fromisoformat(value)
    if start_date and end_date and start_date > end_date:
        raise ValueError("El inicio no puede ser posterior al fin.")
    weekdays = {word for word in re.findall(r"\w+", period_text) if word in WEEKDAYS}
    if weekdays:
        if not intrinsic or start_date is None or start_date != end_date or len(weekdays) != 1:
            raise ValueError(
                "Indica una fecha exacta; no se infiere ni se filtra un día semanal dentro de un intervalo."
            )
        if date.fromisoformat(start_date).weekday() != WEEKDAYS[next(iter(weekdays))]:
            raise ValueError("El día semanal no coincide con la fecha explícita.")
    text = semantic_text
    topics = [
        key
        for key, aliases in TOPICS.items()
        if any(
            re.search(
                r"\b" + re.escape(alias) + r"\b",
                text,
            )
            for alias in aliases
        )
    ]
    removed = STOP | set(MONTHS) | set(years) | set(WEEKDAYS)
    # Exclude only the occurrence introducing the next calendar filter.
    # Set subtraction would also erase the same word in a literal topic.
    calendar_marker = r"\b(?:\d{4}|" + "|".join(MONTHS) + r")\b"
    search_characters = list(semantic_text)
    for cue in re.finditer(PUBLICATION_CUES, cue_period_text):
        following = period_text[cue.end():]
        calendar_match = re.search(calendar_marker, following)
        next_cue = re.search(PUBLICATION_CUES, cue_period_text[cue.end():])
        if calendar_match and (next_cue is None or calendar_match.start() < next_cue.start()):
            search_characters[cue.start():cue.end()] = " " * len(cue.group())
    words = set(re.findall(r"\w+", "".join(search_characters)))
    # Legacy stop words include publica/publico. Restore only the accented
    # adjective's literal occurrence; actual filter occurrences are masked.
    for literal in re.finditer(r"\bp\ue000blic[oa]s?\b", cue_period_text):
        removed.discard(semantic_text[literal.start():literal.end()])
    removed |= set(re.findall(r"\w+", " ".join(alias for aliases in ENTITIES.values() for alias in aliases)))
    removed |= set(re.findall(r"\w+", " ".join(alias for key in topics for alias in TOPICS[key])))
    terms = sorted(word for word in words - removed if len(word) > 1 and not word.isdigit())
    return {
        "companies": companies,
        "start_date": start_date,
        "end_date": end_date,
        "date_basis": "publication",
        "topics": topics,
        "terms": terms,
    }


def news_match(intent: dict, title: str, description: str, companies: list[str], topics: list[str]) -> int:
    if intent["companies"] and not {norm(c) for c in companies}.intersection(
        norm(c) for c in intent["companies"]
    ):
        return 0
    if intent["topics"] and not {topic_key(t) for t in intent["topics"]}.intersection(
        topic_key(t) for t in topics
    ):
        return 0
    available = set(re.findall(r"\w+", norm(" ".join([title, description, *topics]))))
    matched = len(set(intent["terms"]) & available)
    return matched + (1 if intent["topics"] else 0) if intent["terms"] else 1
