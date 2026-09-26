"""Checks that the already-assembled, gate-signed ``site/`` (P6b) still
matches its own sources of truth.

P7 retired ``static/aeromexico_tracker.html`` (the Streamlit-served copy of
the legacy integrated HTML) and, with it, the whole "compare two rendered
pages" style this file and ``tests/test_web_page_parity.py``/
``tests/test_web_flights_parity.py`` used before -- there is no second page
left to compare against. This now checks ``site/`` against its own inputs
instead:

- ``test_site_flights_and_executive_data_match_a_fresh_export`` (no
  browser): the Vuelos/executive data already committed under
  ``site/data/v1/`` equals a fresh ``src.web_export`` run over the current
  warehouse -- the snapshot-equality check the P7 package asked for in
  place of the old cross-page comparison.
- The Playwright tests below render ``site/`` alone and check what it shows
  against the real payloads directly (``executive_payload``/the local
  ledger's approved analysis), not against a second render.

Requires ``site/`` to already exist and pass ``src.publish.verify`` (skips
with a clear reason otherwise -- run
``python -m src.publish --record ... --out site/`` first, an
owner-authorized step, see ``src/publish/README.md``).
"""

from __future__ import annotations

import json
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from src.analysis_agent import lifecycle as flow
from src.publish.verify import verify_site
from src.web_export.analysis import MissingAnalysisInput, discover_approved_manifest, export_period
from src.web_export.executive import export_executive
from src.web_export.flights import export_flights, recombine_flights

pytestmark = pytest.mark.local_data

SITE_DIR = Path(__file__).resolve().parent.parent / "site"
DATA_DIR = SITE_DIR / "data" / "v1"
READER_KPI_KEYS = ("rask_cents_per_km", "cask_cents_per_km", "ask_km")


def _require_site() -> None:
    if not SITE_DIR.is_dir():
        pytest.skip(f"{SITE_DIR} does not exist; run `python -m src.publish --record ... --out site/` first")
    problems = verify_site(SITE_DIR)
    if problems:
        pytest.skip(f"{SITE_DIR} fails src.publish.verify: {problems[:3]}")


def test_site_flights_and_executive_data_match_a_fresh_export(
    tmp_path: Path, flight_payload: dict, executive_payload: dict
) -> None:
    """``site/data/v1`` is exactly what exporting the current warehouse gives."""

    _require_site()
    out_dir = tmp_path / "data" / "v1"
    export_flights(flight_payload, out_dir, skip_input_check=True)
    export_executive(executive_payload, out_dir, skip_input_check=True)

    assert recombine_flights(out_dir) == recombine_flights(DATA_DIR)
    fresh_executive = json.loads((out_dir / "executive.json").read_text(encoding="utf-8"))
    site_executive = json.loads((DATA_DIR / "executive.json").read_text(encoding="utf-8"))
    assert fresh_executive == site_executive

    for analysis_path in sorted((DATA_DIR / "analysis").glob("*.json")):
        period_id = analysis_path.stem
        site_analysis = json.loads(analysis_path.read_text(encoding="utf-8"))
        try:
            fresh_analysis = export_period(period_id, site_analysis["version"], root=flow.ROOT)
        except MissingAnalysisInput as error:
            pytest.skip(f"{period_id}/{site_analysis['version']} no longer approved locally: {error}")
        assert fresh_analysis == site_analysis


# ---------------------------------------------------------------------------
# Browser checks against site/ alone
# ---------------------------------------------------------------------------

playwright_sync_api = pytest.importorskip("playwright.sync_api")
sync_playwright = playwright_sync_api.sync_playwright

browser_test = pytest.mark.browser


def _chromium_executable() -> str | None:
    candidate = Path("/opt/pw-browsers/chromium-1194/chrome-linux/chrome")
    return str(candidate) if candidate.exists() else None


@pytest.fixture(scope="module")
def site_server():
    _require_site()
    handler = partial(SimpleHTTPRequestHandler, directory=str(SITE_DIR))
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}/"
    finally:
        server.shutdown()
        thread.join()


@pytest.fixture(scope="module")
def site_page(site_server):
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(executable_path=_chromium_executable())
        page = browser.new_page()
        page.route("**/favicon.ico", lambda route: route.fulfill(status=204, body=""))
        page.goto(site_server)
        page.wait_for_function("document.getElementById('period-display').textContent !== '—'")
        yield page
        browser.close()


def _text(page, selector: str) -> str | None:
    return page.evaluate(
        "(selector) => { const el = document.querySelector(selector); "
        "return el ? el.innerText.replace(/\\s+/g, ' ').trim() : null; }",
        selector,
    )


def _kpi_values(page) -> dict[str, str]:
    return {key: page.inner_text(f"#kpi-{key}-value") for key in READER_KPI_KEYS} | {
        "unit_margin_cents_per_km": page.inner_text("#kpi-unit_margin_cents_per_km-value")
    }


def _period_ids(executive_payload: dict) -> list[str]:
    return [record["period_id"] for record in executive_payload["records"]]


@browser_test
def test_reader_tabs_switch_panels_on_the_site(site_page) -> None:
    for tab_id, panel_id in (("tab-economy", "panel-economy"), ("tab-flights", "panel-flights"), ("tab-reading", "panel-reading")):
        site_page.click(f"#{tab_id}")
        assert site_page.is_visible(f"#{panel_id}")
        assert site_page.get_attribute(f"#{tab_id}", "aria-selected") == "true"


@browser_test
def test_economy_tab_kpis_match_the_underlying_payload_for_every_quarter(
    site_page, executive_payload: dict
) -> None:
    """The economy tab's KPI cards show exactly the payload's own display
    values -- rask/cask/ask are pre-formatted server-side
    (``executive_summary.py``'s ``_display_value``); the margin card is the
    one KPI computed client-side, from the same record's raw field."""

    site_page.click("#tab-economy")
    while site_page.is_enabled("#period-next"):
        site_page.click("#period-next")
    views = executive_payload["views"]
    records = {record["period_id"]: record for record in executive_payload["records"]}
    period_ids = _period_ids(executive_payload)
    for period_id in reversed(period_ids):
        site_page.wait_for_function(
            "(id) => document.getElementById('narrative-copy').dataset.period === id", arg=period_id
        )
        view = views[period_id]
        kpis_by_key = {item["key"]: item for item in view["kpis"]}
        observed = _kpi_values(site_page)
        for key in READER_KPI_KEYS:
            assert observed[key] == kpis_by_key[key]["display_value"], f"{key} mismatch at {period_id}"
        margin = records[period_id]["unit_margin_cents_per_km"]
        expected_margin = f"{'+' if margin >= 0 else ''}{margin:.2f} ¢ USD"
        assert observed["unit_margin_cents_per_km"] == expected_margin, f"margin mismatch at {period_id}"
        if site_page.is_enabled("#period-prev"):
            site_page.click("#period-prev")


@browser_test
def test_reading_tab_narrative_matches_the_approved_analysis(site_page) -> None:
    """For every period the local ledger currently has approved/published,
    the reading tab's narrative text contains that exact approved thesis
    and every summary item -- read straight from the ledger, not from a
    second render."""

    manifest = discover_approved_manifest(flow.ROOT)
    if not manifest:
        pytest.skip("No period is currently approved/published in this checkout's local analysis_runs/")
    expected = {}
    for entry in manifest:
        try:
            expected[entry["period_id"]] = export_period(entry["period_id"], entry["version"], root=flow.ROOT)
        except MissingAnalysisInput as error:
            pytest.skip(f"{entry}: {error}")

    site_page.click("#tab-reading")
    while site_page.is_enabled("#period-next"):
        site_page.click("#period-next")
    checked: set[str] = set()
    while True:
        period_id = site_page.evaluate("document.getElementById('narrative-copy').dataset.period")
        if period_id in expected:
            analysis = expected[period_id]
            text = _text(site_page, "#narrative-copy")
            assert analysis["thesis"] in text, period_id
            for item in analysis["summary_items"]:
                assert item["text"] in text, (period_id, item["claim_id"])
            checked.add(period_id)
        if not site_page.is_enabled("#period-prev"):
            break
        site_page.click("#period-prev")
        site_page.wait_for_function(
            "(id) => document.getElementById('narrative-copy').dataset.period !== id", arg=period_id
        )
    assert checked == set(expected), f"never reached {set(expected) - checked}"
