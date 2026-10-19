import json

import pandas as pd
import pytest

from src.common.storage import save_bronze
from src.config import ProjectPaths
from src.source_updates.news import build_from_bronze


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
