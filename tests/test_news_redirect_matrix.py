"""A captured hash must describe a fetched HTTP-200 response, never redirect HTML."""

from __future__ import annotations

import hashlib
import json
import sys

import httpx
import pytest

from scripts.news import prepare_monthly_cut as cut
from src.config import ProjectPaths


def setup_capture(monkeypatch, tmp_path, handler, items=None):
    source = "https://ir.aeromexico.com/source"
    row = {
        "id": "source",
        "kind": "news",
        "companies": ["Aeroméxico"],
        "title": "Reporte mensual",
        "description": "Resumen original breve.",
        "source_url": source,
        "published_at": "2026-10-01",
        "publisher": "Aeroméxico",
    }
    input_path = tmp_path / "input.json"
    output = tmp_path / "candidate.json"
    input_path.write_text(json.dumps(items or [row]))
    paths = ProjectPaths(root=tmp_path)
    monkeypatch.setattr(cut, "PATHS", paths)
    monkeypatch.setattr(sys, "argv", ["cut", "--input", str(input_path), "--out", str(output), "--capture"])
    real_client = httpx.Client
    monkeypatch.setattr(
        cut.httpx, "Client", lambda **kwargs: real_client(transport=httpx.MockTransport(handler), **kwargs)
    )
    return source, output, paths.bronze / "news/review", row


@pytest.mark.parametrize("status", [301, 302, 303, 307, 308])
@pytest.mark.parametrize("redirects", range(6))
def test_complete_redirect_budget_matrix(monkeypatch, tmp_path, status, redirects):
    calls = []
    final = b"%PDF-1.7\nACTUAL FINAL RESPONSE"

    def handler(request):
        calls.append(str(request.url))
        step = len(calls) - 1
        if step < redirects:
            return httpx.Response(
                status,
                headers={"location": f"/hop-{step + 1}"},
                content=f"<html>REDIRECT BODY {step}</html>".encode(),
            )
        return httpx.Response(200, content=final)

    source, output, folder, _ = setup_capture(monkeypatch, tmp_path, handler)
    if redirects >= 4:
        with pytest.raises(ValueError, match="limit exhausted"):
            cut.main()
        assert len(calls) == 4
        assert not output.exists() and not folder.exists()
    else:
        cut.main()
        assert len(calls) == redirects + 1
        row = json.loads(output.read_text())["records"][0]
        assert row["source"]["url"] == calls[-1]
        assert row["source"]["sha256"] == hashlib.sha256(final).hexdigest()
        assert row["verification"] == "http_200_source_hash"
        assert next(folder.glob("*.pdf")).read_bytes() == final
        assert not list(folder.glob("*.html"))


@pytest.mark.parametrize("step", range(4))
@pytest.mark.parametrize(
    "target",
    [
        "http://ir.aeromexico.com/evil",
        "https://user:password@ir.aeromexico.com/evil",
        "https://unapproved.invalid/evil",
    ],
)
def test_every_allowed_hop_validates_the_next_target_without_fetching_it(monkeypatch, tmp_path, step, target):
    calls = []

    def handler(request):
        calls.append(str(request.url))
        n = len(calls) - 1
        return httpx.Response(
            302,
            headers={"location": target if n == step else f"/hop-{n + 1}"},
            content=b"<html>redirect</html>",
        )

    _, output, folder, _ = setup_capture(monkeypatch, tmp_path, handler)
    with pytest.raises(ValueError, match="bounded HTTPS"):
        cut.main()
    assert len(calls) == step + 1 and target not in calls
    assert not output.exists() and not folder.exists()


@pytest.mark.parametrize("location", [None, "", "   "])
def test_missing_redirect_destination_is_not_a_source(monkeypatch, tmp_path, location):
    def handler(request):
        return httpx.Response(
            302, headers={} if location is None else {"location": location}, content=b"<html>redirect</html>"
        )

    _, output, folder, _ = setup_capture(monkeypatch, tmp_path, handler)
    with pytest.raises(ValueError, match="missing Location"):
        cut.main()
    assert not output.exists() and not folder.exists()


@pytest.mark.parametrize("status", [201, 202, 204, 206, 304, 400, 403, 429, 500])
def test_only_complete_http_200_is_verified(monkeypatch, tmp_path, status):
    def handler(request):
        return httpx.Response(status, content=b"%PDF-1.7\nnot a complete 200 response")

    _, output, folder, _ = setup_capture(monkeypatch, tmp_path, handler)
    with pytest.raises((ValueError, httpx.HTTPStatusError)):
        cut.main()
    assert not output.exists() and not folder.exists()


def test_failed_later_source_preserves_valid_earlier_capture_without_publishing_a_cut(monkeypatch, tmp_path):
    calls = []
    final = b"%PDF-1.7\nFIRST REAL DOCUMENT"

    def handler(request):
        calls.append(str(request.url))
        if request.url.path == "/source":
            return httpx.Response(200, content=final)
        return httpx.Response(302, headers={"location": "/loop"}, content=b"<html>redirect only</html>")

    _, output, folder, row = setup_capture(monkeypatch, tmp_path, handler)
    (tmp_path / "input.json").write_text(
        json.dumps([row, {**row, "id": "second", "source_url": "https://ir.aeromexico.com/loop"}])
    )
    with pytest.raises(ValueError, match="limit exhausted"):
        cut.main()
    assert len(calls) == 5 and not output.exists()
    assert [p.read_bytes() for p in folder.glob("*.pdf")] == [final]
    metadata = [json.loads(p.read_text()) for p in (folder / "captures").glob("*.json")]
    assert len(metadata) == 1 and metadata[0]["url"] == "https://ir.aeromexico.com/source"
    assert not list(folder.glob("*.html"))
