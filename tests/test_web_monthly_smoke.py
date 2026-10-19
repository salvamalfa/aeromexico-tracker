"""Real editorial preview in Chromium, offline, at desktop and mobile widths."""

from __future__ import annotations

import pytest
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

from scripts.monthly.build_preview import build

playwright = pytest.importorskip("playwright.sync_api")
pytestmark = pytest.mark.browser


def test_ordinary_build_excludes_editorial_drafts(web_dist_dir):
    assert not (web_dist_dir / "monthly.html").exists()
    assert 'aria-label="Productos"' not in (web_dist_dir / "index.html").read_text()
    for path in (web_dist_dir / "assets").glob("*.js"):
        assert "Tres maneras de ajustar la capacidad" not in path.read_text()


@pytest.fixture
def preview_url(tmp_path):
    build(tmp_path / "monthly.html")
    server = ThreadingHTTPServer(("127.0.0.1", 0), partial(SimpleHTTPRequestHandler, directory=str(tmp_path)))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/monthly.html"
    finally:
        server.shutdown()
        thread.join()


@pytest.mark.parametrize("width", [320, 390, 1280])
def test_monthly_offline_reading_navigation_and_sources(preview_url, width):
    with playwright.sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page(viewport={"width": width, "height": 900})
        errors, network = [], []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.on("request", lambda request: network.append(request.url))
        page.route("**/*", lambda route: route.continue_() if route.request.url.split("#")[0] == preview_url else route.abort())
        page.goto(preview_url)
        page.get_by_role("heading", name="Airline Monthly", exact=True).wait_for()
        assert page.get_by_text("Piloto · Borrador para revisión", exact=True).is_visible()
        page.keyboard.press("Tab")
        assert page.locator(".skip-link").evaluate("el => el === document.activeElement")
        page.keyboard.press("Enter")
        assert page.locator("#monthly-content").evaluate("el => el === document.activeElement")
        assert page.locator("#analisis").count() == 1
        assert page.locator("tbody tr").count() == 3
        assert page.locator("#fuentes ol li").count() == 6
        assert page.locator("input, form").count() == 0
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        links = page.locator("a.citation").evaluate_all("links => links.map(a => ({href: a.href, label: a.getAttribute('aria-label')}))")
        assert links and all(link["href"].startswith("https://") and "2026" in link["label"] for link in links)
        page.get_by_role("navigation", name="Índice de la edición").get_by_role("link", name="Análisis", exact=True).click()
        playwright.expect(page.locator("#analisis h2")).to_be_focused()
        page.get_by_role("link", name="Archivo mensual", exact=True).click()
        playwright.expect(page.get_by_role("heading", name="Archivo mensual", exact=True)).to_be_visible()
        assert page.locator(".archive-list article").count() == 1
        page.go_back()
        page.locator("#analisis h2").wait_for()
        page.reload()
        assert page.locator("#analisis h2").is_visible()
        page.goto(preview_url + "#edicion/2026-08")
        playwright.expect(page.get_by_role("heading", name="Edición no disponible", exact=True)).to_be_visible()
        assert not errors
        assert all(url.split("#")[0] == preview_url for url in network)
        browser.close()
