"""Viva monthly traffic entries in the actual BMV issuer table, never XBRL ZIPs."""

import re
from datetime import datetime
from urllib.parse import urljoin, urlsplit

from bs4 import BeautifulSoup

from src.source_updates.collection import validate_url

ENTRY = "https://www.bmv.com.mx/es/emisoras/eventosrelevantes/GVIVA-34292-CGEN_DEUD"
MONTHS = "enero febrero marzo abril mayo junio julio agosto septiembre octubre noviembre diciembre".split()


def latest(index, requested="latest"):
    soup = BeautifulSoup(index.read_bytes(), "html.parser")
    profiles = soup.select(".info-profile")
    if len(profiles) != 1:
        raise ValueError("BMV Viva issuer identity/profile not established uniquely")
    names, keys = profiles[0].select("h3"), profiles[0].select(".key")
    if (
        soup.find("base", href=True)
        or len(names) != 1
        or len(keys) != 1
        or " ".join(names[0].get_text(" ", strip=True).split()) != "GRUPO VIVA AEROBUS SA DE CV"
        or keys[0].get_text(" ", strip=True) != "GVIVA"
    ):
        raise ValueError("BMV Viva issuer identity/base not established")
    periods = {}
    for row in soup.select("tr"):
        if not re.search(r"tr[áa]fico", row.get_text(" ", strip=True), re.I):
            continue
        cells = row.find_all("td", recursive=False)
        if len(cells) != 3:
            raise ValueError("Unreviewed Viva traffic table row layout")
        title = " ".join(cells[1].get_text(" ", strip=True).split())
        match = re.fullmatch(
            r"VIVA(?: AEROBUS)? REPORTA RESULTADOS "
            r"(?:DE TR[ÁA]FICO MENSUAL(?: DE)?|MENSUALES DE TR[ÁA]FICO(?: DE| -)) "
            r"([A-Z]+)(?: Y ANUAL)? (20\d{2})(?: \(fe de erratas\))?",
            title,
            re.I,
        )
        if not match or match[1].lower() not in MONTHS:
            raise ValueError("Unreviewed Viva monthly traffic title/table")
        # Preserve the unzoned portal clock as an observation, not a publication instant.
        datetime.strptime(cells[0].get_text(" ", strip=True), "%d-%m-%Y %H:%M")
        period = f"{match[2]}M{MONTHS.index(match[1].lower()) + 1:02d}"
        links = {
            urljoin(ENTRY, a["href"])
            for a in cells[2].select("a[href]")
            if urlsplit(a["href"]).path.lower().endswith(".pdf")
        }
        if len(links) != 1:
            raise ValueError("Viva traffic entry requires one PDF, never an XBRL/viewer substitute")
        url = links.pop()
        validate_url(url, ["bmv.com.mx"])
        if not re.fullmatch(r"/docs-pub/eventemi/eventemi_\d+_\d+\.pdf", urlsplit(url).path):
            raise ValueError("Unreviewed BMV Viva PDF location")
        periods.setdefault(period, set()).add(url)
    if not periods:
        raise ValueError("No monthly Viva traffic reports in official BMV issuer table")
    period = max(periods) if requested == "latest" else requested
    if period not in periods:
        raise ValueError("Requested Viva traffic month absent from official BMV issuer table")
    if len(periods[period]) != 1:
        raise ValueError(
            "Latest Viva traffic period has multiple editions; explicit revision review required"
        )
    return period, next(iter(periods[period]))
