"""Playwright parity between the published integrated page's Vuelos tab
(``static/aeromexico_tracker.html``) and the standalone ``web/`` view, over
a matrix of quarters, modes, regions, airports and month toggles.

Both pages render the exact same generator output
(``src.dashboard.flights_html.integration_flight_payload``); this test
proves the ES-module split changed nothing visible. See
docs/arquitectura/auditoria-arquitectura-20260926.md Fase 3 and
web/README.md.

Marked ``browser`` and ``local_data``: it needs the real warehouse-backed
``flight_payload`` (via ``tests/conftest.py``) so the matrix reflects the
real data currently published, not a synthetic fixture.
"""

from __future__ import annotations

import os
import threading
from functools import partial
from http.server import ThreadingHTTPServer
from pathlib import Path
from typing import Any

import pytest

playwright_sync_api = pytest.importorskip("playwright.sync_api")
sync_playwright = playwright_sync_api.sync_playwright

from src.web_export.executive import export_executive  # noqa: E402
from src.web_export.flights import export_flights  # noqa: E402
from web.serve import WEB_ROOT, SimpleHTTPRequestHandler  # noqa: E402

pytestmark = [pytest.mark.browser, pytest.mark.local_data]

KPI_KEYS = ("passengers", "asm_miles", "rpm_miles", "load_factor")


def _chromium_executable() -> str | None:
    candidate = Path("/opt/pw-browsers/chromium-1194/chrome-linux/chrome")
    return str(candidate) if candidate.exists() else None


@pytest.fixture(scope="module")
def web_server(tmp_path_factory, flight_payload, executive_payload):
    """Serve a temp copy of web/ whose public/data/v1 holds the real,
    warehouse-backed payload (the same one integration_flight_payload()
    reduces the published page's data to). Since P4b, web/index.html
    mounts the reading/economy tabs too (see views/executive/bootstrap.js),
    so this needs executive.json even though this file only checks
    panel-flights."""

    root = tmp_path_factory.mktemp("web_parity")
    for name in ("index.html", "src", "vendor"):
        os.symlink(WEB_ROOT / name, root / name)
    export_flights(flight_payload, root / "public" / "data" / "v1", skip_input_check=True)
    export_executive(executive_payload, root / "public" / "data" / "v1", skip_input_check=True)

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
        published = browser.new_page()
        published.route("**/favicon.ico", lambda route: route.fulfill(status=204, body=""))
        published_html = Path(__file__).resolve().parent.parent / "static" / "aeromexico_tracker.html"
        published.goto(published_html.as_uri())
        published.click("#tab-flights")
        published.wait_for_selector("#panel-flights:not([hidden])")

        web = browser.new_page()
        web.route("**/favicon.ico", lambda route: route.fulfill(status=204, body=""))
        web.goto(web_server)
        web.click("#tab-flights")

        for page in (published, web):
            page.wait_for_selector("#network-volume:not([hidden])")
        yield published, web
        browser.close()


# ---------------------------------------------------------------------------
# Extraction helpers: read the same visible numbers/text from either page.
# ---------------------------------------------------------------------------


def _kpis(page) -> dict[str, tuple[str, str, str]]:
    return {
        key: (
            page.inner_text(f"#flight-kpi-{key}"),
            page.inner_text(f"#flight-kpi-{key}-qoq"),
            page.inner_text(f"#flight-kpi-{key}-yoy"),
        )
        for key in KPI_KEYS
    }


def _network_summary(page) -> tuple[str, str, str]:
    volume = page.query_selector("#network-volume")
    volume_text = "" if volume.is_hidden() else volume.inner_text()
    return (
        page.inner_text("#network-title"),
        page.inner_text("#network-scope-note"),
        volume_text,
    )


def _route_rows(page) -> list[str]:
    rows = page.query_selector_all("#airport-tooltip .route-summary-row")
    return [" | ".join(cell.inner_text().strip() for cell in row.query_selector_all("td")) for row in rows]


def _panel_header(page) -> str:
    header = page.query_selector("#airport-tooltip h3")
    return header.inner_text() if header else ""


def _snapshot(page) -> dict[str, Any]:
    return {
        "period": page.inner_text("#period-display"),
        "kpis": _kpis(page),
        "network": _network_summary(page),
        "panel_header": _panel_header(page),
        "rows": _route_rows(page),
    }


def _assert_parity(published, web, *, label: str) -> None:
    published_snapshot = _snapshot(published)
    web_snapshot = _snapshot(web)
    assert web_snapshot == published_snapshot, f"{label}: {web_snapshot} != {published_snapshot}"


def _goto_period_index(page, current: int, target: int) -> int:
    while current > target:
        page.click("#period-prev")
        current -= 1
    while current < target:
        page.click("#period-next")
        current += 1
    page.wait_for_timeout(30)
    return current


def _goto_both(published, web, current: int, target: int) -> int:
    """Move both pages' shared global quarter stepper the same amount:
    they always start on the same default period and only this helper
    moves them, so they stay in lockstep."""

    _goto_period_index(published, current, target)
    return _goto_period_index(web, current, target)


# ---------------------------------------------------------------------------


def test_every_quarter_matches_in_its_default_mode(browsers, flight_payload) -> None:
    published, web = browsers
    from src.dashboard.flights_html import integration_flight_payload

    embedded = integration_flight_payload(flight_payload)
    period_ids = [q["period_id"] for q in embedded["quarters"]]
    last_index = len(period_ids) - 1
    current = last_index  # both pages start on metadata.default_period, the last quarter
    for target in range(last_index, -1, -1):
        current = _goto_both(published, web, current, target)
        _assert_parity(published, web, label=f"quarter {period_ids[target]}")
    # Leave both pages back on the default period for the tests that follow.
    _goto_both(published, web, current, last_index)


def test_international_regions_match(browsers) -> None:
    published, web = browsers
    for page in (published, web):
        page.click("#network-mode-international")
        page.wait_for_timeout(30)
    _assert_parity(published, web, label="international, no region")
    region_ids = [
        button.get_attribute("data-region")
        for button in published.query_selector_all("#network-region-switch button")
    ]
    for region_id in region_ids:
        for page in (published, web):
            page.click(f'#network-region-switch button[data-region="{region_id}"]')
            page.wait_for_timeout(30)
        _assert_parity(published, web, label=f"international region {region_id}")
        for page in (published, web):
            page.click(f'#network-region-switch button[data-region="{region_id}"]')  # toggle back off
            page.wait_for_timeout(30)
    for page in (published, web):
        page.click("#network-mode-domestic")
        page.wait_for_timeout(30)


def test_selecting_mex_and_cun_airports_matches(browsers) -> None:
    published, web = browsers
    for iata in ("MEX", "CUN"):
        for page in (published, web):
            page.click("#airport-search-toggle")
            page.fill("#airport-search-input", iata)
            page.wait_for_timeout(30)
            page.click(f'[data-airport-result="{iata}"]')
            page.wait_for_timeout(30)
        _assert_parity(published, web, label=f"airport {iata}")


def test_domestic_month_toggle_matches(browsers, flight_payload) -> None:
    published, web = browsers
    from src.dashboard.flights_html import integration_flight_payload

    embedded = integration_flight_payload(flight_payload)
    quarters_with_months = sorted({
        f"{period_id[:4]}Q{(int(period_id[5:7]) - 1) // 3 + 1}"
        for period_id in embedded["domestic_monthly_networks"]
    })
    period_ids = [q["period_id"] for q in embedded["quarters"]]
    last_index = len(period_ids) - 1
    current = last_index
    for quarter_id in quarters_with_months:
        if quarter_id not in period_ids:
            continue  # a month can belong to a quarter not yet in the global selector
        target = period_ids.index(quarter_id)
        current = _goto_both(published, web, current, target)
        for page in (published, web):
            page.click("#network-mode-domestic")
            page.wait_for_timeout(30)
        _assert_parity(published, web, label=f"domestic default months {quarter_id}")
        month_button = published.query_selector("#network-month-switch button")
        if month_button is None:
            continue
        month_id = month_button.get_attribute("data-domestic-month")
        pressed = published.query_selector_all("#network-month-switch button[aria-pressed='true']")
        if len(pressed) < 2:
            continue  # deselecting the only pressed month is a no-op, skip
        for page in (published, web):
            page.click(f'#network-month-switch button[data-domestic-month="{month_id}"]')
            page.wait_for_timeout(30)
        _assert_parity(published, web, label=f"domestic month toggle {quarter_id}/{month_id}")
    _goto_both(published, web, current, last_index)
