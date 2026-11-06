"""CI-runnable smoke test for web/: serves it with a synthetic, public
fixture (no warehouse) and checks the Vuelos view renders with no console
errors. Marked ``browser`` only (not ``local_data``) so it is the one test
in this package that could run once CI enables Playwright — see web/README.md.
"""

from __future__ import annotations

import json
import os
import shutil
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import pytest

playwright_sync_api = pytest.importorskip("playwright.sync_api")
sync_playwright = playwright_sync_api.sync_playwright

# noqa: E402 below — these imports come after pytest.importorskip on purpose.
from src.web_export.executive import export_executive  # noqa: E402
from src.web_export.flights import export_flights  # noqa: E402
from src.web_export.market import export_market  # noqa: E402
from src.web_export.writer import write_json  # noqa: E402

pytestmark = pytest.mark.browser


def _chromium_executable() -> str | None:
    override = os.environ.get("PLAYWRIGHT_CHROMIUM_EXECUTABLE")
    if override:
        candidate = Path(override)
        if not candidate.is_file():
            raise ValueError("PLAYWRIGHT_CHROMIUM_EXECUTABLE does not name a browser executable")
        return str(candidate)
    candidate = Path("/opt/pw-browsers/chromium-1194/chrome-linux/chrome")
    return str(candidate) if candidate.exists() else None


def _load_fixture(name: str) -> dict[str, Any]:
    path = Path(__file__).resolve().parent / "fixtures" / "web" / name
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def web_server(tmp_path_factory, web_dist_dir):
    """Serve a temp copy of web/dist/ (the built site) whose data/v1
    holds only the synthetic fixture, over HTTP (fetch() needs http:, not
    file:). See test_web_page_smoke.py's web_server for why data/v1 (not
    public/data/v1) is the right path against the built site."""

    root = tmp_path_factory.mktemp("web_smoke")
    # Synthetic fixtures must not inherit an existing real export's files.
    shutil.copytree(web_dist_dir, root, dirs_exist_ok=True, ignore=shutil.ignore_patterns("data"))
    write_json(root / "api/chat/health", {"status": "ok", "auth": "password", "snapshot_version": "synthetic-ui-only"})

    out_dir = root / "data" / "v1"
    write_json(out_dir / "official-routes.json", _load_fixture("official_routes_sample.json"))
    fixture = _load_fixture("flights_sample.json")
    payload = {**fixture, "international_networks": fixture["route_networks"]}
    export_flights(payload, out_dir, skip_input_check=True)
    # main.js now mounts the executive/economy tabs too (see web/index.html),
    # so this page needs their payload even though this test only exercises
    # panel-flights (now behind the "Vuelos" tab, see mountTabs()).
    export_executive(_load_fixture("executive_sample.json"), out_dir, skip_input_check=True)
    export_market(_load_fixture("market_sample.json"), out_dir, skip_input_check=True)
    analysis = _load_fixture("analysis_sample.json")
    write_json(out_dir / "analysis" / f"{analysis['period_id']}.json", analysis)
    # Reading availability is independent of the financial/flight periods.
    # Advertise only the synthetic analysis actually served by this fixture.
    write_json(root / "publication_manifest.json", {"analysis_manifest": [
        {"period_id": analysis["period_id"], "approval_event": "synthetic-approved-reading"}
    ]})

    handler = partial(SimpleHTTPRequestHandler, directory=str(root))
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}/"
    finally:
        server.shutdown()
        thread.join()


def _open_official_map(page, server):
    page.goto(server)
    page.get_by_role("button", name="Cerrar chat", exact=True).click()
    page.click("#tab-flights")
    page.wait_for_selector("#route-flow-map[data-map-status=ready]")
    page.wait_for_function("document.getElementById('route-flow-map')._fullLayout.width === document.getElementById('route-flow-map').clientWidth")


def test_flights_view_renders_the_official_fixture_without_console_errors(web_server):
    errors = []
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=_chromium_executable())
        page = browser.new_page(viewport={"width": 1400, "height": 900})
        page.route("**/favicon.ico", lambda route: route.fulfill(status=204, body=""))
        page.on("pageerror", lambda error: errors.append(str(error)))
        _open_official_map(page, web_server)
        page.wait_for_selector("#route-flow-map .scattergeo .js-line")
        assert page.inner_text("#period-display") == "2T26"
        assert page.inner_text("#official-map-total") == "6"
        assert page.inner_text("#official-map-months") == "3/3 meses"
        assert page.locator("[data-official-route]").count() == 1
        page.locator("[data-official-route]").click()
        assert "MEXICO → MONTERREY" in page.locator(".official-route-detail").inner_text()
        assert "abril 2026" in page.locator(".official-route-detail").inner_text()
        assert page.inner_text("#flight-kpi-passengers") != "—"
        assert page.locator("#official-map-carriers").is_hidden()
        browser.close()
    assert errors == []


def test_region_map_refits_its_actual_width_without_mobile_horizontal_scroll(web_server):
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=_chromium_executable())
        page = browser.new_page(viewport={"width": 1400, "height": 900})
        _open_official_map(page, web_server)
        wide = page.locator("#route-flow-map").evaluate("e => e._fullLayout.width")
        page.set_viewport_size({"width": 390, "height": 844})
        page.wait_for_function("document.getElementById('route-flow-map')._fullLayout.width === document.getElementById('route-flow-map').clientWidth")
        narrow = page.locator("#route-flow-map").evaluate("e => e._fullLayout.width")
        assert 250 < narrow < wide
        page.wait_for_function("document.documentElement.scrollWidth <= innerWidth", timeout=5000)
        assert page.inner_text("#official-map-total") == "6"
        browser.close()


def test_region_map_refits_when_only_the_canvas_height_changes(web_server):
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=_chromium_executable())
        page = browser.new_page(viewport={"width": 600, "height": 900})
        _open_official_map(page, web_server)
        read = "e => [e._fullLayout.width, e._fullLayout.height, e.layout.geo.lataxis.range]"
        before = page.locator("#route-flow-map").evaluate(read)
        page.locator("#route-flow-map").evaluate("e => e.style.height='330px'")
        page.wait_for_function("document.getElementById('route-flow-map')._fullLayout.height === 330")
        after = page.locator("#route-flow-map").evaluate(read)
        assert before[0] == after[0]
        assert before[1] != after[1]
        assert before[2] != after[2]
        browser.close()


def test_region_map_refits_after_a_hidden_tab_redraw(web_server):
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=_chromium_executable())
        page = browser.new_page(viewport={"width": 1400, "height": 900})
        _open_official_map(page, web_server)
        page.set_viewport_size({"width": 1000, "height": 900})
        page.wait_for_function("document.getElementById('route-flow-map')._fullLayout.width === document.getElementById('route-flow-map').clientWidth")
        at_b = page.locator("#route-flow-map").evaluate("e => e._fullLayout.width")
        page.click("#tab-reading")
        page.set_viewport_size({"width": 1400, "height": 900})
        page.click("#tab-flights")
        page.wait_for_function("document.getElementById('route-flow-map')._fullLayout.width === document.getElementById('route-flow-map').clientWidth")
        assert page.locator("#route-flow-map").evaluate("e => e._fullLayout.width") > at_b
        page.set_viewport_size({"width": 1000, "height": 900})
        page.wait_for_function("document.getElementById('route-flow-map')._fullLayout.width === document.getElementById('route-flow-map').clientWidth")
        assert page.locator("#route-flow-map").evaluate("e => e._fullLayout.width") == at_b
        assert page.inner_text("#official-map-total") == "6"
        browser.close()


def test_official_scope_carriers_empty_regions_and_global_quarter_do_not_fallback(web_server):
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=_chromium_executable())
        page = browser.new_page()
        _open_official_map(page, web_server)
        page.locator('[data-map-scope="us"]').click()
        page.wait_for_function("document.getElementById('official-map-total').textContent === '30'")
        assert page.inner_text("#official-map-months") == "1/3 meses"
        assert "official-partial" in page.locator("#official-map-source").get_attribute("class")
        page.locator("#official-map-carriers summary").click()
        page.locator('#official-map-carriers input[value="VOLARIS"]').uncheck()
        page.wait_for_function("document.getElementById('official-map-total').textContent === '20'")
        page.locator('[data-map-scope="international"]').click()
        page.locator("#official-map-region").select_option("europe")
        page.wait_for_function("document.getElementById('route-flow-map').dataset.mapRegion === 'europe'")
        assert page.inner_text("#official-map-total") == "N/D"
        assert page.locator("#official-map-region").input_value() == "europe"
        page.locator('[data-map-scope="national"]').click()
        page.wait_for_function("document.getElementById('official-map-total').textContent === '6'")
        page.click("#period-prev")
        page.wait_for_function("document.getElementById('route-flow-map').dataset.mapPeriod === '2026Q1'")
        assert page.inner_text("#period-display") == "1T26"
        assert page.inner_text("#official-map-total") == "N/D"
        assert page.inner_text("#official-map-months") == "0/3 meses"
        assert page.locator("[data-official-route]").count() == 0
        browser.close()
