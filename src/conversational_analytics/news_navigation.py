"""Server-owned news navigation derived only from the executed evidence tool."""

from __future__ import annotations

import re
from urllib.parse import urlsplit

from .evidence_index import ALLOWED_HOSTS


def news_navigation(result):
    if result.get("corpus") != "approved_only" or not re.fullmatch(
        r"[a-f0-9]{64}", str(result.get("index_sha256", ""))
    ):
        return None
    rows = result.get("results")
    if not isinstance(rows, list) or len(rows) > 5 or result.get("count") != len(rows):
        return None
    items = []
    for row in rows:
        if not isinstance(row, dict) or any(
            not isinstance(row.get(key), str) for key in ("id", "title", "published_at", "publisher")
        ):
            return None
        citation = row.get("citation", {})
        if not isinstance(citation, dict) or not isinstance(citation.get("url"), str):
            return None
        url = urlsplit(citation.get("url", ""))
        if (
            not re.fullmatch(r"[A-Za-z0-9_.-]{1,120}", str(row.get("id", "")))
            or url.scheme != "https"
            or url.hostname not in ALLOWED_HOSTS
            or url.username
            or url.password
            or not re.fullmatch(r"[a-f0-9]{64}", str(citation.get("source_sha256", "")))
        ):
            return None
        items.append(
            {
                "id": row["id"],
                "story_id": row.get("story_id", row["id"]),
                "title": row["title"],
                "published_at": row["published_at"],
                "publisher": row["publisher"],
                "source_url": citation["url"],
                "source_sha256": citation["source_sha256"],
            }
        )
    matching_ids = result.get("matching_ids", [item["id"] for item in items])
    if (
        not isinstance(matching_ids, list)
        or len(matching_ids) > 50
        or any(not isinstance(value, str) for value in matching_ids)
        or len(set(matching_ids)) != len(matching_ids)
        or any(
            not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_.-]{1,120}", value)
            for value in matching_ids
        )
    ):
        return None
    return {
        "corpus": "approved_only",
        "index_sha256": result["index_sha256"],
        "filters": result.get("filters", {}),
        "total": result.get("total", len(items)),
        "items": items,
        "matching_ids": matching_ids,
    }
