"""Playwright parity between the published integrated page
(``static/aeromexico_tracker.html``) and the already-assembled, gate-signed
``site/`` (P6b) — reuses the extraction helpers from
``tests/test_web_page_parity.py`` (P4b/P5's parity test against
``web/dist/``) but serves ``site/`` exactly as committed, with no rebuild
and no fresh export: the point of this test is that the *published
artifact* (what CI deploys) still matches, not that the generators do.

Marked ``browser`` and ``local_data`` (needs the real
``executive_payload`` to know the full quarter matrix — see
``tests/conftest.py``). Requires ``site/`` to already exist and pass
``src.publish.verify`` (skips with a clear reason otherwise — run
``python -m src.publish --record ... --out site/`` first, an
owner-authorized step, see ``src/publish/README.md``).
"""

from __future__ import annotations

import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

playwright_sync_api = pytest.importorskip("playwright.sync_api")
sync_playwright = playwright_sync_api.sync_playwright

from src.publish.verify import verify_site  # noqa: E402
from tests.test_web_page_parity import (  # noqa: E402
    PUBLISHED_HTML,
    _chromium_executable,
    _kpis,
    _period_ids,
    _text,
)

pytestmark = [pytest.mark.browser, pytest.mark.local_data]

SITE_DIR = Path(__file__).resolve().parent.parent / "site"


@pytest.fixture(scope="module")
def site_server():
    if not SITE_DIR.is_dir():
        pytest.skip(f"{SITE_DIR} does not exist; run `python -m src.publish --record ... --out site/` first")
    problems = verify_site(SITE_DIR)
    if problems:
        pytest.skip(f"{SITE_DIR} fails src.publish.verify: {problems[:3]}")

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
def browsers(site_server):
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(executable_path=_chromium_executable())
        pages = []
        for target in (PUBLISHED_HTML.as_uri(), site_server):
            page = browser.new_page()
            page.route("**/favicon.ico", lambda route: route.fulfill(status=204, body=""))
            page.goto(target)
            page.wait_for_function("document.getElementById('period-display').textContent !== '—'")
            pages.append(page)
        published, site = pages
        yield published, site
        browser.close()


def test_reader_tabs_switch_panels_on_the_site(browsers) -> None:
    _, site = browsers
    for tab_id, panel_id in (("tab-economy", "panel-economy"), ("tab-flights", "panel-flights"), ("tab-reading", "panel-reading")):
        site.click(f"#{tab_id}")
        assert site.is_visible(f"#{panel_id}")
        assert site.get_attribute(f"#{tab_id}", "aria-selected") == "true"


def test_reading_tab_matches_every_quarter_on_the_site(browsers, executive_payload) -> None:
    published, site = browsers
    for page in (published, site):
        page.click("#tab-reading")
    period_ids = _period_ids(executive_payload)
    for period_id in reversed(period_ids[:-1]):
        for page in (published, site):
            page.click("#period-prev")
        site.wait_for_function(
            "(id) => document.getElementById('narrative-copy').dataset.period === id", arg=period_id
        )
        assert published.inner_text("#narrative-period") == site.inner_text("#narrative-period")
        assert _text(published, "#narrative-copy") == _text(site, "#narrative-copy"), (
            f"narrative mismatch at {site.inner_text('#narrative-period')}"
        )


def test_economy_tab_kpis_match_every_quarter_on_the_site(browsers, executive_payload) -> None:
    published, site = browsers
    for page in (published, site):
        page.click("#tab-economy")
        while page.is_enabled("#period-next"):
            page.click("#period-next")
    period_ids = _period_ids(executive_payload)
    for _ in range(len(period_ids) - 1):
        for page in (published, site):
            page.click("#period-prev")
        assert _kpis(published) == _kpis(site), f"KPI mismatch at {site.inner_text('#period-display')}"
