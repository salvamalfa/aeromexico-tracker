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
            field: None if pd.api.types.is_scalar(value) and pd.isna(value) else value
            for field, value in record.items()
            if field not in {"canonical_url", "provenance_json"}
        }
        if key not in grouped:
            grouped[key] = {**record, "canonical_url": key[0], "provenance": []}
        if provenance not in grouped[key]["provenance"]:
            grouped[key]["provenance"].append(provenance)
    output = []
    for row in grouped.values():
        provenance = row.pop("provenance")
        row["provenance_json"] = json.dumps(provenance, sort_keys=True, ensure_ascii=False, default=str)
        output.append(row)
    return output


def checkable_contributors(frame):
    """Project each contributor for source-specific checks without duplicating stored news."""
    import pandas as pd

    if "provenance_json" not in frame:
        return frame  # Legacy direct rows only certify their own top-level source.
    projected = []
    required = {"source_system", "source_file", "source_hash", "url", "published_at", "title"}
    for row in frame.to_dict("records"):
        provenance = json.loads(row["provenance_json"])
        if not isinstance(provenance, list) or not provenance:
            raise ValueError("News contributors require nonempty provenance")
        lineage_fields = ("source_system", "source_file", "source_hash")
        if not any(
            isinstance(part, dict) and all(part.get(field) == row[field] for field in lineage_fields)
            for part in provenance
        ):
            raise ValueError("Top-level news lineage is absent from its contributors")
        canonical = canonical_url(row["url"])
        stamp = pd.Timestamp(row["published_at"])
        if stamp.tzinfo is None:
            raise ValueError("News publication requires a timezone")
        day = stamp.tz_convert("America/Mexico_City").date()
        for contributor in provenance:
            if not isinstance(contributor, dict) or not required <= contributor.keys():
                raise ValueError("News contributor lacks direct lineage or metadata")
            observed = pd.Timestamp(contributor["published_at"])
            if (
                contributor["source_system"] not in {"rss", "gdelt"}
                or canonical_url(contributor["url"]) != canonical
                or observed.tzinfo is None
                or observed.tz_convert("America/Mexico_City").date() != day
            ):
                raise ValueError("News contributor does not match the deduplicated dated URL")
            # Unknown contributor fields stay absent, rather than inheriting
            # another source's title, language or GDELT tone.
            projected.append(
                {
                    **dict.fromkeys(frame.columns),
                    **contributor,
                    "published_at": observed,
                    "canonical_url": canonical,
                    "provenance_json": row["provenance_json"],
                }
            )
    return pd.DataFrame(projected)


def build_from_bronze() -> dict:
    """Read all successful selected captures, never query aggregators or articles."""
    import pandas as pd

    from src.config import PATHS
    from src.ingest.news.rss_gdelt import _parse_gdelt, _parse_rss
    from src.ingest.stage4_common import write_parquet_atomic

    rows, visited, rejected = [], set(), []
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
            # Historical HTTP-200 aggregator errors are retained in Bronze.
            # They are access evidence, never successful empty news captures.
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
                if not isinstance(payload, dict) or not isinstance(payload.get("articles"), list):
                    raise ValueError("Expected a GDELT articles array")
            except ValueError as exc:
                rejected.append({"source_file": artifact["source_file"], "reason": str(exc)})
                continue
            rows.extend(_parse_gdelt(path))
    if not rows:
        raise ValueError("No valid news metadata; access failure is not an empty successful month")
    output = pd.DataFrame(deduplicate(rows)).sort_values("published_at", ascending=False)
    # Silver's existing grain is URL/query. Dated editions stay separate during
    # provenance grouping; select the latest edition without borrowing an older
    # edition's date or lineage. Originals and the discarded edition identities
    # remain inspectable, including for the separate monthly archive adapter.
    superseded = output.loc[output.duplicated(["url", "query_term"], keep="first")]
    output = output.drop_duplicates(["url", "query_term"], keep="first")
    output["gdelt_tone"] = pd.to_numeric(output["gdelt_tone"], errors="coerce").astype("Float64")
    write_parquet_atomic(output, PATHS.silver / "news_headlines.parquet")
    edition_selection = superseded[["url", "published_at", "source_file", "source_hash"]].to_dict("records")
    PATHS.quality.mkdir(parents=True, exist_ok=True)
    (PATHS.quality / "news_metadata_selection.json").write_text(
        json.dumps(
            {"superseded_editions": edition_selection, "invalid_artifacts": rejected}, default=str, indent=2
        )
        + "\n"
    )
    return {
        "input_rows": len(rows),
        "deduplicated_rows": len(output),
        "article_requests": 0,
        "coverage": "selected_metadata_only_not_complete_month",
        "activation": "none",
        "invalid_artifacts_preserved": rejected,
        "source_completeness": "partial_invalid_captures" if rejected else "not_certified",
        "superseded_editions_preserved_in_bronze": len(superseded),
    }
