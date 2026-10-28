"""AFAC airport-index discovery bound to its exact, fully replayed workbook.

Historical originals exercise discovery, never today's availability. Current
binding requires two actual same-day captures through the collection protocol.
"""

import hashlib
import json
import re
from pathlib import Path
from urllib.parse import urljoin, urlsplit

import pandas as pd
from bs4 import BeautifulSoup

from src.source_updates import afac_airports
from src.source_updates import availability as physical
from src.source_updates.calendar import local_time

ENTRY = "https://www.gob.mx/afac/acciones-y-programas/estadisticas-280404"
MONTHS = "ene feb mar abr may jun jul ago sep oct nov dic".split()
ENGLISH = "January February March April May June July August September October November December".split()
HEADING = "Estadística Operacional de Aeropuertos. Statistics by Airport"
TABLE = "silver/source_products/afac_airports.parquet"


def label(node):
    return " ".join(node.get_text(" ", strip=True).split())


def latest(index):
    """Select the exact workbook and period in the observed official airport row."""
    body = index if isinstance(index, bytes) else index.read_bytes()
    soup = BeautifulSoup(body.decode("utf-8"), "html.parser")
    titles = soup.find_all("h1")
    if soup.find("base", href=True) or len(titles) != 1 or label(titles[0]) != "Estadísticas":
        raise ValueError("AFAC airport index identity/base changed")
    links = []
    for link in soup.select("a[href]"):
        text, url = label(link), urljoin(ENTRY, link["href"])
        named_family = re.search(
            r"producto-aeropuertos?[-/]|estad[ií]stica.*aeropuertos|"
            r"statistics by airport|airports operational",
            url + " " + text,
            re.I,
        )
        airport_topic = re.search(r"\b(?:airports?|aeropuertos?)\b", text, re.I)
        report_topic = re.search(
            r"statistic|estad[ií]stic|operational|operacional|report|informe|bolet[ií]n", text, re.I
        )
        dated_or_document = re.search(r"\b20\d{2}\b", text) or re.search(
            r"\.(?:pdf|xlsx?|csv|zip|docx?|ods)$", urlsplit(url).path, re.I
        )
        if named_family or (airport_topic and report_topic and dated_or_document):
            physical.validate_url(url, ["www.gob.mx"])
            links.append((link, url, text))
    if len(links) != 3 or len({id(a.find_parent("tr")) for a, _, _ in links}) != 1:
        raise ValueError("AFAC airport index requires one exact workbook-and-two-PDF row")
    row = links[0][0].find_parent("tr")
    cells = row.find_all("td", recursive=False) if row else []
    headings = cells[0].find_all("p", recursive=False) if len(cells) == 1 else []
    if len(headings) != 1 or label(headings[0]) != HEADING:
        raise ValueError("AFAC airport table scope/layout changed")
    workbooks = [(url, text) for _, url, text in links if urlsplit(url).path.endswith(".xlsx")]
    if len(workbooks) != 1:
        raise ValueError("AFAC airport index requires one unambiguous XLSX edition")
    url, text = workbooks[0]
    match = re.fullmatch(
        r"https://www\.gob\.mx/cms/uploads/attachment/file/\d+/"
        r"producto-aeropuertos?-2006-(20\d{2})-([a-z]{3})-(\d{8})\.xlsx",
        url,
    )
    if (
        not match
        or match[2] not in MONTHS
        or text
        != (f"(Excel File) Estadística Operativa de Aeropuertos / Statistics by Airport 2006-{match[1]}")
    ):
        raise ValueError("AFAC airport workbook URL/title identity changed")
    year, month, edition = int(match[1]), MONTHS.index(match[2]) + 1, match[3]
    expected = {
        "es": "(PDF Español) Estadística Operacional de Aeropuertos - "
        f"{afac_airports.SPANISH[month - 1].title()} {year}",
        "en": f"(PDF English) Airports Operational Statistics - {ENGLISH[month - 1]} {year}",
    }
    seen = set()
    for _, pdf, title in links:
        if pdf == url:
            continue
        found = re.fullmatch(
            r"https://www\.gob\.mx/cms/uploads/attachment/file/\d+/"
            r"producto-aeropuertos-(es|en)-"
            + match[2]
            + "-"
            + f"{year % 100:02d}"
            + "-"
            + edition
            + r"\.pdf",
            pdf,
        )
        if not found or found[1] in seen or title != expected[found[1]]:
            raise ValueError("AFAC airport PDF labels/periods/editions disagree with the workbook")
        seen.add(found[1])
    if seen != {"es", "en"}:
        raise ValueError("AFAC airport index lacks its two corroborating language labels")
    return f"{year}M{month:02d}", url


def index_selection():
    """Plan the canonical index without fetching or inventing a workbook URL."""
    from src.source_updates.recipes import describe

    recipe = describe("afac_airports")
    if recipe["entry_url"] != ENTRY or recipe["state"] in {"disabled", "internal", "manual"}:
        raise ValueError("AFAC airport configured official entry changed")
    return {
        "version": 1,
        "items": [
            dict(
                id="afac-airports-catalog",
                product="afac_airports",
                source_system="afac",
                entity="afac_airports_catalog",
                period="current",
                purpose="catalog",
                url=ENTRY,
                extension="html",
                mode="get",
            )
        ],
    }


def select(index, requested="latest"):
    """Plan two GETs; an old input does not make this a current discovery."""
    body = index.read_bytes()
    period, url = latest(body)
    if requested not in {"latest", period}:
        raise ValueError("Requested AFAC airport month is not the observed official workbook edition")
    selection = index_selection()
    selection["discovery"] = dict(
        index_sha256=hashlib.sha256(body).hexdigest(),
        linked_period=period,
        basis="observed_index_link_not_current_availability_or_first_publication",
    )
    selection["items"].append(
        dict(
            id="afac-airports-workbook",
            product="afac_airports",
            source_system="afac",
            entity="airports_workbook",
            period=period,
            purpose="data",
            url=url,
            extension="xlsx",
            mode="get",
            relative_dir="afac/airports",
        )
    )
    return selection


def verified_body(path, row):
    body = path.read_bytes()
    if hashlib.sha256(body).hexdigest() != row["sha256"] or len(body) != row["bytes"]:
        raise ValueError("AFAC airport source changed before immutable-byte review")
    return body


def current_chronology(index, data, cutoff):
    """Apply the same-day contract to observed captures, never inferred releases."""
    first, last = (local_time(r["downloaded_at"]) for r in (index, data))
    as_of = local_time(cutoff)
    if first.date() != as_of.date() or last.date() != as_of.date() or not first <= last <= as_of:
        raise ValueError("AFAC airport discovery and workbook must be actual captures on the round date")


def verify(item, result, cutoff):
    if (item["product"], item["adapter"]) != ("afac_airports", "retained"):
        raise ValueError("AFAC airport discovery requires its complete retained-product adapter")
    binding = item["availability"]
    root = physical.preflight(binding, item["workspace"])
    if set(binding) != physical.FIELDS or binding["catalog_item"] == binding["artifact_item"]:
        raise ValueError("AFAC airports bind exactly one index and one distinct workbook")
    before = physical.collection_inventory(root)
    receipt_path = root / "receipts" / f"collection-{binding['run_id']}.json"
    receipt_sha = physical.sha(receipt_path)
    receipt = json.loads(receipt_path.read_text())
    expected = dict(
        run_id=binding["run_id"],
        mode="collection",
        status="collected_unvalidated",
        activation="none",
        publication="not_authorized",
    )
    if any(receipt.get(k) != v for k, v in expected.items()) or len(receipt.get("items", [])) != 2:
        raise ValueError("AFAC airports require a complete two-original collection receipt")
    chosen = []
    for field, status in (("catalog_item", "collected_catalog"), ("artifact_item", "collected_unvalidated")):
        rows = [r for r in receipt["items"] if r.get("id") == binding[field]]
        if len(rows) != 1 or rows[0].get("product") != "afac_airports" or rows[0].get("status") != status:
            raise ValueError("AFAC airport collection role/product/status changed")
        chosen.append(rows[0])
    index, data = chosen
    index_path, index_record = physical.artifact(
        root, index, cutoff, ["www.gob.mx"], receipt, {"afac", "route_research"}
    )
    data_path, data_record = physical.artifact(root, data, cutoff, ["www.gob.mx"], receipt, {"afac"})
    current_chronology(index_record, data_record, cutoff)
    if (
        any(index.get(k) != ENTRY for k in ("source_url", "response_url"))
        or index.get("requested_period") != "current"
    ):
        raise ValueError("AFAC airports require the exact official discovery URL/current role")
    period, url = latest(verified_body(index_path, index))
    if (
        period != item["period"]
        or data.get("requested_period") != period
        or any(data.get(k) != url for k in ("source_url", "response_url"))
        or local_time(index_record["downloaded_at"]) > local_time(data_record["downloaded_at"])
    ):
        raise ValueError("AFAC airport indexed month/artifact or collection chronology differs")
    frame, details = afac_airports.parse(verified_body(data_path, data), period, data_record)
    native = pd.read_parquet(Path(item["workspace"]) / "data" / TABLE)
    if len(native) != len(frame) or not set(frame.columns) <= set(native):
        raise ValueError("AFAC airport native scope differs from the complete workbook replay")
    try:
        pd.testing.assert_frame_equal(native[list(frame.columns)], frame, check_exact=True)
    except AssertionError as exc:
        raise ValueError("AFAC airport native observations differ from exact workbook replay") from exc
    if (
        result.get("status") != "checks_passed"
        or result.get("report_period") != period
        or result.get("months_validated") != details["months_validated"]
        or result.get("visible_crosschecks") != details["visible_crosschecks"]
        or result.get("rows") != len(frame)
        or max(frame.period_id) != period
        or physical.sha(receipt_path) != receipt_sha
        or physical.collection_inventory(root) != before
    ):
        raise ValueError("AFAC airport checked period/coverage or immutable collection changed")
    return dict(
        collection_receipt_sha256=receipt_sha,
        official_index_sha256=index["sha256"],
        source_artifact_sha256=data["sha256"],
        source_artifact_url=url,
        latest_available_period=period,
        source_availability_observed_at=data_record["downloaded_at"],
        round_as_of=cutoff,
        discovery_url=ENTRY,
        discovery_contract_product="afac_airports",
        physical_collection_files=before,
        reported_workbook_verified=True,
        complete_observational_census_claimed=False,
        first_publication_date=None,
        release_lag_days=None,
        scope="reported_airport_groups_excluding_official_state_operations_not_airline_network",
    )
