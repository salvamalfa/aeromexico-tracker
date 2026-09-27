"""CI-runnable smoke test for web/: serves it with a synthetic, public
fixture (no warehouse) and checks the Vuelos view renders with no console
errors. Marked ``browser`` only (not ``local_data``) so it is the one test
in this package that could run once CI enables Playwright — see web/README.md.
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
    holds only the synthetic fixture, over HTTP (fetch() needs http:, not
    file:). See test_web_page_smoke.py's web_server for why data/v1 (not
    public/data/v1) is the right path against the built site."""

    root = tmp_path_factory.mktemp("web_smoke")
    shutil.copytree(web_dist_dir, root, dirs_exist_ok=True)

    out_dir = root / "data" / "v1"
    fixture = _load_fixture("flights_sample.json")
    payload = {**fixture, "international_networks": fixture["route_networks"]}
    export_flights(payload, out_dir, skip_input_check=True)
    # main.js now mounts the executive/economy tabs too (see web/index.html),
    # so this page needs their payload even though this test only exercises
    # panel-flights (now behind the "Vuelos" tab, see mountTabs()).
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


def test_flights_view_renders_the_synthetic_fixture_without_console_errors(web_server) -> None:
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
        page.click("#tab-flights")
        page.wait_for_selector("#network-volume:not([hidden])")
        assert page.inner_text("#period-display") == "2T26"
        assert page.inner_text("#flight-kpi-passengers") != "—"
        browser.close()
    assert console_errors == []


def test_region_map_refits_its_bounds_when_the_canvas_resizes(web_server) -> None:
    # fitViewToCanvas freezes lat/lon ranges to the canvas aspect; a resize
    # that changes the canvas width must recompute them (Codex finding #8).
    read_map_bounds = (
        "() => { const g = document.getElementById('route-flow-map');"
        " if (!g || !g.layout) return null;"
        " return JSON.stringify([g.layout.geo.lataxis.range, g.layout.geo.lonaxis.range]); }"
    )
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(executable_path=_chromium_executable())
        page = browser.new_page(viewport={"width": 1400, "height": 900})
        page.route("**/favicon.ico", lambda route: route.fulfill(status=204, body=""))
        page.goto(web_server)
        page.click("#tab-flights")
        page.wait_for_selector("#network-volume:not([hidden])")
        # A region view uses fitViewToCanvas (the world view does not).
        page.click("#network-region-switch button")
        page.wait_for_function(f"({read_map_bounds})() !== null")
        wide = page.evaluate(read_map_bounds)
        page.set_viewport_size({"width": 700, "height": 900})
        page.wait_for_function(
            f"({read_map_bounds})() !== {json.dumps(wide)}", timeout=5000
        )
        narrow = page.evaluate(read_map_bounds)
        browser.close()
    assert narrow != wide


def test_region_map_refits_when_only_the_canvas_height_changes(web_server) -> None:
    # Below 700px the map keeps a 700px min-width while its height drops at
    # the 420px breakpoint: the refit must track height, not only width.
    read_map_bounds = (
        "() => { const g = document.getElementById('route-flow-map');"
        " if (!g || !g.layout) return null;"
        " return JSON.stringify([g.layout.geo.lataxis.range, g.layout.geo.lonaxis.range]); }"
    )
    read_size = (
        "() => { const c = document.getElementById('route-flow-map');"
        " return [c.clientWidth, c.clientHeight]; }"
    )
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(executable_path=_chromium_executable())
        page = browser.new_page(viewport={"width": 600, "height": 900})
        page.route("**/favicon.ico", lambda route: route.fulfill(status=204, body=""))
        page.goto(web_server)
        page.click("#tab-flights")
        page.wait_for_selector("#network-volume:not([hidden])")
        page.click("#network-region-switch button")
        page.wait_for_function(f"({read_map_bounds})() !== null")
        # Record the pre-breakpoint size through a resize event first.
        page.set_viewport_size({"width": 599, "height": 900})
        page.wait_for_timeout(300)
        before_size = page.evaluate(read_size)
        before = page.evaluate(read_map_bounds)
        page.set_viewport_size({"width": 400, "height": 900})
        after_size = page.evaluate(read_size)
        if after_size[0] != before_size[0] or after_size[1] == before_size[1]:
            browser.close()
            pytest.skip(f"layout did not isolate a height-only change: {before_size} -> {after_size}")
        page.wait_for_function(f"({read_map_bounds})() !== {json.dumps(before)}", timeout=5000)
        browser.close()


def test_region_map_refits_after_a_hidden_tab_redraw(web_server) -> None:
    # Resize A->B visibly, B->A while Vuelos is hidden, reopen (redraw at A),
    # then resize to B again: the resize guard must compare against the size
    # of the latest draw, not the last resize it saw (Codex finding on #70).
    read_map_bounds = (
        "() => { const g = document.getElementById('route-flow-map');"
        " if (!g || !g.layout) return null;"
        " return JSON.stringify([g.layout.geo.lataxis.range, g.layout.geo.lonaxis.range]); }"
    )
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(executable_path=_chromium_executable())
        page = browser.new_page(viewport={"width": 1400, "height": 900})
        page.route("**/favicon.ico", lambda route: route.fulfill(status=204, body=""))
        page.goto(web_server)
        page.click("#tab-flights")
        page.wait_for_selector("#network-volume:not([hidden])")
        page.click("#network-region-switch button")
        page.wait_for_function(f"({read_map_bounds})() !== null")
        at_a = page.evaluate(read_map_bounds)
        page.set_viewport_size({"width": 1000, "height": 900})
        page.wait_for_function(f"({read_map_bounds})() !== {json.dumps(at_a)}", timeout=5000)
        page.click("#tab-reading")
        page.set_viewport_size({"width": 1400, "height": 900})
        page.wait_for_timeout(300)
        page.click("#tab-flights")
        page.wait_for_function(f"({read_map_bounds})() === {json.dumps(at_a)}", timeout=5000)
        page.set_viewport_size({"width": 1000, "height": 900})
        page.wait_for_function(f"({read_map_bounds})() !== {json.dumps(at_a)}", timeout=5000)
        browser.close()
