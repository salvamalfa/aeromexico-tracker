"""Physical OMA newsroom report for the most recently closed Mexico month.

This proves availability of the requested report, not a census of all revisions
across OMA's sites. The original IR-index contract remains a separate option.
"""

import calendar
import json
import re
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import urljoin, urlsplit

import pandas as pd
from bs4 import BeautifulSoup

from src.source_updates import availability as physical
from src.source_updates.calendar import local_time
from src.source_updates.oma_traffic import TABLE, parse
from src.transform.stage9_lineage import add_record_ids

SCOPE = "oma_official_newsroom_v1"
HOST = "news.oma.aero"


def latest_closed_month(cutoff):
    previous = local_time(cutoff).date().replace(day=1) - timedelta(days=1)
    return f"{previous.year}M{previous.month:02d}"


def official_url(url, kind):
    parts = urlsplit(url)
    pattern = r"/news/[a-z0-9-]+\.html" if kind == "news" else r"/assets/[a-z0-9-]+\.html"
    if (
        parts.scheme != "https"
        or parts.netloc != HOST
        or not re.fullmatch(pattern, parts.path)
        or parts.fragment
        or parts.query != ("" if kind == "news" else "dl=1")
    ):
        raise ValueError("OMA newsroom requires its exact official hostname and document route")
    return url


def discover(path, url):
    official_url(url, "news")
    soup = BeautifulSoup(path.read_bytes(), "html.parser")
    if soup.find("base", href=True):
        raise ValueError("OMA newsroom base URL changed")
    titles, dates = soup.select("h1.section-title"), soup.select(".section-subtitle-date")
    if len(titles) != 1 or len(dates) != 1:
        raise ValueError("OMA newsroom report title/date absent or ambiguous")
    title = " ".join(titles[0].get_text(" ", strip=True).split())
    match = re.fullmatch(
        r"OMA reports a \d+(?:\.\d+)?% (?:increase|decrease) in ([A-Za-z]+) (20\d{2}) passenger traffic",
        title,
    )
    if not match or match[1] not in calendar.month_name:
        raise ValueError("OMA newsroom traffic month/title changed")
    period = f"{match[2]}M{list(calendar.month_name).index(match[1]):02d}"
    day = datetime.strptime(dates[0].get_text(strip=True), "%d %B %Y").date().isoformat()
    urls = {
        urljoin(url, a["href"])
        for a in soup.select("a[href]")
        if " ".join(a.get_text(" ", strip=True).split()) == "Download PDF"
    }
    # The observed page repeats the same download in two buttons.
    if len(urls) != 1:
        raise ValueError("OMA newsroom PDF link absent or ambiguous")
    return period, official_url(urls.pop(), "pdf"), day


def selection(url, period=None, catalog=None):
    """Prepare literal official URLs without network requests or URL guessing."""
    official_url(url, "news")
    items = [
        dict(
            id="oma-newsroom",
            product="oma_traffic",
            source_system="oma_ir",
            entity="oma_newsroom",
            period="current",
            purpose="catalog",
            url=url,
            extension="html",
            mode="get",
        )
    ]
    if catalog is not None:
        selected, pdf, _ = discover(catalog, url)
        if period not in (selected, "latest"):
            raise ValueError("OMA newsroom requested month differs from the actual article")
        items.append(
            dict(
                id="oma-newsroom-pdf",
                product="oma_traffic",
                source_system="oma_ir",
                entity="traffic_report",
                period=selected,
                purpose="data",
                url=pdf,
                extension="pdf",
                mode="get",
                relative_dir="airports/oma",
            )
        )
    return dict(version=1, items=items)


def preflight(binding, candidate):
    if not isinstance(binding, dict) or set(binding) != physical.FIELDS | {"source_scope"}:
        raise ValueError("OMA newsroom requires exact scoped physical collection fields")
    if binding["source_scope"] != SCOPE or binding["catalog_item"] == binding["artifact_item"]:
        raise ValueError("OMA newsroom requires distinct discovery and PDF roles")
    return physical.preflight({k: v for k, v in binding.items() if k != "source_scope"}, candidate)


def verify(item, result, cutoff):
    if (item["product"], item["adapter"]) != ("oma_traffic", "retained"):
        raise ValueError("OMA newsroom discovery cannot certify a different product or adapter")
    binding = item["availability"]
    root = preflight(binding, item["workspace"])
    inventory = physical.collection_inventory(root)
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
        raise ValueError("OMA newsroom requires one complete two-original collection")
    chosen = []
    for field, status in (("catalog_item", "collected_catalog"), ("artifact_item", "collected_unvalidated")):
        rows = [r for r in receipt["items"] if r.get("id") == binding[field]]
        if len(rows) != 1 or rows[0].get("product") != "oma_traffic" or rows[0].get("status") != status:
            raise ValueError("OMA newsroom collection role/product/status differs")
        chosen.append(rows[0])
    index, data = chosen
    index_path, index_record = physical.artifact(root, index, cutoff, [HOST], receipt, {"oma_ir"})
    data_path, data_record = physical.artifact(root, data, cutoff, [HOST], receipt, {"oma_ir"})
    period, url, day = discover(index_path, index["source_url"])
    latest_closed = latest_closed_month(cutoff)
    if (
        period != item["period"]
        or period != latest_closed
        or index.get("requested_period") != "current"
        or index["response_url"] != index["source_url"]
        or data.get("requested_period") != period
        or any(data.get(k) != url for k in ("source_url", "response_url"))
        or local_time(index_record["downloaded_at"]) > local_time(data_record["downloaded_at"])
    ):
        raise ValueError("OMA newsroom must bind the latest closed month and literal paired PDF")
    frame, details = parse({"pdf": (data_path.read_bytes(), data_record)}, period)
    frame = add_record_ids(
        frame,
        table_name=TABLE,
        natural_key_columns=["source_hash", "source_locator", "parser_version", "period_id", "metric_key"],
    )
    native = pd.read_parquet(Path(item["workspace"]) / "data/silver/source_products/oma_traffic.parquet")
    if set(native) != set(frame):
        raise ValueError("OMA newsroom native schema differs from complete source replay")
    try:
        pd.testing.assert_frame_equal(native[list(frame)], frame, check_exact=True)
    except AssertionError as exc:
        raise ValueError("OMA newsroom native observations differ from exact PDF replay") from exc
    if (
        result.get("complete_month_certified") is not True
        or details["source_report_date_as_reported"] != day
        or result.get("source_report_date_as_reported") != day
        or physical.collection_inventory(root) != inventory
    ):
        raise ValueError("OMA newsroom report date, completeness or immutable source binding differs")
    return dict(
        discovery_contract_product="oma_traffic",
        source_scope=SCOPE,
        collection_receipt_sha256=receipt_sha,
        official_index_sha256=index["sha256"],
        source_artifact_sha256=data["sha256"],
        source_artifact_url=url,
        discovery_url=index["source_url"],
        latest_available_period=period,
        source_availability_observed_at=data_record["downloaded_at"],
        round_as_of=cutoff,
        source_report_date_as_reported=day,
        availability_basis="official_newsroom_report_for_most_recently_closed_month",
        all_sites_latest_revision_census=False,
        first_publication_date=None,
        publication_time=None,
        release_lag_days=None,
        physical_collection_files=inventory,
    )
