"""Latest advertised AICM/OMA report from their reviewed physical indexes."""

import re
from urllib.parse import urljoin, urlsplit

from bs4 import BeautifulSoup

from src.source_updates.catalog import load_catalog, product_map
from src.source_updates.collection import validate_url
from src.source_updates.recipes import describe

ENGLISH = "January February March April May June July August September October November December".split()
SPANISH = "enero febrero marzo abril mayo junio julio agosto septiembre octubre noviembre diciembre".split()
OMA_ARCHIVE = (
    "https://ir.oma.aero/wp-content/uploads/2021/11/OMAB_News_2007_1_10_Press_Releases.pdf",
    "OMA passenger traffic grew 17.8% in December and 11.2% during 2006",
)


def latest(index, product):
    if product not in {"aicm_traffic", "oma_traffic"}:
        raise ValueError("No reviewed airport discovery contract for this product")
    source = load_catalog()[product_map()[product]["source_key"]]
    entry = describe(product)["entry_url"]
    soup = BeautifulSoup(index.read_bytes(), "html.parser")
    if soup.find("base", href=True):
        raise ValueError("Institutional airport index base changed")
    rows = [
        (urljoin(entry, a["href"]), " ".join(a.get_text(" ", strip=True).split()))
        for a in soup.select("a[href]")
    ]
    known, relevant = {}, set()
    for url, title in rows:
        folded, path = title.casefold(), urlsplit(url).path.casefold()
        document = path.endswith((".pdf", ".xlsx", ".zip"))
        dated = re.search(r"\b20\d{2}\b", folded) is not None
        # Detect the broader subject before parsing its reviewed grammar. A new
        # title or opaque download URL must not hide a newer report.
        is_doc = (
            bool(re.search(r"estad[ií]sticas.*\baicm\b", folded))
            and (document or dated)
            or "/estadisticas/" in path
            if product == "aicm_traffic"
            else "traffic" in folded and (document or dated) or ("traffic" in path and document)
        )
        if not is_doc:
            continue
        relevant.add(url)
        if not title:
            continue  # paired download icons must resolve to a named link below
        if product == "oma_traffic" and (url, title) == OMA_ARCHIVE:
            # Exact archived entry observed in the same official index; never
            # infer a report period from the upload folder's 2021 date.
            known.setdefault(url, set()).add("2006M12")
            continue
        pattern = (
            r"Estadísticas del AICM a ([A-Za-z]+) de (20\d{2})"
            if product == "aicm_traffic"
            else r"OMA['’´]s ([A-Za-z]+) (20\d{2}) Total Passenger Traffic"
            r"(?: (?:increases|decreases) \d+(?:\.\d+)?%)?"
        )
        match = re.fullmatch(pattern, title, re.I)
        names = SPANISH if product == "aicm_traffic" else [s.lower() for s in ENGLISH]
        if not match or match[1].lower() not in names or not path.endswith(".pdf"):
            raise ValueError("Relevant airport document has an unreviewed title/month/format")
        validate_url(url, source["allowed_hosts"])
        period = f"{match[2]}M{names.index(match[1].lower()) + 1:02d}"
        known.setdefault(url, set()).add(period)
    if not known or relevant != set(known):
        raise ValueError("Airport index has missing or unclassified relevant document links")
    period = max(p for periods in known.values() for p in periods)
    chosen = [url for url, periods in known.items() if period in periods]
    # Old, explicitly dated index mistakes cannot supply this current report.
    # The chosen latest URL itself must identify exactly one period.
    if len(chosen) != 1 or known[chosen[0]] != {period}:
        raise ValueError("Latest advertised airport reporting period is ambiguous")
    return period, chosen[0]
