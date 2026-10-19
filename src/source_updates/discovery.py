"""Resolve selected documents from preserved institutional catalogues."""

from pathlib import Path
import hashlib
import re
from urllib.parse import urljoin


def airport_selection(product: str, catalog_file: Path, period: str) -> dict:
    from bs4 import BeautifulSoup
    from src.source_updates.catalog import load_catalog, product_map
    from src.source_updates.collection import validate_url

    source = load_catalog()[product_map()[product]["source_key"]]
    english = "January February March April May June July August September October November December".split()
    spanish = (
        "enero febrero marzo abril mayo junio julio agosto septiembre octubre noviembre diciembre".split()
    )
    month_numbers = {name.lower(): i for names in (english, spanish) for i, name in enumerate(names, 1)}
    pattern = r"\b(" + "|".join(month_numbers) + r")(?:\s+de)?\s+(20\d{2})\b"
    candidates = {}
    for anchor in BeautifulSoup(catalog_file.read_bytes(), "lxml").select("a[href]"):
        title = " ".join(anchor.stripped_strings)
        matches_product = {
            "oma_traffic": "Total Passenger Traffic" in title,
            "aicm_traffic": "Estadísticas del AICM a" in title,
            "aifa_traffic": "Numeralia Aeroportuaria" in title and "Formato XLSX" in title,
        }[product]
        match = re.search(pattern, title, re.I)
        if not matches_product or match is None:
            continue
        found = f"{match.group(2)}M{month_numbers[match.group(1).lower()]:02d}"
        url = urljoin(source["official_page_url"], anchor["href"])
        candidates[(found, url)] = title
    if period == "latest" and candidates:
        period = max(key[0] for key in candidates)
    chosen = [(url, title) for (found, url), title in candidates.items() if found == period]
    if len(chosen) != 1:
        raise ValueError("Requested airport report absent or ambiguous in the actual catalogue")
    url, title = chosen[0]
    validate_url(url, source["allowed_hosts"])
    source_system, entity, extension, directory = {
        "oma_traffic": ("oma_ir", re.sub(r"\W+", "_", title).strip("_"), "pdf", "airports/oma"),
        "aicm_traffic": ("aicm", "traffic_statistics", "pdf", "airports/government"),
        "aifa_traffic": ("aifa", "airport_statistics", "xlsx", "airports/government"),
    }[product]
    return {
        "version": 1,
        "discovery": {
            "catalog_sha256": hashlib.sha256(catalog_file.read_bytes()).hexdigest(),
            "linked_period": period,
            "basis": "actual visible link; content still requires parsing",
        },
        "items": [
            {
                "id": f"{product}-{period}",
                "product": product,
                "source_system": source_system,
                "entity": entity,
                "period": period,
                "purpose": "data",
                "url": url,
                "extension": extension,
                "mode": "get",
                "relative_dir": directory,
            }
        ],
    }


def select_documents(product: str, catalog_file: Path, period: str, tickers=None) -> dict:
    if product == "am_traffic_ir":
        from src.source_updates.am_traffic import select

        return select(catalog_file, period)
    if product in {"oma_traffic", "aicm_traffic", "aifa_traffic"}:
        return airport_selection(product, catalog_file, period)
    if product == "bmv_xbrl":
        from src.source_updates.bmv import selection

        return selection(catalog_file, period, tuple(tickers or ["AERO", "VOLAR"]))
    if product == "afac_carriers":
        from src.ingest.afac.download import parse_datatur_catalog
        from src.source_updates.checks import period_end

        period_end(period)
        selected = [
            row for row in parse_datatur_catalog(catalog_file.read_bytes()) if row.period_id == period
        ]
        if len(selected) != 1 or selected[0].artifact_type != "datatur_monthly_bulletin":
            raise ValueError("Requested AFAC monthly bulletin absent or ambiguous in actual catalogue")
        row = selected[0]
        return {
            "version": 1,
            "items": [
                {
                    "id": f"afac-{period}",
                    "product": product,
                    "source_system": "afac",
                    "entity": "datatur_monthly_bulletin",
                    "period": period,
                    "purpose": "data",
                    "url": row.source_url,
                    "extension": row.extension,
                    "mode": "get",
                    "relative_dir": f"afac/{period[:4]}/{period[5:]}",
                }
            ],
        }
    raise ValueError("No catalogue-to-document selector for this product; follow its manual procedure")
