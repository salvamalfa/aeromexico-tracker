"""The monthly tooling keeps unknown GDELT publication separate from publisher dates."""

import json
from contextlib import nullcontext
from urllib.parse import parse_qs, urlsplit

import pandas as pd
import pytest

from src.common.storage import save_bronze
from src.config import ProjectPaths
from src.source_updates.news import build_from_bronze


@pytest.fixture
def closed_candidate(tmp_path, monkeypatch):
    import src.config as config
    import src.ingest.news.rss_gdelt as parser
    import src.ingest.stage4_common as common

    paths = ProjectPaths(root=tmp_path)
    paths.ensure_runtime_directories()
    for module in (config, parser, common):
        monkeypatch.setattr(module, "PATHS", paths)
    return paths


@pytest.mark.parametrize("seen", ["20260831T235900Z", "20260901T120000Z", "20261001T000000Z"])
def test_undated_gdelt_keeps_observation_and_capture_without_overwriting_accepted_silver(
    closed_candidate, seen
):
    paths = closed_candidate
    content = json.dumps(
        {"articles": [{"title": "Fixture", "url": "https://example.test/story", "seendate": seen}]}
    ).encode()
    original = save_bronze(
        content,
        "gdelt",
        "aeromexico_articles",
        "current",
        "json",
        "https://api.gdeltproject.org/api/v2/doc/doc",
        "manual",
        bronze_root=paths.bronze,
    )
    accepted = paths.silver / "news_headlines.parquet"
    accepted.write_bytes(b"previous accepted output remains untouched")
    with pytest.raises(ValueError, match="No dated news metadata"):
        build_from_bronze()
    assert accepted.read_bytes() == b"previous accepted output remains untouched"
    assert original.read_bytes() == content
    receipt = json.loads((paths.quality / "news_metadata_selection.json").read_text())
    unknown = receipt["publication_unknown_metadata"]
    assert len(unknown) == 1 and unknown[0]["published_at"] is None
    assert pd.Timestamp(unknown[0]["first_seen_at"]) == pd.to_datetime(seen, utc=True)
    assert unknown[0]["first_captured_at"] == unknown[0]["ingested_at"]
    assert (
        unknown[0]["source_hash"] == json.loads(original.with_suffix(".json.meta.json").read_text())["sha256"]
    )
    assert receipt["superseded_editions"] == []


def test_legacy_collector_and_monthly_recipe_share_all_three_airline_queries(monkeypatch, tmp_path):
    from src.ingest.news import rss_gdelt as parser
    from src.source_updates.recipes import catalog_selection

    calls = []

    def capture(client, url, **kwargs):
        calls.append((url, kwargs))
        return tmp_path / "fixture"

    monkeypatch.setattr(parser, "SourceHttpClient", lambda *args, **kwargs: nullcontext(object()))
    monkeypatch.setattr(parser, "fetch_bronze", capture)
    monkeypatch.setattr(parser, "_parse_rss", lambda *args: [])
    monkeypatch.setattr(parser, "_parse_gdelt", lambda *args: [])
    monkeypatch.setattr(parser, "build_from_bronze", lambda: {"rows": 0})
    assert parser.run()["failures"] == []
    direct = next(options["params"] for _, options in calls if options["source_system"] == "gdelt")
    recipe = parse_qs(urlsplit(catalog_selection("gdelt")["items"][0]["url"]).query)
    assert recipe == {key: [value] for key, value in direct.items()}
    assert direct["query"].startswith("(") and direct["query"].endswith(")")
    for company in ["Aeromexico", "Viva Aerobus", "Volaris"]:
        assert company in direct["query"]
        assert all(
            company in parse_qs(urlsplit(parser.RSS_FEEDS[feed]).query)["q"][0]
            for feed in ["google_es", "google_en"]
        )
