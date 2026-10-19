import json
import shutil
from uuid import uuid4

import httpx
import pytest

from src.source_updates.catalog import ROOT
from src.source_updates.collection import collect


@pytest.mark.parametrize("html_base", [False, True])
def test_catalog_links_follow_validated_response_directory_and_retain_both_urls(html_base):
    workspace = ROOT / "tmp/source-updates" / ("catalog-redirect-" + uuid4().hex)
    initial = "https://www.eia.gov/old"
    final = "https://www.eia.gov/reports/2026/"
    expected = "https://www.eia.gov/reports/" + ("archive/" if html_base else "2026/") + "q3.pdf"
    calls = []

    class Client:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def request(self, method, url, **kwargs):
            calls.append(url)
            request = httpx.Request(method, url)
            if len(calls) == 1:
                return httpx.Response(302, headers={"location": "/reports/2026/"}, request=request)
            head = '<base href="../archive/">' if html_base else ""
            html = "<html><head>" + head + '</head><body><a href="q3.pdf">Q3</a>'
            html += '<a href="?auth[token]=synthetic-fixture">Blocked</a></body></html>'
            return httpx.Response(200, text=html, request=request)

    item = {
        "id": "catalog",
        "product": "fuel",
        "source_system": "eia",
        "entity": "catalog",
        "period": "current",
        "purpose": "catalog",
        "url": initial,
        "extension": "html",
        "mode": "get",
    }
    try:
        result = collect({"version": 1, "items": [item]}, workspace, execute=True, client_factory=Client)
        assert result["status"] == "collected_unvalidated"
        row = result["items"][0]
        assert calls == [initial, final]
        assert row["source_url"] == initial  # Stable requested identity for downstream catalogue matching.
        assert row["response_url"] == final
        assert row["discovered_links"] == [{"url": expected, "label": "Q3"}]
        path = workspace / "data/bronze" / row["source_file"]
        metadata = json.loads(path.with_suffix(".html.meta.json").read_text())
        assert metadata["source_url"] == initial
        assert "response_url=" + final in metadata["notes"]
    finally:
        shutil.rmtree(workspace, ignore_errors=True)
