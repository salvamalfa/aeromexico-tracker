from __future__ import annotations

import json
import sys

import httpx
import pytest

from scripts.news import prepare_monthly_cut as cut
from src.config import ProjectPaths


@pytest.mark.parametrize(
    "target",
    [
        "http://ir.aeromexico.com/final.pdf",
        "https://user:password@ir.aeromexico.com/final.pdf",
        "https://unapproved.example/final.pdf",
        "/final.pdf",
    ],
)
def test_capture_validates_every_redirect_before_fetching(monkeypatch, tmp_path, target):
    source = "https://ir.aeromexico.com/source.pdf"
    input_path = tmp_path / "input.json"
    output_path = tmp_path / "candidate.json"
    input_path.write_text(
        json.dumps(
            [
                {
                    "id": "source",
                    "kind": "news",
                    "companies": ["Aeroméxico"],
                    "title": "Reporte mensual",
                    "description": "Resumen original breve.",
                    "source_url": source,
                    "published_at": "2026-10-01",
                    "publisher": "Aeroméxico",
                }
            ]
        )
    )
    paths = ProjectPaths(root=tmp_path)
    monkeypatch.setattr(cut, "PATHS", paths)
    monkeypatch.setattr(
        sys, "argv", ["cut", "--input", str(input_path), "--out", str(output_path), "--capture"]
    )
    calls = []

    def handle(request):
        calls.append(str(request.url))
        if str(request.url) == source:
            return httpx.Response(302, headers={"location": target})
        return httpx.Response(200, content=b"%PDF-1.7\nPublic source fixture")

    real_client = httpx.Client
    monkeypatch.setattr(
        cut.httpx, "Client", lambda **kwargs: real_client(transport=httpx.MockTransport(handle), **kwargs)
    )
    if target != "/final.pdf":
        with pytest.raises(ValueError, match="bounded HTTPS"):
            cut.main()
        assert calls == [source]
        assert not output_path.exists()
        assert not (paths.bronze / "news" / "review").exists()
    else:
        cut.main()
        assert calls == [source, "https://ir.aeromexico.com/final.pdf"]
        payload = json.loads(output_path.read_text())
        assert payload["records"][0]["source"]["url"] == calls[-1]
        assert payload["records"][0]["review_status"] == "candidate_unapproved"
