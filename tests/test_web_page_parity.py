"""Playwright parity between the published integrated page
(``static/aeromexico_tracker.html``) and the full ``web/`` page (P4b) —
tab switching, the reading tab's narrative for every quarter, and the
economy tab's KPIs and chart data, over the full quarter matrix.

Both pages render output derived from the same generators
(``src.dashboard.executive_summary.build_executive_payload()`` and, for the
reading tab, ``src.analysis_agent.lifecycle.consumer_payload()`` via
``src.web_export.analysis``); this test proves the ES-module split changed
nothing visible, with one accepted, documented exception: the published
page adds a superscript citation link next to some numbers (built from
private evidence data — see ``src/analysis_agent/reader_ui.py::cite`` — that
``consumer_payload`` does not export). Every text comparison below strips
those ``<sup>`` citation markers from the published side before comparing,
so this test still proves 100% parity of the visible prose itself.

Marked ``browser`` and ``local_data``: needs the real warehouse-backed
``executive_payload``/``flight_payload`` and the local approval ledger (via
``--allow-missing-analysis``, since most quarters have no approved
analysis in a given checkout) — see ``tests/conftest.py`` and
``web/README.md``.
"""

from __future__ import annotations

import shutil
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import pytest

playwright_sync_api = pytest.importorskip("playwright.sync_api")
sync_playwright = playwright_sync_api.sync_playwright

from src.web_export.analysis import export_analysis  # noqa: E402
from src.web_export.executive import export_executive  # noqa: E402
from src.web_export.flights import export_flights  # noqa: E402

pytestmark = [pytest.mark.browser, pytest.mark.local_data]

PUBLISHED_HTML = Path(__file__).resolve().parent.parent / "static" / "aeromexico_tracker.html"
READER_KPI_KEYS = ("rask_cents_per_km", "cask_cents_per_km", "ask_km", "unit_margin_cents_per_km")


def _chromium_executable() -> str | None:
    candidate = Path("/opt/pw-browsers/chromium-1194/chrome-linux/chrome")
    return str(candidate) if candidate.exists() else None


@pytest.fixture(scope="module")
def web_server(tmp_path_factory, web_dist_dir, flight_payload, executive_payload):
    """Serve a temp copy of web/dist/ (the built site) with the real,
    warehouse-backed payloads plus every analysis export the published
    page's own manifest lists. See test_web_page_smoke.py's web_server
    for why data/v1 (not public/data/v1) is the right path against the
    built site."""

    root = tmp_path_factory.mktemp("web_page_parity")
    shutil.copytree(web_dist_dir, root, dirs_exist_ok=True)
    out_dir = root / "data" / "v1"
    export_flights(flight_payload, out_dir, skip_input_check=True)
    export_executive(executive_payload, out_dir, skip_input_check=True)
    export_analysis(out_dir, published_html=PUBLISHED_HTML, allow_missing=True)

    handler = partial(SimpleHTTPRequestHandler, directory=str(root))
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}/"
    finally:
        server.shutdown()
        thread.join()


@pytest.fixture(scope="module")
def browsers(web_server):
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(executable_path=_chromium_executable())
        pages = []
        for target in (PUBLISHED_HTML.as_uri(), web_server):
            page = browser.new_page()
            page.route("**/favicon.ico", lambda route: route.fulfill(status=204, body=""))
            page.goto(target)
            page.wait_for_function("document.getElementById('period-display').textContent !== '—'")
            pages.append(page)
        published, web = pages
        yield published, web
        browser.close()


# ---------------------------------------------------------------------------
# Extraction helpers
# ---------------------------------------------------------------------------

_STRIP_SUP_JS = """(selector) => {
  const el = document.querySelector(selector);
  if (!el) return null;
  // innerText (not textContent) so hidden siblings — the published page
  // keeps every period's analysis block in the DOM and only toggles
  // [hidden], see src/analysis_agent/stage18.py's SCRIPT — are excluded,
  // same as what a person actually sees. Removing <sup> mutates the live
  // page, which is fine here: each period's block is only ever read once.
  el.querySelectorAll('sup').forEach((node) => node.remove());
  return el.innerText.replace(/\\s+/g, ' ').trim();
}"""


def _text_without_citations(page, selector: str) -> str | None:
    return page.evaluate(_STRIP_SUP_JS, selector)


def _kpis(page) -> dict[str, tuple[str, str, str]]:
    return {
        key: (
            page.inner_text(f"#kpi-{key}-value"),
            page.inner_text(f"#kpi-{key}-qoq"),
            page.inner_text(f"#kpi-{key}-yoy"),
        )
        for key in READER_KPI_KEYS
    }


def _chart_series(page, chart_id: str) -> list[dict[str, Any]]:
    return page.evaluate(
        "(id) => (document.getElementById(id).data || []).map(t => ({name: t.name, x: t.x, y: t.y}))",
        chart_id,
    )


def _period_ids(executive_payload) -> list[str]:
    return [record["period_id"] for record in executive_payload["records"]]


# ---------------------------------------------------------------------------
# Tab shell
# ---------------------------------------------------------------------------


def test_reader_tabs_switch_panels_on_the_web_page(browsers) -> None:
    _, web = browsers
    for tab_id, panel_id in (("tab-economy", "panel-economy"), ("tab-flights", "panel-flights"), ("tab-reading", "panel-reading")):
        web.click(f"#{tab_id}")
        assert web.is_visible(f"#{panel_id}")
        assert web.get_attribute(f"#{tab_id}", "aria-selected") == "true"


# ---------------------------------------------------------------------------
# Reading tab, across every quarter in the stepper
# ---------------------------------------------------------------------------


def test_reading_tab_matches_every_quarter(browsers, executive_payload) -> None:
    published, web = browsers
    for page in (published, web):
        page.click("#tab-reading")
    period_ids = _period_ids(executive_payload)
    # Both pages start on the same default (latest) period; step backwards
    # through the whole matrix, clicking both stepper's #period-prev in
    # lockstep (see web/README.md on why the two independent listeners
    # stay aligned while the quarter lists match 1:1).
    for period_id in reversed(period_ids[:-1]):
        for page in (published, web):
            page.click("#period-prev")
        # narrative-copy is filled after an async per-period fetch (see
        # views/executive/narrative.js); wait for it before reading text.
        web.wait_for_function(
            "(id) => document.getElementById('narrative-copy').dataset.period === id", arg=period_id
        )
        assert published.inner_text("#narrative-period") == web.inner_text("#narrative-period")
        published_text = _text_without_citations(published, "#narrative-copy")
        web_text = _text_without_citations(web, "#narrative-copy")
        assert published_text == web_text, f"narrative mismatch at {web.inner_text('#narrative-period')}"


def test_reading_tab_full_dialog_matches_for_the_one_approved_quarter(browsers, executive_payload) -> None:
    published, web = browsers
    for page in (published, web):
        page.click("#tab-reading")
        # Return to the default (latest) period, the one quarter this repo's
        # local ledger currently has an approved analysis for.
        while page.is_enabled("#period-next"):
            page.click("#period-next")
    web.wait_for_selector("#analysis-open-full")
    open_button = published.locator("[data-analysis-open]:visible")
    if open_button.count() == 0:
        pytest.skip("No quarter in this checkout has an approved analysis to open")
    open_button.first.click()
    web.click("#analysis-open-full")
    published_dialog = published.query_selector(".analysis-dialog[open]")
    published_text = _text_without_citations(published, f"#{published_dialog.get_attribute('id')} .modal-content")
    web_text = _text_without_citations(web, "#analysis-full .modal-content")
    published.keyboard.press("Escape")
    web.keyboard.press("Escape")
    assert published_text == web_text


# ---------------------------------------------------------------------------
# Economy tab, across every quarter in the stepper
# ---------------------------------------------------------------------------


def test_economy_tab_kpis_match_every_quarter(browsers, executive_payload) -> None:
    published, web = browsers
    for page in (published, web):
        page.click("#tab-economy")
        while page.is_enabled("#period-next"):
            page.click("#period-next")
    period_ids = _period_ids(executive_payload)
    for _ in range(len(period_ids) - 1):
        for page in (published, web):
            page.click("#period-prev")
        assert _kpis(published) == _kpis(web), f"KPI mismatch at {web.inner_text('#period-display')}"


def test_economy_tab_charts_match(browsers) -> None:
    published, web = browsers
    for page in (published, web):
        page.click("#tab-economy")
    for chart_id in ("unit-chart", "volume-chart", "load-chart"):
        assert _chart_series(published, chart_id) == _chart_series(web, chart_id), chart_id
