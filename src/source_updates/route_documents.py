"""Retained dated source passages; announcements and rosters are not flight observations."""

from __future__ import annotations

from datetime import datetime
import hashlib
import io
import json
import re

from bs4 import BeautifulSoup
import pandas as pd
from pypdf import PdfReader

VERSION = "retained_route_document_passages_v1"
PRODUCTS = ("am_routes", "oma_routes", "colima", "aifa_roster")
TABLES = {p: f"fact_{p}_retained_passages" for p in PRODUCTS}
GRAIN = ["document_date_as_reported", "passage_sha256"]


def normalized(text):
    return " ".join(text.split())


def html(content):
    if not 1 <= len(content) <= 5_000_000:
        raise ValueError("Route source HTML exceeds reviewed bound")
    soup = BeautifulSoup(content.decode("utf-8", errors="strict"), "html.parser")
    if soup.title is None:
        raise ValueError("Route document title missing")
    return soup


def paragraph(soup, prefix):
    found = {
        normalized(tag.get_text(" ", strip=True)): (i, tag)
        for i, tag in enumerate(soup.find_all("p"), 1)
        if normalized(tag.get_text(" ", strip=True)).startswith(prefix)
    }
    if len(found) != 1:
        raise ValueError("Expected unique dated route source paragraph")
    text, (index, _) = next(iter(found.items()))
    return text, f"html:p[{index}]"


def extract(product, content):
    if product == "oma_routes":
        if not content.startswith(b"%PDF-") or len(content) > 2_000_000:
            raise ValueError("OMA route PDF outside reviewed bound")
        pdf = PdfReader(io.BytesIO(content))
        if len(pdf.pages) != 2:
            raise ValueError("OMA route report pages changed")
        intro, schedule = [normalized(p.extract_text() or "") for p in pdf.pages]
        if "Grupo Aeroportuario del Centro Norte (OMA)" not in intro or "Aeroméxico" not in intro:
            raise ValueError("OMA source/company identity missing")
        first = re.search(r"(Monterrey, N\.L\., a 13 de abril de 2026\. .+?)(?= La apertura)", intro)
        second = re.search(
            r"(Monterrey contará con tres frecuencias semanales hacia París .+?)(?= [“\"]Nuevo León)",
            schedule,
        )
        if (
            not first
            or not second
            or not all(
                v in second[1]
                for v in ["lunes, jueves y sábado", "martes, viernes y domingo", "15:15", "12:00"]
            )
        ):
            raise ValueError("OMA dated announcement/schedule passage changed")
        return (
            "2026-04-13",
            [(first[1], "page:1/dated-intro"), (second[1], "page:2/weekly-announced-schedule")],
            "official_dated_announcement_not_verified_operations",
            None,
        )
    soup = html(content)
    if product == "am_routes":
        if "AEROMEXICO INCREASES OPERATIONS AT AIFA" not in soup.title.get_text():
            raise ValueError("Aeromexico source release title changed")
        dates = [normalized(t.get_text(" ", strip=True)) for t in soup.find_all(["p", "time"])]
        if not any("September 06, 2023 20:25 ET" in value for value in dates):
            raise ValueError("Official release reported date/time missing")
        first = paragraph(soup, "Mexico City, September 6th, 2023.- Starting October 5,")
        second = paragraph(soup, "With this adjustment, Aeromexico's operation at AIFA")
        if (
            "the route to Colima will be transferred from AICM to AIFA with seven weekly flights"
            not in second[0]
        ):
            raise ValueError("Official announced route passage changed")
        return (
            "2023-09-06",
            [first, second],
            "official_company_release_distributed_by_GlobeNewswire_not_verified_operations",
            "September 06, 2023 20:25 ET",
        )
    if product == "colima":
        text = soup.get_text(" ", strip=True)
        if "Administrador Colimapm | Colima | 28/05/2026" not in text:
            raise ValueError("Colima article date/byline missing; page clock is not publication date")
        passage = paragraph(soup, "La Subsecretaría de Turismo del Gobierno del Estado de Colima")
        if not all(
            v in passage[0]
            for v in [
                "a partir del 25 de junio",
                "Aeroméxico",
                "Felipe Ángeles (AIFA)",
                "Benito Juárez de la Ciudad de México (AICM)",
            ]
        ):
            raise ValueError("Secondary statement route/date passage changed")
        return (
            "2026-05-28",
            [passage],
            "secondary_mirror_attributing_statement_to_Colima_Subsectur_not_primary_verification",
            None,
        )
    if product == "aifa_roster":
        articles = []
        for script in soup.find_all("script", type="application/ld+json"):
            data = json.loads(script.get_text())
            if isinstance(data, dict) and data.get("@type") == "NewsArticle":
                articles.append(data)
        if len(articles) != 1:
            raise ValueError("Expected one dated NewsArticle in roster")
        article = articles[0]
        if article.get(
            "datePublished"
        ) != "2026-06-08T17:44:32.162Z" or "Todas las aerolíneas que operan en el AIFA" not in article.get(
            "headline", ""
        ):
            raise ValueError("Roster source date/headline changed")
        text = article.get("articleBody", "")
        marker = "Vuelos nacionalesAeroméxicoOfrece los siguientes vuelos nacionales:"
        if text.count(marker) != 1 or text.count("AerusLa aerolínea regional mexicana") != 1:
            raise ValueError("Roster company section boundary changed")
        passage = text.split(marker, 1)[1].split("AerusLa aerolínea regional mexicana", 1)[0]
        if not passage or len(passage) > 1000:
            raise ValueError("Roster section empty/oversized")
        return (
            "2026-06-08",
            [(marker + passage, "html:NewsArticle.articleBody/Aeromexico-national-roster")],
            "secondary_dated_roster_presence_claim_only_not_counted_flights_or_continuing_operation",
            article["datePublished"],
        )
    raise ValueError("No reviewed route-document product")


def parse(product, inputs, period):
    content, original = inputs["document"]
    date, passages, kind, time = extract(product, content)
    datetime.strptime(date, "%Y-%m-%d")
    if period != date[:4] + "M" + date[5:7]:
        raise ValueError("Requested period must match document date, not capture or URL date")
    output = []
    for text, locator in passages:
        output.append(
            dict(
                period_id=period,
                period_type="document_publication_month_not_observation_month",
                metric_key="retained_source_passage",
                value=text,
                unit="source_text",
                document_date_as_reported=date,
                reported_publication_time_literal=time,
                evidence_kind=kind,
                passage_sha256=hashlib.sha256(text.encode()).hexdigest(),
                source_system=original["source_system"],
                source_file=original["source_file"],
                source_hash=original["sha256"],
                ingested_at=pd.Timestamp(original["downloaded_at"]),
                source_locator=locator,
                parser_version=VERSION,
                performed_flights=None,
                passengers=None,
                seats=None,
                operator_icao=None,
                agent_eligible=False,
            )
        )
    frame = pd.DataFrame(output)
    if frame.empty or frame.duplicated(GRAIN).any():
        raise ValueError("Empty/duplicate retained source passage")
    return frame, dict(
        rows=len(frame),
        report_period=period,
        months_validated=[],
        document_date_as_reported=date,
        source_reported_publication_time_literal=time,
        published_at=None,
        release_lag_days=None,
        scope="retained_dated_text_passages_only_not_monthly_route_traffic_or_complete_network",
        observed_flights_inferred=False,
        schedule_expanded_into_future_dates=False,
        news_or_evidence_activated=False,
    )
