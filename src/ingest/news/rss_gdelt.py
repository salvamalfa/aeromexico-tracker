"""Limited news collection: RSS headlines and GDELT coverage metadata."""

from __future__ import annotations

from email.utils import parsedate_to_datetime
import json
from urllib.parse import quote_plus
from src.conversational_analytics.news_projection import canonical_news_url
import xml.etree.ElementTree as ET

import httpx
import pandas as pd

from src.common.http import SourceHttpClient
from src.common.quality import log_issue_once
from src.common.storage import save_bronze
from src.config import PATHS
from src.ingest.stage4_common import fetch_bronze, lineage, write_parquet_atomic


RSS_FEEDS = {
    "google_es": (
        "https://news.google.com/rss/search?q="
        + quote_plus('Aeroméxico OR Aeromexico OR "Viva Aerobus" OR Volaris')
        + "&hl=es-419&gl=MX&ceid=MX:es-419"
    ),
    "google_en": (
        "https://news.google.com/rss/search?q="
        + quote_plus('Aeromexico OR "Viva Aerobus" OR Volaris')
        + "&hl=en-US&gl=US&ceid=US:en"
    ),
    "el_economista_empresas": "https://www.eleconomista.com.mx/rss/empresas.xml",
}


def _preserve_http_failure(exc: Exception, entity: str, relative_dir: str) -> None:
    if not isinstance(exc, httpx.HTTPStatusError):
        return
    response = exc.response
    save_bronze(
        response.content,
        "news_http_error",
        entity,
        "current",
        "xml" if "xml" in response.headers.get("content-type", "") else "txt",
        str(response.url),
        "httpx",
        "Non-success response preserved for source-access diagnostics.",
        http_status=response.status_code,
        content_type=response.headers.get("content-type", "application/octet-stream"),
        relative_dir=relative_dir,
    )


def _parse_rss(path, feed_key: str) -> list[dict[str, object]]:
    root = ET.fromstring(path.read_bytes())
    rows: list[dict[str, object]] = []
    for item in root.findall(".//item"):
        title = (item.findtext("title") or "").strip()
        url = (item.findtext("link") or "").strip()
        published = item.findtext("pubDate")
        if not title or not url or not published:
            continue
        source_node = item.find("source")
        source_name = (source_node.text or "").strip() if source_node is not None else feed_key
        rows.append(
            {
                "published_at": pd.to_datetime(parsedate_to_datetime(published), utc=True),
                "event_date": None,
                "first_seen_at": lineage(path)["ingested_at"],
                "first_captured_at": lineage(path)["ingested_at"],
                "date_basis": "publisher_rss",
                "source_name": source_name,
                "title": title,
                "url": url,
                "language": "es" if feed_key.endswith("es") or "economista" in feed_key else "en",
                "query_term": "mexican_airlines",
                "gdelt_tone": None,
                "gdelt_theme": None,
                "source_system": "rss",
                **lineage(path),
            }
        )
    return rows


def _parse_gdelt(path) -> list[dict[str, object]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    rows: list[dict[str, object]] = []
    for item in payload.get("articles", []):
        seen = pd.to_datetime(item.get("seendate"), utc=True, errors="coerce")
        if pd.isna(seen) or not item.get("url") or not item.get("title"):
            continue
        rows.append(
            {
                "published_at": None,
                "event_date": None,
                "first_seen_at": seen,
                "first_captured_at": lineage(path)["ingested_at"],
                "date_basis": "gdelt_first_seen_only",
                "source_name": item.get("domain") or item.get("sourcecountry") or "GDELT",
                "title": item["title"],
                "url": item["url"],
                "language": item.get("language"),
                "query_term": "mexican_airlines",
                "gdelt_tone": pd.to_numeric(item.get("tone"), errors="coerce"),
                "gdelt_theme": item.get("themes"),
                "source_system": "gdelt",
                **lineage(path),
            }
        )
    return rows




def _archive_paths(source_system: str, entity: str):
    manifest = PATHS.bronze / "_manifest.jsonl"
    if not manifest.is_file():
        return []
    paths = set()
    for line in manifest.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        record = json.loads(line)
        if not str(record.get("logical_key", "")).startswith(f"{source_system}|{entity}|"):
            continue
        source_file = record.get("source_file")
        if not isinstance(source_file, str):
            continue
        path = (PATHS.bronze / source_file).resolve()
        if (
            path.is_relative_to(PATHS.bronze.resolve())
            and path.is_file()
            and record.get("http_status", 200) == 200
        ):
            paths.add(path)
    return sorted(paths)


def build_from_bronze() -> dict[str, object]:
    """Union all retained successful captures; preserve first capture per URL.

    GDELT seendate is observation time. An unknown publication date stays null
    and must not enter a publication-month archive without publisher review.
    """
    rows = []
    sources = []
    for feed_key in RSS_FEEDS:
        for path in _archive_paths("rss", feed_key):
            try:
                parsed = _parse_rss(path, feed_key)
            except (ET.ParseError, ValueError, OSError):
                continue
            if parsed:
                rows.extend(parsed)
                sources.append(feed_key)
    for path in _archive_paths("gdelt", "aeromexico_articles"):
        try:
            parsed = _parse_gdelt(path)
        except (json.JSONDecodeError, UnicodeDecodeError, ValueError, OSError):
            continue
        if parsed:
            rows.extend(parsed)
            sources.append("gdelt")
    if not rows:
        raise RuntimeError("No successful news bronze artifacts were found")
    frame = pd.DataFrame(rows)
    frame["url"] = frame.url.map(canonical_news_url)
    for column in ["published_at", "first_seen_at", "first_captured_at", "ingested_at"]:
        frame[column] = pd.to_datetime(frame[column], utc=True, errors="coerce")
    frame["gdelt_tone"] = pd.to_numeric(frame["gdelt_tone"], errors="coerce").astype("Float64")
    first_capture = frame.groupby("url").first_captured_at.min()
    first_seen = frame.groupby("url").first_seen_at.min()
    # Prefer actual publisher dates to an undated GDELT result; then latest
    # reviewed publisher metadata. Lineage of that selected row stays intact.
    frame = (
        frame.assign(_publication_known=frame.published_at.notna())
        .sort_values(
            ["_publication_known", "ingested_at", "published_at"],
            ascending=False,
            na_position="last",
            kind="stable",
        )
        .drop(columns="_publication_known")
    )
    frame = frame.drop_duplicates(["url"], keep="first").reset_index(drop=True)
    frame["first_captured_at"] = frame.url.map(first_capture)
    frame["first_seen_at"] = frame.url.map(first_seen)
    write_parquet_atomic(frame, PATHS.silver / "news_headlines.parquet")
    return {
        "rows": len(frame),
        "sources": sorted(set(sources)),
        "publication_unknown": int(frame.published_at.isna().sum()),
    }


def run() -> dict[str, object]:
    rows: list[dict[str, object]] = []
    failures: list[str] = []
    with SourceHttpClient("news", timeout_seconds=20, max_attempts=1) as client:
        for feed_key, url in RSS_FEEDS.items():
            try:
                path = fetch_bronze(
                    client,
                    url,
                    source_system="rss",
                    entity=feed_key,
                    period="current",
                    ext="xml",
                    relative_dir="news/rss",
                    notes="Headline collection only; no article-body scraping.",
                )
                rows.extend(_parse_rss(path, feed_key))
            except Exception as exc:
                failures.append(f"{feed_key}:{type(exc).__name__}")
                _preserve_http_failure(exc, feed_key, "news/rss/errors")

        gdelt_url = "https://api.gdeltproject.org/api/v2/doc/doc"
        try:
            gdelt_path = fetch_bronze(
                client,
                gdelt_url,
                source_system="gdelt",
                entity="aeromexico_articles",
                period="current",
                ext="json",
                relative_dir="news/gdelt",
                params={
                    "query": '(Aeromexico OR "Aeroméxico" OR "Viva Aerobus" OR Volaris)',
                    "mode": "artlist",
                    "maxrecords": "250",
                    "format": "json",
                    "sort": "datedesc",
                },
                notes="GDELT media-coverage results; tone is not customer satisfaction.",
            )
            rows.extend(_parse_gdelt(gdelt_path))
        except Exception as exc:
            failures.append(f"gdelt:{type(exc).__name__}")
            _preserve_http_failure(exc, "gdelt", "news/gdelt/errors")
    result = build_from_bronze()
    for failure in failures:
        log_issue_once(
            "silver",
            "news_headlines",
            "",
            "warning",
            "parse_failure",
            f"Optional news source unavailable during Stage 4 collection: {failure}.",
            0,
        )
    result["failures"] = failures
    return result


def main() -> int:
    import argparse

    argparse.ArgumentParser(description=__doc__).parse_args()
    print(run())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
