"""Explicitly isolated search over a review cut. Not imported by the chat runtime."""

from __future__ import annotations

from src.conversational_analytics.news_query import resolve_news_query, news_match


def review_search(archive: dict, question: str) -> dict:
    if archive.get("mode") != "candidate_preview" or not archive.get("candidate_sha256"):
        raise ValueError("Review search requires the explicit unapproved cut projection")
    intent = resolve_news_query(question)
    matches = []
    for row in archive["records"]:
        published = row["published_at"]
        if (
            intent["start_date"]
            and published < intent["start_date"]
            or intent["end_date"]
            and published > intent["end_date"]
        ):
            continue
        score = news_match(intent, row["title"], row["description"], row["companies"], row["topics"])
        if score:
            matches.append((score, row))
    matches.sort(key=lambda item: (item[0], item[1]["published_at"], item[1]["id"]), reverse=True)
    return {
        "corpus": "candidate_simulation",
        "index_sha256": archive["candidate_sha256"],
        "filters": intent,
        "total": len(matches),
        "matching_ids": [row[1]["id"] for row in matches[:50]],
        "items": [
            {
                "id": row["id"],
                "story_id": row["story_id"],
                "title": row["title"],
                "published_at": row["published_at"],
                "publisher": row["publisher"],
                "source_url": row["sources"][0]["url"],
                "source_sha256": row["sources"][0]["sha256"],
            }
            for _, row in matches[:5]
        ],
    }
