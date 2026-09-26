"""CI-runnable smoke test for the full web/ page: serves it with small,
synthetic public fixtures (no warehouse, no analysis_runs/) and checks
every tab — Lectura ejecutiva, Economía unitaria, Vuelos — renders with no
console errors. Marked ``browser`` only (not ``local_data``), same as
``test_web_flights_smoke.py``, so it is CI-capable once Playwright is
enabled there — see docs/arquitectura/auditoria-arquitectura-20260926.md
§2.5 and web/README.md.
"""

from __future__ import annotations

import json
import os
import threading
from functools import partial
from http.server import ThreadingHTTPServer
from pathlib import Path
from typing import Any

import pytest

playwright_sync_api = pytest.importorskip("playwright.sync_api")
sync_playwright = playwright_sync_api.sync_playwright

# noqa: E402 below — these imports come after pytest.importorskip on purpose.
from src.web_export.executive import export_executive  # noqa: E402
from src.web_export.flights import export_flights  # noqa: E402
from src.web_export.writer import write_json  # noqa: E402
from web.serve import WEB_ROOT, SimpleHTTPRequestHandler  # noqa: E402

pytestmark = pytest.mark.browser


def _chromium_executable() -> str | None:
    candidate = Path("/opt/pw-browsers/chromium-1194/chrome-linux/chrome")
    return str(candidate) if candidate.exists() else None


def _load_fixture(name: str) -> dict[str, Any]:
    path = Path(__file__).resolve().parent / "fixtures" / "web" / name
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def web_server(tmp_path_factory):
    """Serve a temp copy of web/ whose public/data/v1 holds only the
    synthetic, public fixtures — no local warehouse or analysis_runs/."""

    root = tmp_path_factory.mktemp("web_page_smoke")
    for name in ("index.html", "src", "vendor"):
        os.symlink(WEB_ROOT / name, root / name)

    out_dir = root / "public" / "data" / "v1"
    flights_fixture = _load_fixture("flights_sample.json")
    flights_payload = {**flights_fixture, "international_networks": flights_fixture["route_networks"]}
    export_flights(flights_payload, out_dir, skip_input_check=True)
    export_executive(_load_fixture("executive_sample.json"), out_dir, skip_input_check=True)
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
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(executable_path=_chromium_executable())
        page = browser.new_page()
        page.route("**/favicon.ico", lambda route: route.fulfill(status=204, body=""))

        def on_console_error(message: Any) -> None:
            if message.type == "error":
                console_errors.append(message.text)

        page.on("console", on_console_error)
        page.on("pageerror", lambda error: console_errors.append(str(error)))
        page.goto(web_server)
        page.wait_for_function("document.getElementById('period-display').textContent !== '—'")
        yield page, console_errors
        browser.close()


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
    assert console_errors == []


def test_flights_tab_renders_the_synthetic_fixture(page_with_console_capture) -> None:
    page, console_errors = page_with_console_capture
    page.click("#tab-flights")
    page.wait_for_selector("#network-volume:not([hidden])")
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
