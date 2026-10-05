"""Browser smoke coverage for the private, local-only answer review UI.

The test uses only an in-memory synthetic dataset and the built static site.
It never reads the private evaluation output directory.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import pytest

playwright_sync_api = pytest.importorskip("playwright.sync_api")
sync_playwright = playwright_sync_api.sync_playwright

pytestmark = pytest.mark.browser


def _chromium_executable() -> str | None:
    candidate = Path("/opt/pw-browsers/chromium-1194/chrome-linux/chrome")
    return str(candidate) if candidate.exists() else None


def _synthetic_dataset() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "dataset_id": "a" * 64,
        "available_count": 4,
        "questions": [
            {
                "id": "Q01",
                "question": "Pregunta sintética uno",
                "language": "es",
                "expected": {"summary": "Respuesta esperada sintética"},
                "candidates": [
                    {"alias": "A", "answer": '<img src=x onerror="window.__reviewXss=1">'},
                    {"alias": "B", "answer": "Respuesta normal sintética"},
                    {"alias": "C", "answer": None},
                ],
            },
            {
                "id": "Q02",
                "question": "Pregunta sintética dos",
                "language": "en",
                "expected": "Expected synthetic answer",
                "candidates": [
                    {"alias": "A", "answer": "<script>window.__reviewXss=2</script>"},
                    {"alias": "B", "answer": "Another synthetic answer"},
                    {"alias": "C", "answer": None},
                ],
            },
        ],
    }


@pytest.fixture(scope="module")
def review_server(tmp_path_factory, web_dist_dir):
    root = tmp_path_factory.mktemp("web_review_smoke")
    shutil.copytree(web_dist_dir, root, dirs_exist_ok=True)
    handler = partial(SimpleHTTPRequestHandler, directory=str(root))
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}/review.html"
    finally:
        server.shutdown()
        thread.join()


@pytest.mark.parametrize("width", [390, 1040])
def test_review_import_rating_export_and_local_recovery(review_server, width: int) -> None:
    dataset = _synthetic_dataset()
    dataset_bytes = (json.dumps(dataset, ensure_ascii=False, separators=(",", ":")) + "\n").encode()
    expected_sha = hashlib.sha256(dataset_bytes).hexdigest()
    origin = f"{urlparse(review_server).scheme}://{urlparse(review_server).netloc}"

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(executable_path=_chromium_executable())
        page = browser.new_page(viewport={"width": width, "height": 900})
        requests: list[tuple[str, str, str]] = []
        page.on(
            "request",
            lambda request: requests.append(
                (request.url, request.method, request.resource_type)
            ),
        )
        page.route("**/favicon.ico", lambda route: route.fulfill(status=204, body=""))
        page.goto(review_server)

        page.locator("#dataset-file").set_input_files(
            {"name": "synthetic-review.json", "mimeType": "application/json", "buffer": dataset_bytes}
        )
        page.locator("#review-workspace").wait_for(state="visible")
        assert page.locator("#progress-count").inner_text() == "0 / 4"
        assert page.locator("#expected-summary").inner_text()
        assert page.locator("#candidate-list .missing-answer").count() == 1
        assert page.locator('input[name="rating-Q01-C"]').count() == 0
        assert page.locator(".candidate-answer img, .candidate-answer script").count() == 0
        assert page.evaluate("window.__reviewXss ?? 0") == 0
        assert '<img src=x onerror="window.__reviewXss=1">' in (
            page.locator(".candidate-answer").first.inner_text()
        )

        page.locator('input[name="rating-Q01-A"][value="correct"]').check()
        page.get_by_label("Notas para candidato A").fill("Nota sintética de revisión")
        page.locator("#next-question").click()
        assert "Q02" in page.locator("#question-position").inner_text()
        assert page.locator(".candidate-answer img, .candidate-answer script").count() == 0
        assert page.evaluate("window.__reviewXss ?? 0") == 0
        assert "<script>window.__reviewXss=2</script>" in (
            page.locator(".candidate-answer").first.inner_text()
        )
        page.locator('input[name="rating-Q02-B"][value="problem"]').check()
        page.get_by_label("Notas para candidato B").fill("Problema sintético")
        assert page.locator("#progress-count").inner_text() == "2 / 4"
        assert page.locator("#count-correct").inner_text() == "1"
        assert page.locator("#count-problem").inner_text() == "1"

        page.locator("#question-filter").select_option("problems")
        assert page.locator("#question-nav button").count() == 1
        assert "Q02" in page.locator("#question-position").inner_text()
        page.locator("#question-filter").select_option("all")
        page.locator('#question-nav button[data-question-index="0"]').click()
        assert "Q01" in page.locator("#question-position").inner_text()

        with page.expect_download() as download_info:
            page.locator("#export-button").click()
        download = download_info.value
        export_path = Path(download.path())
        exported = json.loads(export_path.read_text(encoding="utf-8"))
        assert exported["dataset_content_sha256"] == expected_sha
        assert exported["dataset_id"] == dataset["dataset_id"]
        assert exported["ratings"] == [
            {"question_id": "Q01", "alias": "A", "status": "correct", "notes": "Nota sintética de revisión"},
            {"question_id": "Q02", "alias": "B", "status": "problem", "notes": "Problema sintético"},
        ]
        exported_text = json.dumps(exported, ensure_ascii=False)
        assert all(
            candidate["answer"] not in exported_text
            for question in dataset["questions"]
            for candidate in question["candidates"]
            if candidate["answer"]
        )

        page.reload()
        page.locator("#dataset-file").set_input_files(
            {"name": "synthetic-review.json", "mimeType": "application/json", "buffer": dataset_bytes}
        )
        page.locator("#review-workspace").wait_for(state="visible")
        assert page.locator("#progress-count").inner_text() == "2 / 4"
        assert page.locator('input[name="rating-Q01-A"][value="correct"]').is_checked()
        assert page.get_by_label("Notas para candidato A").input_value() == "Nota sintética de revisión"

        page.wait_for_timeout(100)
        assert all(urlparse(url).netloc == urlparse(origin).netloc for url, _, _ in requests)
        assert all(urlparse(url).scheme == urlparse(origin).scheme for url, _, _ in requests)
        assert all(method == "GET" for _, method, _ in requests)
        assert all(
            urlparse(url).path == "/favicon.ico"
            or resource_type in {"document", "script", "stylesheet", "image", "font"}
            for url, _, resource_type in requests
        )
        assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")

        if os.environ.get("CHAT_REVIEW_SMOKE_SCREENSHOT") == "1":
            screenshot_dir = Path(".state/outputs/chat-review-ui")
            screenshot_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
            os.chmod(screenshot_dir, 0o700)
            screenshot = screenshot_dir / f"review-synthetic-{width}.png"
            page.screenshot(path=str(screenshot), full_page=True)
            os.chmod(screenshot, 0o600)
        browser.close()
