"""AM current index quarter + independently attributed official IR financial6-K.

The index announces a PDF; the native input is a separate official HTML format.
No direct index-to-HTML link, PDF byte equivalence or publication hour is claimed.
"""

import json
import re
from pathlib import Path
from urllib.parse import urljoin

import pandas as pd
from bs4 import BeautifulSoup

from src.source_updates import availability as physical
from src.source_updates.calendar import local_time
from src.source_updates.financials_html import DAY, PERIOD, URL, parse
from src.source_updates.retained import originals

INDEX = "https://ir.aeromexico.com/financial-information/quarterly-results"


def latest_quarter(path):
    soup = BeautifulSoup(path.read_bytes(), "html.parser")
    if soup.find("base", href=True):
        raise ValueError("AM quarterly index base URL changed")
    year, quarter, releases = None, None, {}
    for node in soup.find_all(["h2", "h3", "a"]):
        label = " ".join(node.get_text(" ", strip=True).split())
        if node.name == "h2":
            year = label if re.fullmatch(r"20\d{2}", label) else None
            quarter = None
        elif node.name == "h3":
            quarter = label if year and re.fullmatch(r"Q[1-4]", label) else None
        elif year and quarter and label == "Quarterly Earnings Release":
            url = urljoin(INDEX, node.get("href", ""))
            physical.validate_url(url, ["ir.aeromexico.com"])
            if not re.fullmatch(
                r"https://ir\.aeromexico\.com/(?:static-files/[0-9a-f-]{36}|system/files-encrypted/[^?#]+\.pdf)",
                url,
            ):
                raise ValueError("AM quarterly earnings index artifact format changed")
            releases.setdefault(year + quarter, set()).add(url)
    if not releases or any(len(urls) != 1 for urls in releases.values()):
        raise ValueError("AM quarterly index has missing or ambiguous earnings releases")
    period = max(releases)
    return period, next(iter(releases[period]))


def verify(item, result, cutoff):
    if item["product"] != "am_financials" or item["adapter"] != "retained" or item["period"] != PERIOD:
        raise ValueError("AM current financial HTML availability supports only reviewed2026Q3")
    binding = item["availability"]
    root = physical.preflight(binding, item["workspace"])
    if set(binding) != physical.FIELDS:
        raise ValueError("AM financial availability requires exact physical index/artifact fields")
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
    if any(receipt.get(k) != v for k, v in expected.items()):
        raise ValueError("AM financial discovery requires a complete immutable collection receipt")
    chosen = []
    for field, status in (("catalog_item", "collected_catalog"), ("artifact_item", "collected_unvalidated")):
        rows = [r for r in receipt.get("items", []) if r.get("id") == binding[field]]
        if len(rows) != 1 or rows[0].get("product") != "am_financials" or rows[0].get("status") != status:
            raise ValueError("AM financial index/native collection identity or status changed")
        chosen.append(rows[0])
    index, data = chosen
    index_path, index_row = physical.artifact(
        root, index, cutoff, ["ir.aeromexico.com"], receipt, {"aeromexico_ir"}
    )
    _, data_row = physical.artifact(root, data, cutoff, ["ir.aeromexico.com"], receipt, {"aeromexico_ir"})
    if (
        any(index.get(k) != INDEX for k in ("source_url", "response_url"))
        or index.get("requested_period") != "current"
        or index_row.get("logical_key") != "aeromexico_ir|am_financials_catalog|current|html"
        or any(data.get(k) != URL for k in ("source_url", "response_url"))
        or data.get("requested_period") != PERIOD
        or local_time(index_row["downloaded_at"]) > local_time(data_row["downloaded_at"])
    ):
        raise ValueError("AM financial canonical index/native identity or chronology changed")
    period, announced_pdf = latest_quarter(index_path)
    if period != PERIOD:
        raise ValueError("AM native financial quarter differs from latest official indexed earnings quarter")
    inputs, retained_sha = originals(Path(item["workspace"]), "am_financials", item["receipt_id"], cutoff)
    if (
        set(inputs) != {"html"}
        or inputs["html"][1] != data_row
        or result.get("retention_receipt_sha256") != retained_sha
    ):
        raise ValueError("AM current native HTML is not the exact physically retained collection original")
    frame, evidence = parse(inputs, PERIOD)
    if (
        result.get("status") != "checks_passed"
        or result.get("report_period") != PERIOD
        or result.get("source_report_date_as_reported") != DAY
        or result.get("source_unaudited") is not True
        or result.get("source_preliminary", "missing") is not None
        or result.get("financial_exhibit") != "99.1"
    ):
        raise ValueError("AM financial accepted result lacks its attributed financial report evidence")
    native_path = Path(item["workspace"]) / "data/silver/source_products/am_financials.parquet"
    native = pd.read_parquet(native_path)
    if len(native) != 20 or not set(frame.columns) <= set(native):
        raise ValueError("AM native financial scope must contain exactly the twenty source metrics")
    try:
        pd.testing.assert_frame_equal(native[list(frame.columns)], frame, check_exact=True)
    except AssertionError as exc:
        raise ValueError("AM financial native rows differ from exact official financial99.1 replay") from exc
    if physical.sha(receipt_path) != receipt_sha or physical.collection_inventory(root) != before:
        raise ValueError("AM financial physical discovery changed during verification")
    return dict(
        discovery_contract_product="am_financials",
        collection_receipt_sha256=receipt_sha,
        official_index_sha256=index["sha256"],
        source_artifact_sha256=data["sha256"],
        source_artifact_url=URL,
        discovery_url=INDEX,
        announced_pdf_url=announced_pdf,
        latest_available_period=period,
        source_report_date_as_reported=evidence["source_report_date_as_reported"],
        source_availability_observed_at=data_row["downloaded_at"],
        round_as_of=cutoff,
        availability_basis="current_official_index_quarter_and_attributed_official_IR_6K_financial_Ex99.1",
        direct_index_link_to_native_artifact=False,
        PDF_byte_equivalence_claimed=False,
        first_publication_date=None,
        release_lag_days=None,
        physical_collection_files=before,
    )
