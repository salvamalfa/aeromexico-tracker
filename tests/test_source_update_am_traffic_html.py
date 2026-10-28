"""Synthetic HTML contracts plus PDF-path regression; actual captures are checked separately."""

import hashlib
import json
import re
import shutil
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import httpx
import pandas as pd
import pytest
from bs4 import BeautifulSoup, Tag

from src.source_updates import am_traffic, availability, readiness
from src.source_updates import am_traffic_candidate as candidate
from src.source_updates import am_traffic_html as source
from src.source_updates.catalog import ROOT
from src.source_updates.collection import collect
from src.source_updates.recipes import catalog_selection
from tests.test_source_update_am_traffic import CURRENT_INDEX, ORIGINAL, TEXT
from tests.test_source_update_financials_html import report as financial_fixture

COMPARE = [
    "period_id",
    "metric_key",
    "segment",
    "value_raw",
    "unit_raw",
    "scale_multiplier",
    "value_normalized",
    "unit_normalized",
    "service_scope",
]


def body():
    soup = BeautifulSoup(financial_fixture(), "html.parser")
    cover = soup.select_one("#block-client-site-content").find("html", recursive=False)
    row = next(
        r for r in cover.find_all("tr") if r.find("td") and r.find("td").get_text(strip=True) == "99.4"
    )
    row.find_all("td")[
        -1
    ].a.string = "Press Release dated October 6, 2026, titled “Aeroméxico September 2026 Traffic Results.”"
    anchor = soup.find("a", attrs={"name": "aeromxicoseptembertrafficr.htm"})
    document = next(n for n in anchor.parent.next_siblings if isinstance(n, Tag))
    document.body.clear()
    intro = soup.new_tag("p")
    intro.string = (
        "Aeroméxico September 2026 Traffic Results Mexico City, Mexico, October 6, 2026 – "
        "Grupo Aeroméxico S.A.B. de C.V. reports its September 2026 operational results. "
        "Figures may not sum to total due to rounding. The information has not been audited."
    )
    document.body.append(intro)
    glossary = soup.new_tag("p")
    glossary.string = (
        "Glossary: Revenue Passenger Miles represent one revenue-passenger transported one mile. "
        "This includes itinerary and charter flights. "
        "Available Seat Miles represent the number of available seats multiplied by the distance flown. "
        "It equals one seat offered for one mile, whether the seat is used. "
        "This metric considers the total passengers transported and total seats available "
        "in itinerary flights only."
    )
    document.body.append(glossary)
    table = soup.new_tag("table")
    table.append(
        BeautifulSoup(
            '<tr><td colspan="3"></td><td colspan="9">September</td>'
            '<td colspan="9">Cumulative to September</td></tr>',
            "html.parser",
        ).tr
    )

    def seven(values):
        tr = soup.new_tag("tr")
        for value in values:
            td = soup.new_tag("td", colspan="3")
            td.string = value
            tr.append(td)
        table.append(tr)

    seven(["", "2026", "2025", "Var.", "2026", "2025", "Var."])
    section = None
    for line in TEXT.splitlines():
        match = re.fullmatch(
            r"(?:(Passengers|ASMs|RPMs|Load Factor) )?(Domestic|International|Total) (.+)", line
        )
        if not match:
            continue
        if match[1]:
            section = match[1]
            heading = {
                "Passengers": "Passengers (itinerary + charter, thousands)",
                "ASMs": "ASMs (itinerary + charter, millions)",
                "RPMs": "RPMs (itinerary + charter, millions)",
                "Load Factor": "Load Factor (itinerary, %)",
            }[section]
            seven([heading, "", "", "", "", "", ""])
        values = match[3].split()
        if section == "Load Factor":
            values = [
                values[0],
                values[1],
                values[2] + " " + values[3],
                values[4],
                values[5],
                values[6] + " " + values[7],
            ]
        seven([match[2], *values])
    document.body.append(table)
    return str(soup).encode()


def original(raw):
    return dict(
        source_system="aeromexico_ir",
        source_file="synthetic/september6k.html",
        source_url=source.URL,
        logical_key=source.KEY,
        sha256=hashlib.sha256(raw).hexdigest(),
        downloaded_at="2026-10-27T14:46:19Z",
    )


def parse(raw):
    return source.parse(raw, "2026M09", original(raw))


def test_native_matches_all_twentyfour_pdf_tuples_without_ytd_or_unknown_coercion():
    frame, result = parse(body())
    pdf, _ = am_traffic.parse(TEXT, "2026M09", ORIGINAL)
    pd.testing.assert_frame_equal(frame[COMPARE], pdf[COMPARE], check_exact=True)
    assert frame.is_preliminary.isna().all() and frame.source_page.isna().all()
    assert frame.source_locator.str.startswith("exhibit:99.4/").all()
    assert result["published_date"] == result["source_report_date_as_reported"] == "2026-10-06"
    assert result["source_preliminary"] is None and result["source_preliminary_status"] == "not_stated"
    assert result["first_publication_date"] is result["release_lag_days"] is None
    assert (
        result["monthly_rows"] == result["comparative_rows"] == 12 and result["cumulative_rows_imported"] == 0
    )


def test_scope_month_units_column_order_and_incomplete_grid_fail_closed():
    raw = body().decode()
    for old, new in (
        ('name="aeromxicoseptembertrafficr.htm"', 'name="wrong.htm"'),
        ("October 6, 2026", "October 19, 2026"),
        ("reports its September 2026", "reports its August 2026"),
        ("Grupo Aeroméxico, S.A.B. de C.V.", "Other issuer"),
        (">September</td>", ">Cumulative to September</td>"),
        ('>2026</td><td colspan="3">2025', '>2025</td><td colspan="3">2026'),
        ("itinerary + charter, thousands", "itinerary + charter, millions"),
        ("Load Factor (itinerary, %)", "Load Factor (itinerary + charter, %)"),
        (">1,226<", ">NaN<"),
        (">1,226<", ">9,226<"),
        (">85.9%<", ">185.9%<"),
        (
            "has not been audited.",
            "has not been audited. The September figures presented here are preliminary.",
        ),
        ("has not been audited.", "has not been audited. ASM/RPM values are expressed in kilometres."),
        (
            "It equals one seat offered for one mile, whether the seat is used.",
            "Capacity is reported in ASMs.",
        ),
    ):
        assert old in raw
        with pytest.raises(ValueError):
            parse(raw.replace(old, new).encode())
    soup = BeautifulSoup(body(), "html.parser")
    table = next(t for t in soup.find_all("table") if "Cumulative to September" in t.get_text())
    tr = next(
        r for r in table.find_all("tr") if r.find("td") and r.find("td").get_text(strip=True) == "Domestic"
    )
    tr.insert_after(deepcopy(tr))
    with pytest.raises(ValueError, match="duplicated"):
        parse(str(soup).encode())
    soup = BeautifulSoup(body(), "html.parser")
    table = next(t for t in soup.find_all("table") if "Cumulative to September" in t.get_text())
    caption = soup.new_tag("caption")
    caption.string = "All passenger figures in this table are in millions"
    table.insert(0, caption)
    with pytest.raises(ValueError, match="caption/unit declaration"):
        parse(str(soup).encode())
    with pytest.raises(ValueError, match="September2026"):
        source.parse(body(), "2026M08", original(body()))
    wrong = original(body())
    wrong["logical_key"] = "aeromexico_ir|am_financials_2026Q3_6K|2026Q3|html"
    with pytest.raises(ValueError, match="actual monthly IR identity"):
        source.parse(body(), "2026M09", wrong)


@pytest.fixture
def physical():
    root = ROOT / "tmp/source-updates" / ("am-traffic-html-test-" + uuid4().hex)
    collection, workspace = root / "collection", root / "candidate"

    class Client:
        def __init__(self, *args, **kw):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def request(self, method, url, **kw):
            return httpx.Response(
                200,
                content=CURRENT_INDEX.encode() if url == am_traffic.ENTRY else body(),
                request=httpx.Request(method, url),
            )

    selection = catalog_selection("am_traffic_ir")
    selection["items"].append(
        dict(
            id="monthly-6k",
            product="am_traffic_ir",
            source_system="aeromexico_ir",
            entity="am_traffic_ir_2026M09_6K",
            period="2026M09",
            extension="html",
            purpose="data",
            url=source.URL,
        )
    )
    try:
        receipt = collect(selection, collection, execute=True, client_factory=Client)
        shutil.copytree(collection, workspace)
        cutoff = (datetime.now(UTC) + timedelta(seconds=1)).isoformat()
        yield root, collection, workspace, receipt["run_id"], cutoff
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_integral_html_and_availability_preserve_observed_gold_flag_and_replay(physical):
    root, collection, workspace, run, cutoff = physical
    result = candidate.run(workspace, "2026M09", cutoff, run, execute=True)
    assert result["lineage"]["status"] == "passed" and result["complete_month_certified"]
    native = pd.read_parquet(workspace / "data/silver/aeromexico_ir_monthly_metrics.parquet")
    facts = pd.read_parquet(workspace / "data/gold/fact_carrier_metrics.parquet")
    assert native.is_preliminary.isna().all() and not facts.is_preliminary.any()
    notes = pd.read_parquet(workspace / "data/gold/bridge_record_lineage.parquet").lineage_note
    assert notes.str.contains("not confirmation of finality").all()
    before = readiness.inventory(workspace)
    assert (
        candidate.run(workspace, "2026M09", cutoff, run, check=True)["output_sha256"]
        == result["output_sha256"]
    )
    item = dict(
        id="traffic",
        product="am_traffic_ir",
        adapter="am_traffic_ir",
        period="2026M09",
        workspace=str(workspace),
        receipt_id=run,
        required=True,
        candidate_as_of=cutoff,
        availability=dict(
            workspace=str(collection),
            run_id=run,
            catalog_item="am_traffic_ir-catalog",
            artifact_item="monthly-6k",
        ),
    )
    bound = availability.verify(item, result, cutoff)
    assert (
        bound["latest_available_period"] == "2026M09"
        and bound["source_report_date_as_reported"] == "2026-10-06"
    )
    assert (
        not bound["PDF_byte_equivalence_claimed"] and not bound["financial_cover_date_used_as_traffic_date"]
    )
    assert readiness.check_task(item, cutoff, cutoff)["latest_source_availability_verified"]
    assert readiness.inventory(workspace) == before
    forged = {**result, "source_report_date_as_reported": "2026-10-19"}
    with pytest.raises(ValueError, match="unknown preliminary status"):
        availability.verify(item, forged, cutoff)
    with pytest.raises(ValueError, match="explicit round date"):
        availability.verify(item, result, (datetime.fromisoformat(cutoff) + timedelta(days=1)).isoformat())


def test_pair_binding_body_integrity_and_tampered_native_cannot_claim_current(physical):
    root, collection, workspace, run, cutoff = physical
    result = candidate.run(workspace, "2026M09", cutoff, run, execute=True)
    item = dict(
        product="am_traffic_ir",
        adapter="am_traffic_ir",
        period="2026M09",
        workspace=str(workspace),
        receipt_id=run,
        availability=dict(
            workspace=str(collection),
            run_id=run,
            catalog_item="am_traffic_ir-catalog",
            artifact_item="monthly-6k",
        ),
    )
    native = workspace / "data/silver/aeromexico_ir_monthly_metrics.parquet"
    saved = native.read_bytes()
    f = pd.read_parquet(native)
    f.loc[0, "value_raw"] += 1
    f.to_parquet(native)
    with pytest.raises(ValueError, match="exact physical99.4"):
        availability.verify(item, result, cutoff)
    native.write_bytes(saved)
    path = collection / "receipts" / f"collection-{run}.json"
    content = json.loads(path.read_text())
    content["items"][-1]["product"] = "am_financials"
    path.write_text(json.dumps(content))
    with pytest.raises(ValueError, match="role/product/status"):
        availability.verify(item, result, cutoff)
