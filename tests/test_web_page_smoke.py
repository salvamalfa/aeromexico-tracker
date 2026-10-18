"""CI-runnable smoke test for the full web/ page: builds it with Vite
(``web_dist_dir`` in tests/conftest.py) and serves web/dist/ with
small, synthetic public fixtures (no warehouse, no analysis_runs/), then
checks every tab — Lectura ejecutiva, Economía unitaria, Vuelos — renders
with no console errors. Marked ``browser`` only (not ``local_data``), same
as ``test_web_flights_smoke.py``, so it is CI-capable once Playwright is
enabled there — see web/README.md.
"""

from __future__ import annotations

import json
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
    candidate = Path("/opt/pw-browsers/chromium-1194/chrome-linux/chrome")
    return str(candidate) if candidate.exists() else None


def _load_fixture(name: str) -> dict[str, Any]:
    path = Path(__file__).resolve().parent / "fixtures" / "web" / name
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def web_server(tmp_path_factory, web_dist_dir):
    """Serve a temp copy of web/dist/ (the built site) whose data/v1
    holds only the synthetic, public fixtures — no local warehouse or
    analysis_runs/. Vite copies web/public/* to the root of dist/ (not
    under a public/ subdirectory), so the exported payload goes at
    <root>/data/v1, matching the runtime dataRoot the built page fetches
    from (see web/src/views/{flights,executive}/state.ts)."""

    root = tmp_path_factory.mktemp("web_page_smoke")
    # A local build can include a real export from web/public/data. Keeping
    # its entity/period files would let the synthetic page load real routes
    # (and their map dependencies) instead of the fixture below.
    shutil.copytree(web_dist_dir, root, dirs_exist_ok=True, ignore=shutil.ignore_patterns("data"))

    out_dir = root / "data" / "v1"
    flights_fixture = _load_fixture("flights_sample.json")
    flights_payload = {**flights_fixture, "international_networks": flights_fixture["route_networks"]}
    export_flights(flights_payload, out_dir, skip_input_check=True)
    export_executive(_load_fixture("executive_sample.json"), out_dir, skip_input_check=True)
    export_market(_load_fixture("market_sample.json"), out_dir, skip_input_check=True)
    write_json(out_dir / "market-demand.json", {"months": ["2026M06"], "airports": [], "groups": [], "quality_notes": ["Fixture"]})
    write_json(out_dir / "news.json", {
        "mode":"candidate_preview", "coverage_note":"Fixture parcial", "months":["2026-09"], "limits":[],
        "records":[{"id":"fixture", "story_id":"fixture", "title":"Viva ajusta capacidad", "description":"Resumen original de prueba", "publisher":"Viva", "companies":["Viva"], "topics":["capacidad"], "published_at":"2026-09-11", "event_date":"2026-08-01", "event_end_date":"2026-08-31", "first_captured_at":"2026-10-15T00:00:00Z", "review_status":"candidate_unapproved", "sources":[{"id":"fixture", "url":"https://ri.vivaaerobus.com/doc", "sha256":"a"*64}]}]})
    analysis = _load_fixture("analysis_sample.json")
    write_json(out_dir / "analysis" / f"{analysis['period_id']}.json", analysis)

    handler = partial(SimpleHTTPRequestHandler, directory=str(root))
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}/"
    finally:
        server.shutdown()
        thread.join()


@pytest.fixture()
def page_with_console_capture(web_server):
    console_errors: list[str] = []
    external_requests: list[str] = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(executable_path=_chromium_executable())
        page = browser.new_page()
        page.route("**/favicon.ico", lambda route: route.fulfill(status=204, body=""))

        def on_console_error(message: Any) -> None:
            if message.type == "error":
                console_errors.append(message.text)

        def on_request(request: Any) -> None:
            if not request.url.startswith(web_server):
                external_requests.append(request.url)

        page.on("console", on_console_error)
        page.on("pageerror", lambda error: console_errors.append(str(error)))
        page.on("request", on_request)
        page.goto(web_server)
        page.wait_for_function("document.getElementById('period-display').textContent !== '—'")
        yield page, console_errors
        browser.close()
    assert external_requests == [], f"Synthetic smoke requested external resources: {external_requests}"


def test_news_mounts_when_selected_while_executive_data_is_loading(web_server):
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(executable_path=_chromium_executable())
        page = browser.new_page(viewport={"width":390,"height":844})
        held = []
        page.route("**/data/v1/executive.json", lambda route: held.append(route))
        with page.expect_request("**/data/v1/executive.json"):
            page.goto(web_server, wait_until="domcontentloaded")
        page.click("#tab-news")
        # Let the original tab-visible event fire while startup is suspended.
        page.evaluate("() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))")
        assert page.inner_text("#news-count") == "Cargando noticias…"
        assert held
        held[0].continue_()
        page.wait_for_selector(".news-card")
        assert page.get_attribute("#tab-news", "aria-selected") == "true"
        assert "Viva ajusta capacidad" in page.inner_text("#news-stories")
        browser.close()


def test_news_source_links_keep_their_own_publisher(page_with_console_capture, web_server):
    page, errors = page_with_console_capture
    payload = page.request.get(web_server + "data/v1/news.json").json()
    payload["records"][0]["sources"][0]["publisher"] = "Viva"
    payload["records"][0]["sources"].append({"id":"other", "url":"https://example.com/second", "sha256":"b"*64, "publisher":"Otro medio"})
    page.route("**/data/v1/news.json", lambda route: route.fulfill(json=payload))
    page.click("#tab-news")
    page.wait_for_selector(".news-card")
    assert page.locator('a[href="https://example.com/second"]').text_content() == "Abrir fuente · Otro medio"
    assert page.locator('a[href="https://ri.vivaaerobus.com/doc"]').text_content() == "Abrir fuente · Viva"
    assert errors == []


def test_reading_tab_renders_the_synthetic_analysis_by_default(page_with_console_capture) -> None:
    page, console_errors = page_with_console_capture
    assert page.get_attribute("#tab-reading", "aria-selected") == "true"
    assert page.is_visible("#panel-reading")
    assert page.inner_text("#period-display") == "2T26"
    page.wait_for_function("document.getElementById('narrative-copy').dataset.period === '2026Q2'")
    assert "Fixture" in page.inner_text("#narrative-copy")
    assert page.is_visible("#analysis-open-full")
    assert console_errors == []


def test_economy_tab_renders_kpis_and_charts(page_with_console_capture) -> None:
    page, console_errors = page_with_console_capture
    page.click("#tab-economy")
    assert page.is_visible("#panel-economy")
    assert page.inner_text("#kpi-rask_cents_per_km-value") != "—"
    for chart_id in ("unit-chart", "volume-chart", "load-chart"):
        page.wait_for_selector(f"#{chart_id} .js-plotly-plot, #{chart_id}.js-plotly-plot")
    page.wait_for_function(
        "[...document.querySelectorAll('#unit-chart, #volume-chart, #load-chart')].every("
        "chart => Math.abs(chart.clientWidth - chart.querySelector('svg.main-svg').getBoundingClientRect().width) < 2)"
    )
    assert console_errors == []


def test_flights_tab_renders_the_synthetic_fixture(page_with_console_capture) -> None:
    page, console_errors = page_with_console_capture
    page.click("#tab-flights")
    page.wait_for_selector("#network-volume:not([hidden])")
    page.wait_for_selector("#route-flow-map .scattergeo .js-line")
    assert page.is_visible("#panel-flights")
    assert page.inner_text("#flight-kpi-passengers") != "—"
    assert console_errors == []


def test_analysis_dialog_opens_and_closes(page_with_console_capture) -> None:
    page, console_errors = page_with_console_capture
    page.click("#analysis-open-full")
    page.wait_for_selector("#analysis-full[open]")
    assert "Fixture" in page.inner_text("#analysis-full .modal-content")
    page.click("#analysis-full .close")
    page.wait_for_function("!document.getElementById('analysis-full').hasAttribute('open')")
    assert console_errors == []


@pytest.mark.parametrize("new_tab", ["market", "news"])
def test_independent_tabs_and_mobile_navigation(page_with_console_capture, new_tab):
    page, errors = page_with_console_capture
    if page.locator(f"#tab-{new_tab}").count() == 0:
        pytest.skip("Independent proposal is not part of this branch")
    page.set_viewport_size({"width":390,"height":844})
    page.click(f"#tab-{new_tab}")
    if new_tab == "market":
        page.wait_for_selector("#market-comparison tr")
        assert not page.is_visible("#panel-reading #market-chart")
        page.select_option("#market-grain","month")
        page.select_option("#market-segment","domestic")
        page.wait_for_function("document.getElementById('market-period').value.includes('M')")
    else:
        page.wait_for_selector(".news-card")
        page.select_option("#news-company","Volaris")
        assert "Sin fichas" in page.inner_text("#news-stories")
        page.select_option("#news-company","Viva")
        page.fill("#news-query","capacidad")
        assert page.locator(".news-card").count() == 1
        page.fill("#news-query","<img src=x>")
        assert page.locator("#news-stories img").count() == 0
        page.fill("#news-query","")
    page.click("#tab-reading")
    page.click("#tab-economy")
    page.click(f"#tab-{new_tab}")
    assert page.is_visible(f"#panel-{new_tab}")
    page.wait_for_function("document.documentElement.scrollWidth <= innerWidth")
    assert errors == []
