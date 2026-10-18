"""Metadata-only news parsing with deduplication and every contributing provenance."""

from __future__ import annotations

import json
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


def canonical_url(url: str) -> str:
    parsed = urlsplit(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("Invalid article metadata URL")
    query = [
        (key, value)
        for key, value in parse_qsl(parsed.query, keep_blank_values=True)
        if not key.lower().startswith("utm_") and key.lower() not in {"fbclid", "gclid"}
    ]
    return urlunsplit(
        (parsed.scheme.lower(), parsed.netloc.lower(), parsed.path or "/", urlencode(sorted(query)), "")
    )


def deduplicate(records: list[dict]) -> list[dict]:
    import pandas as pd

    grouped = {}
    for record in records:
        if record["source_system"] not in {"rss", "gdelt"}:
            raise ValueError("Only successful RSS/GDELT metadata is eligible")
        stamp = pd.Timestamp(record["published_at"])
        if stamp.tzinfo is None:
            raise ValueError("News publication requires a timezone")
        # Keep dated editions apart. No claim to unwrap opaque Google News links
        # or to identify two different URLs as the same article.
        key = (canonical_url(record["url"]), stamp.tz_convert("America/Mexico_City").date().isoformat())
        provenance = {
            field: str(record[field])
            for field in ("source_system", "source_file", "source_hash", "url", "published_at", "title")
        }
        if key not in grouped:
            grouped[key] = {**record, "canonical_url": key[0], "provenance": []}
        if provenance not in grouped[key]["provenance"]:
            grouped[key]["provenance"].append(provenance)
    output = []
    for row in grouped.values():
        provenance = row.pop("provenance")
        row["provenance_json"] = json.dumps(provenance, sort_keys=True, ensure_ascii=False)
        output.append(row)
    return output


def build_from_bronze() -> dict:
    """Read all successful selected captures, never query aggregators or articles."""
    import pandas as pd

    from src.config import PATHS
    from src.ingest.news.rss_gdelt import _parse_gdelt, _parse_rss
    from src.ingest.stage4_common import write_parquet_atomic

    rows, visited = [], set()
    manifest = PATHS.bronze / "_manifest.jsonl"
    for line in manifest.read_text().splitlines():
        artifact = json.loads(line)
        key = (artifact["source_system"], artifact["source_file"])
        if key in visited or artifact["source_system"] not in {"rss", "gdelt"}:
            continue
        visited.add(key)
        path = PATHS.bronze / artifact["source_file"]
        if artifact["source_system"] == "rss":
            feed_key = artifact["logical_key"].split("|")[1]
            rows.extend(_parse_rss(path, feed_key))
        else:
            rows.extend(_parse_gdelt(path))
    if not rows:
        raise ValueError("No valid news metadata; access failure is not an empty successful month")
    output = pd.DataFrame(deduplicate(rows)).sort_values("published_at", ascending=False)
    output["gdelt_tone"] = pd.to_numeric(output["gdelt_tone"], errors="coerce").astype("Float64")
    write_parquet_atomic(output, PATHS.silver / "news_headlines.parquet")
    return {
        "input_rows": len(rows),
        "deduplicated_rows": len(output),
        "article_requests": 0,
        "coverage": "selected_metadata_only_not_complete_month",
        "activation": "none",
    }
