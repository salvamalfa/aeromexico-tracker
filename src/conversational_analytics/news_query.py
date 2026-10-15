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
    "Aeroméxico": ("aeromexico", "aeromexico connect"),
    "Viva": ("viva", "viva aerobus"),
    "Volaris": ("volaris",),
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
STOP.update(
    "fue fueron ha han habia como cuando donde acerca publico publicaron publica publicaciones publicacion notas nota dijo reporto informo comunico anuncio anuncios anuncia anunciaron principales".split()
)


def norm(value: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", value.lower()) if unicodedata.category(c) != "Mn")


def topic_key(value: str) -> str:
    text = norm(value)
    return next((norm(key) for key, aliases in TOPICS.items() if text in aliases or text == norm(key)), text)


def resolve_news_query(question: str, start_date=None, end_date=None, company=None) -> dict:
    text = norm(question)
    words = set(re.findall(r"\w+", text))
    companies = [
        name
        for name, aliases in ENTITIES.items()
        if any(re.search(r"\b" + re.escape(alias) + r"\b", text) for alias in aliases)
    ]
    if company:
        selected = next(
            (
                name
                for name, aliases in ENTITIES.items()
                if norm(company) in aliases or norm(company) == norm(name)
            ),
            company,
        )
        companies = [selected]
    years = re.findall(r"\b(20\d{2})\b", text)
    months = [MONTHS[m] for m in re.findall(r"\b(" + "|".join(MONTHS) + r")\b", text)]
    iso_months = re.findall(r"\b(20\d{2})-(0[1-9]|1[0-2])(?!-\d{2})\b", text)
    iso_dates = re.findall(r"\b20\d{2}-\d{2}-\d{2}\b", text)
    if not start_date and not end_date:
        if iso_dates:
            start_date, end_date = iso_dates[0], iso_dates[-1]
        elif iso_months:
            first, last = iso_months[0], iso_months[-1]
            start_date = date(int(first[0]), int(first[1]), 1).isoformat()
            end_date = date(
                int(last[0]), int(last[1]), calendar.monthrange(int(last[0]), int(last[1]))[1]
            ).isoformat()
        elif months:
            pairs = re.findall(r"\b(" + "|".join(MONTHS) + r")\s+(?:de\s+)?(20\d{2})\b", text)
            if len(months) > 2:
                raise ValueError("Indica un mes o un intervalo explícito de dos meses.")
            if len(pairs) == len(months):
                first_year, last_year = int(pairs[0][1]), int(pairs[-1][1])
            elif len(set(years)) == 1:
                first_year = last_year = int(years[0])
            else:
                raise ValueError("Indica el año de cada extremo del intervalo.")
            start_date = date(first_year, months[0], 1).isoformat()
            end_date = date(last_year, months[-1], calendar.monthrange(last_year, months[-1])[1]).isoformat()
        elif len(set(years)) == 1:
            start_date, end_date = f"{years[0]}-01-01", f"{years[0]}-12-31"
        elif re.search(r"\b(pasado|pasada|ayer|hoy)\b", text):
            raise ValueError("Indica fechas explícitas; no se infiere el periodo de una noticia.")
    for value in (start_date, end_date):
        if value:
            date.fromisoformat(value)
    if start_date and end_date and start_date > end_date:
        raise ValueError("El inicio no puede ser posterior al fin.")
    topics = [
        key
        for key, aliases in TOPICS.items()
        if any(re.search(r"\b" + re.escape(alias) + r"\b", text) for alias in aliases)
    ]
    removed = STOP | set(MONTHS) | set(years)
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
