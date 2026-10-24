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
    write_json(
        out_dir / "market-demand.json",
        {"months": ["2026M06"], "airports": [], "groups": [], "quality_notes": ["Fixture"]},
    )
    write_json(
        out_dir / "news.json",
        {
            "mode": "candidate_preview",
            "coverage_note": "Fixture parcial",
            "months": ["2026-09"],
            "limits": [],
            "records": [
                {
                    "id": "fixture",
                    "story_id": "fixture",
                    "title": "Viva ajusta capacidad",
                    "description": "Resumen original de prueba",
                    "publisher": "Viva",
                    "companies": ["Viva"],
                    "topics": ["capacidad"],
                    "published_at": "2026-09-11",
                    "event_date": "2026-08-01",
                    "event_end_date": "2026-08-31",
                    "first_captured_at": "2026-10-15T00:00:00Z",
                    "review_status": "candidate_unapproved",
                    "sources": [
                        {"id": "fixture", "url": "https://ri.vivaaerobus.com/doc", "sha256": "a" * 64}
                    ],
                }
            ],
        },
    )
    analysis = _load_fixture("analysis_sample.json")
    for record in _load_fixture("executive_sample.json")["records"]:
        period = record["period_id"]
        write_json(out_dir / "analysis" / f"{period}.json", {**analysis, "period_id": period})
    write_json(
        root / "publication_manifest.json",
        {
            "analysis_manifest": [
                {"period_id": record["period_id"], "approval_event": "synthetic-approved"}
                for record in _load_fixture("executive_sample.json")["records"]
            ]
        },
    )

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
        page = browser.new_page(viewport={"width": 390, "height": 844})
        held = []
        page.route("**/data/v1/executive.json", lambda route: held.append(route))
        with page.expect_request("**/data/v1/executive.json"):
            page.goto(web_server, wait_until="domcontentloaded")
        page.click("#tab-news")
        # Let the original tab-visible event fire while startup is suspended.
        page.evaluate(
            "() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))"
        )
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
    payload["records"][0]["sources"].append(
        {"id": "other", "url": "https://example.com/second", "sha256": "b" * 64, "publisher": "Otro medio"}
    )
    page.route("**/data/v1/news.json", lambda route: route.fulfill(json=payload))
    page.click("#tab-news")
    page.wait_for_selector(".news-card")
    assert page.locator('a[href="https://example.com/second"]').text_content() == "Abrir fuente · Otro medio"
    assert page.locator('a[href="https://ri.vivaaerobus.com/doc"]').text_content() == "Abrir fuente · Viva"
    assert errors == []


def test_editorial_quarter_does_not_add_financial_observations(page_with_console_capture, web_server) -> None:
    page, errors = page_with_console_capture
    manifest = {
        "analysis_manifest": [
            {"period_id": "2026Q2", "approval_event": "old"},
            {"period_id": "2026Q3", "approval_event": "new"},
        ]
    }
    analysis = {**_load_fixture("analysis_sample.json"), "period_id": "2026Q3"}
    page.route("**/publication_manifest.json", lambda route: route.fulfill(json=manifest))
    page.route("**/analysis/2026Q3.json", lambda route: route.fulfill(json=analysis))
    page.reload()
    page.wait_for_function("document.getElementById('narrative-copy').dataset.period === '2026Q3'")
    assert page.inner_text("#period-display") == "2T26"
    assert page.input_value("#reading-period") == "2026Q3"
    page.select_option("#reading-period", "2026Q2")
    page.wait_for_function("document.getElementById('narrative-copy').dataset.period === '2026Q2'")
    assert page.inner_text("#period-display") == "2T26"
    page.click("#period-prev")
    page.wait_for_function("document.getElementById('period-display').textContent === '1T26'")
    assert page.input_value("#reading-period") == "2026Q2"
    assert (
        page.request.get(web_server + "data/v1/executive.json").json()["metadata"]["last_period"] == "2026Q2"
    )
    assert errors == []


def test_reading_tab_renders_the_synthetic_analysis_by_default(page_with_console_capture) -> None:
    page, console_errors = page_with_console_capture
    assert page.get_attribute("#tab-reading", "aria-selected") == "true"
    assert page.is_visible("#panel-reading")
    assert page.inner_text("#period-display") == "2T26"
    page.wait_for_function("document.getElementById('narrative-copy').dataset.period === '2026Q2'")
    page.wait_for_selector("#analysis-open-full")
    assert "Fixture" in page.inner_text("#narrative-copy")
    assert page.is_visible("#analysis-open-full")
    assert console_errors == []


def test_market_uses_global_quarter_when_selected_during_startup(web_server):
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(executable_path=_chromium_executable())
        page = browser.new_page(viewport={"width": 390, "height": 844})
        held = []
        airport_requests = []
        page.on(
            "request",
            lambda request: (
                airport_requests.append(request.url) if "market-demand.json" in request.url else None
            ),
        )
        page.route("**/data/v1/executive.json", lambda route: held.append(route))
        with page.expect_request("**/data/v1/executive.json"):
            page.goto(web_server, wait_until="domcontentloaded")
        page.click("#tab-market")
        page.evaluate(
            "() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))"
        )
        assert held
        held[0].continue_()
        page.wait_for_selector("#market-chart.js-plotly-plot")
        assert page.get_attribute("#tab-market", "aria-selected") == "true"
        assert page.inner_text("#period-display") == "2T26"
        assert page.locator("#market-comparison tr").count() == 4
        assert page.locator("#airport-demand-card, #market-grain, #market-period").count() == 0
        assert airport_requests == []
        browser.close()


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
    # The two axes measure different quantities. Their rendered ticks must
    # remain independent; Plotly4's default sync aligns them on the same grid.
    for chart_id in ("unit-chart", "volume-chart"):
        rendered = page.evaluate(
            """id => {
            const chart = document.getElementById(id);
            const ticks = selector => [...chart.querySelectorAll(selector)]
                .map(tick => tick.getBoundingClientRect().y);
            return { primary: ticks('.ytick text'), secondary: ticks('.y2tick text'),
                primaryRange: chart._fullLayout.yaxis.range,
                secondaryRange: chart._fullLayout.yaxis2.range };
        }""",
            chart_id,
        )
        assert len(rendered["primary"]) >= 2
        assert len(rendered["secondary"]) >= 2
        assert rendered["primaryRange"] != rendered["secondaryRange"]
        assert len(rendered["primary"]) != len(rendered["secondary"]) or any(
            abs(left - right) > 1 for left, right in zip(rendered["primary"], rendered["secondary"])
        ), f"{chart_id}: unrelated units must not share a synchronized tick grid"
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
    page.set_viewport_size({"width": 390, "height": 844})
    page.click(f"#tab-{new_tab}")
    if new_tab == "market":
        page.wait_for_selector("#market-comparison tr")
        assert not page.is_visible("#panel-reading #market-chart")
        assert page.locator("#market-grain, #market-period, #airport-demand-card").count() == 0
        page.select_option("#market-segment", "domestic")
        page.click("#period-prev")
        page.wait_for_function("document.getElementById('market-chart').layout.shapes[0].x0 === '2026-01-01'")
        assert page.inner_text("#period-display") == "1T26"
        assert page.evaluate(
            "document.getElementById('market-chart').data.every(t => t.x.every(x => x < '2026-04-01'))"
        )
        assert "2026Q1" in page.get_attribute("#market-source", "title")
        page.select_option("#market-segment", "international")
        page.wait_for_function("document.getElementById('market-chart').layout.shapes[0].x0 === '2026-01-01'")
        page.click("#period-next")
        page.wait_for_function("document.getElementById('market-chart').layout.shapes[0].x0 === '2026-04-01'")
        assert page.inner_text("#period-display") == "2T26"
    else:
        page.wait_for_selector(".news-card")
        page.select_option("#news-company", "Volaris")
        assert "Sin fichas" in page.inner_text("#news-stories")
        page.select_option("#news-company", "Viva")
        page.fill("#news-query", "capacidad")
        assert page.locator(".news-card").count() == 1
        page.fill("#news-query", "<img src=x>")
        assert page.locator("#news-stories img").count() == 0
        page.fill("#news-query", "")
    page.click("#tab-reading")
    page.click("#tab-economy")
    page.click(f"#tab-{new_tab}")
    assert page.is_visible(f"#panel-{new_tab}")
    page.wait_for_function("document.documentElement.scrollWidth <= innerWidth")
    assert errors == []


@pytest.mark.parametrize("catalog", ["missing", "html", "invalid_identity"])
def test_missing_reading_catalog_keeps_indicators_and_lazy_views_available(web_server, catalog):
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(executable_path=_chromium_executable())
        page = browser.new_page()
        errors, analysis_requests = [], []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.on(
            "request",
            lambda request: (
                analysis_requests.append(request.url) if "/data/v1/analysis/" in request.url else None
            ),
        )
        if catalog == "missing":
            page.route(
                "**/publication_manifest.json", lambda route: route.fulfill(status=404, body="missing")
            )
        elif catalog == "html":
            page.route(
                "**/publication_manifest.json",
                lambda route: route.fulfill(
                    status=200, content_type="text/html", body="<!doctype html><title>Vite fallback</title>"
                ),
            )
        else:
            page.route(
                "**/publication_manifest.json",
                lambda route: route.fulfill(json={"analysis_manifest": [{"period_id": "2026Q3"}]}),
            )
        page.goto(web_server)
        page.wait_for_function("document.getElementById('period-display').textContent !== '—'")
        page.wait_for_function(
            "document.getElementById('narrative-copy').textContent.includes('No se pudo verificar el catálogo')"
        )
        assert page.locator("#reading-period").is_disabled()
        assert "No se pudo verificar el catálogo" in page.inner_text("#narrative-copy")
        assert page.locator("#analysis-open-full").count() == 0
        page.click("#tab-economy")
        previous = page.inner_text("#period-display")
        assert page.is_enabled("#period-prev")
        page.click("#period-prev")
        page.wait_for_function(
            "before => document.getElementById('period-display').textContent !== before", arg=previous
        )
        assert page.inner_text("#kpi-rask_cents_per_km-value") not in {"", "—", "No disponible"}
        page.click("#tab-flights")
        page.wait_for_selector("#route-flow-map .scattergeo .js-line")
        assert errors == []
        assert analysis_requests == []
        browser.close()


def test_financial_kpi_parity_does_not_wait_for_the_independent_reading_period(web_server):
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "independent_period_parity", Path(__file__).with_name("test_site_parity.py")
    )
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)
    executive = _load_fixture("executive_sample.json")
    analysis = {**_load_fixture("analysis_sample.json"), "period_id": "2026Q3"}
    entries = [
        {"period_id": row["period_id"], "approval_event": "synthetic-approved"}
        for row in executive["records"]
    ]
    entries.append({"period_id": "2026Q3", "approval_event": "synthetic-reading-only"})
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(executable_path=_chromium_executable())
        page = browser.new_page()
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.route(
            "**/publication_manifest.json", lambda route: route.fulfill(json={"analysis_manifest": entries})
        )
        page.route("**/data/v1/analysis/2026Q3.json", lambda route: route.fulfill(json=analysis))
        page.goto(web_server + "?sel_kpis=AEROMEXICO")
        page.wait_for_function("document.getElementById('narrative-copy').dataset.period === '2026Q3'")
        helper._check_economy_kpis(page, executive)
        assert page.locator("#narrative-copy").get_attribute("data-period") == "2026Q3"
        assert (
            page.inner_text("#period-display")
            == executive["views"][executive["records"][0]["period_id"]]["period_label"]
        )
        assert errors == []
        browser.close()


@pytest.mark.parametrize("stalled", ["catalog", "analysis"])
def test_slow_reading_requests_do_not_block_financial_controls_or_lazy_views(web_server, stalled):
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(executable_path=_chromium_executable())
        page = browser.new_page()
        errors, held = [], []
        page.on("pageerror", lambda error: errors.append(str(error)))
        target = "**/publication_manifest.json" if stalled == "catalog" else "**/data/v1/analysis/*.json"
        page.route(target, lambda route: held.append(route))
        with page.expect_request(target):
            page.goto(web_server, wait_until="domcontentloaded")
        page.wait_for_function("document.getElementById('period-display').textContent === '2T26'")
        page.evaluate(
            "() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))"
        )
        assert len(held) == 1
        assert page.locator("#analysis-open-full").count() == 0
        if stalled == "catalog":
            assert page.locator("#reading-period").is_disabled()
            assert "Cargando lectura" in page.inner_text("#narrative-copy")
        else:
            assert not page.locator("#reading-period").is_disabled()
            assert "Cargando análisis" in page.inner_text("#narrative-copy")
        page.click("#tab-economy")
        assert page.is_enabled("#period-prev")
        page.click("#period-prev")
        page.wait_for_function("document.getElementById('period-display').textContent === '1T26'")
        assert page.inner_text("#kpi-rask_cents_per_km-value") not in {"", "—", "No disponible"}
        page.click("#tab-flights")
        page.wait_for_selector("#route-flow-map .scattergeo .js-line")
        assert len(held) == 1
        # Flights keeps its own available cut. Return to financial controls
        # and select Q1 again before releasing the still-pending Q2 reading.
        page.click("#tab-economy")
        while page.is_enabled("#period-next"):
            page.click("#period-next")
        page.click("#period-prev")
        page.wait_for_function("document.getElementById('period-display').textContent === '1T26'")
        held[0].continue_()
        page.wait_for_selector("#analysis-open-full", state="attached")
        assert page.inner_text("#period-display") == "1T26"
        page.click("#tab-reading")
        page.wait_for_selector("#analysis-open-full")
        assert page.locator("#narrative-copy").get_attribute("data-period") == "2026Q2"
        assert page.inner_text("#period-display") == "1T26"
        assert errors == []
        browser.close()


def test_narrative_parity_visits_each_reading_without_selecting_financial_quarters(web_server, monkeypatch):
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "narrative_selector_parity", Path(__file__).with_name("test_site_parity.py")
    )
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)
    fixture_spec = importlib.util.spec_from_file_location(
        "narrative_entity_fixtures", Path(__file__).with_name("test_web_chat_smoke.py")
    )
    fixture_module = importlib.util.module_from_spec(fixture_spec)
    fixture_spec.loader.exec_module(fixture_module)
    executive = fixture_module._public_fixtures()["/data/v1/executive.json"]
    identities = [
        ("AEROMEXICO", "2026Q2"),
        ("AEROMEXICO", "2026Q3"),
        ("VOLARIS", "2026Q2"),
        ("VIVA_AEROBUS", "2026Q2"),
        ("INDUSTRY", "2026Q2"),
    ]
    entries, payloads = [], {}
    for entity, period in identities:
        payload = {
            **_load_fixture("analysis_sample.json"),
            "period_id": period,
            "thesis": f"Fixture {entity} {period}",
        }
        if entity != "AEROMEXICO":
            payload.update(
                entity_key=entity,
                period_label="2T26",
                cutoff_date="2026-10-24",
                selection_mode="retrospective",
                guidance_as_of="report_date",
            )
        payloads[entity, period] = payload
        entries.append(
            {
                "period_id": period,
                "approval_event": "synthetic-approved",
                **({"entity_key": entity} if entity != "AEROMEXICO" else {}),
            }
        )
    monkeypatch.setattr(helper.manifest_mod, "load_manifest", lambda site: {"analysis_manifest": entries})
    monkeypatch.setattr(
        helper, "_export_approved_entry", lambda entry: payloads[helper.manifest_mod.analysis_identity(entry)]
    )
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(executable_path=_chromium_executable())
        page = browser.new_page()
        errors, visited = [], []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.route("**/data/v1/executive.json", lambda route: route.fulfill(json=executive))
        page.on(
            "request",
            lambda request: (
                visited.append(request.url)
                if request.is_navigation_request() and request.frame == page.main_frame
                else None
            ),
        )
        page.route(
            "**/publication_manifest.json", lambda route: route.fulfill(json={"analysis_manifest": entries})
        )

        def serve_reading(route):
            suffix = route.request.url.split("/analysis/", 1)[1].removesuffix(".json")
            entity, period = suffix.split("/", 1) if "/" in suffix else ("AEROMEXICO", suffix)
            route.fulfill(json=payloads[entity, period])

        page.route("**/data/v1/analysis/**", serve_reading)
        helper.test_reading_tab_narrative_matches_the_approved_analysis(None, page, web_server)
        assert len(visited) == len(identities)
        assert all("readingPeriod=" in url and "&period=" not in url for url in visited)
        assert page.inner_text("#period-display") == "2T26"
        assert errors == []
        browser.close()
