"""Browser smoke for the opt-in chat UI with an in-process fake chat API."""

import os
import shutil
import socket
import subprocess
import time
from pathlib import Path
from urllib.error import URLError
from urllib.parse import urlsplit
from urllib.request import urlopen

import pytest

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "web"
pytestmark = pytest.mark.browser


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def test_chat_panel_browser_smoke_with_mock_backend() -> None:
    playwright = pytest.importorskip("playwright.sync_api")
    chromium_path = next(
        (str(path) for path in [Path("/opt/pw-browsers/chromium-1194/chrome-linux/chrome")] if path.exists()),
        None,
    )
    chromium_path = (
        chromium_path
        or shutil.which("chromium")
        or shutil.which("chromium-browser")
        or shutil.which("google-chrome")
    )
    if not chromium_path:
        pytest.skip("No hay Chromium instalado para el smoke de navegador.")

    port = _free_port()
    env = {**os.environ, "VITE_CHAT_ENABLED": "true", "VITE_CHAT_API_URL": "/api/chat"}
    server = subprocess.Popen(
        ["npm", "run", "dev", "--", "--host", "127.0.0.1", "--port", str(port), "--strictPort"],
        cwd=WEB,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        ready = False
        for _ in range(80):
            if server.poll() is not None:
                pytest.fail("Vite terminó antes de quedar disponible.")
            try:
                with urlopen(f"http://127.0.0.1:{port}", timeout=1):
                    ready = True
                    break
            except (URLError, TimeoutError):
                time.sleep(0.2)
        assert ready, "Vite no inició a tiempo"

        with playwright.sync_playwright() as p:
            try:
                browser = p.chromium.launch(
                    headless=True, executable_path=chromium_path, args=["--no-sandbox"]
                )
            except Exception as error:  # browser binaries can exist but lack system libraries
                pytest.skip(f"Chromium no pudo iniciarse: {error}")
            page = browser.new_page(viewport={"width": 1280, "height": 900})
            sent_context: list[dict[str, object]] = []

            def fake_api(route: object) -> None:
                request = route.request  # type: ignore[attr-defined]
                path = urlsplit(request.url).path.split("/api/chat", 1)[-1]
                if path == "/health":
                    route.fulfill(json={"status": "ok", "snapshot_version": "snapshot-smoke"})  # type: ignore[attr-defined]
                elif path == "/conversations" and request.method == "POST":
                    route.fulfill(
                        json={
                            "id": "conversation-smoke",
                            "snapshot_version": "snapshot-smoke",
                            "created_at": "2026-10-04T00:00:00Z",
                        }
                    )  # type: ignore[attr-defined]
                elif path.endswith("/messages") and request.method == "POST":
                    sent_context.append(request.post_data_json["context"])
                    route.fulfill(json={"turn_id": "turn-smoke", "status": "queued"})  # type: ignore[attr-defined]
                elif path.endswith("/events"):
                    body = (
                        'id: 1\nevent: turn.started\ndata: {"turn_id":"turn-smoke"}\n\n'
                        "id: 2\nevent: message.delta\ndata: "
                        '{"turn_id":"turn-smoke","text":"Respuesta **segura**."}\n\n'
                        "id: 3\nevent: message.completed\ndata: "
                        '{"turn_id":"turn-smoke","content":"Respuesta **segura**.",'
                        '"references":[{"label":"Fuente",'
                        '"url":"https://www.gob.mx/afac/estadisticas"}],"chart":null}\n\n'
                        'id: 4\nevent: turn.completed\ndata: {"turn_id":"turn-smoke"}\n\n'
                    )
                    route.fulfill(status=200, content_type="text/event-stream", body=body)  # type: ignore[attr-defined]
                else:
                    route.fulfill(status=404, json={"detail": f"No mock for {path}"})  # type: ignore[attr-defined]

            page.route("**/api/chat/**", fake_api)
            page.goto(f"http://127.0.0.1:{port}", wait_until="domcontentloaded")
            launcher = page.get_by_role("button", name="Abrir Airline Tracker chat analítico")
            launcher.wait_for(state="visible", timeout=20_000)
            launcher.click()
            page.get_by_label("Pregunta sobre los datos publicados").fill("¿Cómo cambió la ocupación?")
            page.get_by_role("button", name="Enviar").click()
            page.get_by_text("Respuesta segura.").wait_for(timeout=10_000)
            assert sent_context and sent_context[0]["tab"] == "reading"
            assert sent_context[0]["period"]
            assert (
                page.get_by_role("link", name="Fuente", exact=True).get_attribute("rel")
                == "noopener noreferrer"
            )
            page.keyboard.press("Escape")
            assert launcher.get_attribute("aria-expanded") == "false"

            reading_entity = page.locator("#carrier-reading")
            if reading_entity.count():
                reading_entity.select_option("VOLARIS")
                page.get_by_role("button", name="Preguntar sobre esta gráfica").click()
                page.get_by_label("Pregunta sobre los datos publicados").fill("Explícame esta lectura")
                page.get_by_role("button", name="Enviar").click()
                page.get_by_text("Respuesta segura.").last.wait_for(timeout=10_000)
                assert sent_context[1]["card_id"] == "reading-card"
                assert sent_context[1]["entity"] == "VOLARIS"
                page.keyboard.press("Escape")

            page.locator(".chart-card .chat-card-action").first.click()
            page.get_by_label("Pregunta sobre los datos publicados").fill("Explícame esta gráfica")
            page.get_by_role("button", name="Enviar").click()
            page.get_by_text("Respuesta segura.").last.wait_for(timeout=10_000)
            market_index = len(sent_context) - 1
            assert sent_context[market_index]["card_id"] == "market-chart"
            assert sent_context[market_index]["filters"]["segment"] == "total"  # type: ignore[index]
            page.keyboard.press("Escape")

            page.set_viewport_size({"width": 390, "height": 844})
            launcher.click()
            assert page.locator("#airline-chat-panel").is_visible()
            assert (
                page.locator("#airline-chat-panel").evaluate("node => getComputedStyle(node).width")
                == "390px"
            )
            browser.close()
    finally:
        server.terminate()
        try:
            server.wait(timeout=5)
        except subprocess.TimeoutExpired:
            server.kill()
