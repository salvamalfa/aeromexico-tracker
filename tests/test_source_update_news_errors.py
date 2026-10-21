import json
from copy import deepcopy

import httpx
import pandas as pd
import pytest

from src.common.storage import save_bronze
from src.config import ProjectPaths
from src.source_updates.news import build_from_bronze


@pytest.mark.parametrize("status", [200, 429])
def test_gdelt_collection_obeys_source_spacing_and_never_retries_429(tmp_path, monkeypatch, status):
    from src.common.http import SourceHttpClient, TokenBucket
    from src.config import RATE_LIMITS
    from src.source_updates import collection
    from src.source_updates.gdelt import recipe

    monkeypatch.setattr(collection, "ROOT", tmp_path)
    workspace = tmp_path / "tmp/source-updates/gdelt-rate"
    selected = recipe("2026M09", "2026-10-21T00:00:00Z")
    second = deepcopy(selected["items"][0])
    second["id"] = "second-diagnostic"
    selected["items"].append(second)
    now, calls, limiters = [0.0], [], {}

    def sleep(seconds):
        now[0] += seconds

    def handler(request):
        calls.append(now[0])
        return httpx.Response(status, json={"articles": []})

    def factory(source, **kwargs):
        # Exercise the actual collection->source routing, configured bucket,
        # HTTP retry policy and immutable failed-response receipt together.
        assert source == "gdelt"
        limiter = limiters.setdefault(
            source,
            TokenBucket(RATE_LIMITS[source], clock=lambda: now[0], sleeper=sleep),
        )
        return SourceHttpClient(source, limiter=limiter, transport=httpx.MockTransport(handler), **kwargs)

    result = collection.collect(selected, workspace, execute=True, client_factory=factory)
    if status == 200:
        assert calls == pytest.approx([0.0, 6.0])
        assert result["status"] == "collected_unvalidated"
    else:
        assert calls == [0.0]
        assert result["status"] == "incomplete"
        assert result["items"][0]["failed_response"]["http_status"] == 429
        assert result["items"][1]["status"] == "blocked_after_http_429"
        assert not (workspace / "data/bronze/_manifest.jsonl").exists()


def test_historical_http_200_gdelt_error_is_preserved_and_never_successful_empty_month(tmp_path, monkeypatch):
    import src.config as config
    import src.ingest.news.rss_gdelt as parser
    import src.ingest.stage4_common as common

    paths = ProjectPaths(root=tmp_path)
    paths.ensure_runtime_directories()
    for module in (config, parser, common):
        monkeypatch.setattr(module, "PATHS", paths)
    path = save_bronze(
        b"Queries containing OR'd terms must be surrounded by ().",
        "gdelt",
        "aeromexico_articles",
        "current",
        "json",
        "https://api.gdeltproject.org/api/v2/doc/doc",
        "manual",
        bronze_root=paths.bronze,
        http_status=200,
        content_type="text/html",
    )
    original = path.read_bytes()
    with pytest.raises(ValueError, match="No valid news metadata"):
        build_from_bronze()
    assert not (paths.silver / "news_headlines.parquet").exists()
    rss = b"""<rss version="2.0"><channel><item><title>Aeromexico fixture</title>
    <link>https://example.test/article</link><pubDate>Tue, 01 Sep 2026 12:00:00 GMT</pubDate>
    </item></channel></rss>"""
    save_bronze(
        rss,
        "rss",
        "google_es",
        "current",
        "xml",
        "https://news.google.com/rss/search",
        "manual",
        bronze_root=paths.bronze,
    )
    result = build_from_bronze()
    assert result["deduplicated_rows"] == 1
    assert result["source_completeness"] == "partial_invalid_captures"
    assert (
        result["invalid_artifacts_preserved"][0]["source_file"] == path.relative_to(paths.bronze).as_posix()
    )
    assert path.read_bytes() == original
    frame = pd.read_parquet(paths.silver / "news_headlines.parquet")
    assert set(frame.source_system) == {"rss"}
    assert all(item["source_system"] == "rss" for item in json.loads(frame.provenance_json.iloc[0]))
    newer = rss.replace(b"Tue, 01 Sep 2026 12:00:00 GMT", b"Wed, 02 Sep 2026 12:00:00 GMT")
    save_bronze(
        newer,
        "rss",
        "google_es",
        "current",
        "xml",
        "https://news.google.com/rss/search",
        "manual",
        bronze_root=paths.bronze,
    )
    result = build_from_bronze()
    assert result["superseded_editions_preserved_in_bronze"] == 1
    latest = pd.read_parquet(paths.silver / "news_headlines.parquet")
    assert len(latest) == 1 and latest.published_at.iloc[0].day == 2
    receipt = json.loads((paths.quality / "news_metadata_selection.json").read_text())
    assert "2026-09-01" in receipt["superseded_editions"][0]["published_at"]
