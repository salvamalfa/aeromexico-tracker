"""Preserve RSS declarations and every contribution; never infer publisher verification."""

from __future__ import annotations

import calendar
import hashlib
import json
import re
from datetime import date
from email.utils import parsedate_to_datetime
from urllib.parse import parse_qs, urlsplit

from lxml import etree

from src.source_updates.calendar import local_time
from src.source_updates.checks import period_end
from src.source_updates.news import canonical_url
from src.source_updates.collection import validate_url
from src.source_updates.rss_retention import MAX_BYTES, identity

VERSION = "rss_declared_metadata_v1"
NATIVE = "rss_native_metadata"
FACT = "fact_rss_declared_metadata"


def stable_id(*parts):
    return hashlib.sha256(json.dumps(parts, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def window(period, cutoff):
    if not isinstance(period, str) or not re.fullmatch(r"20\d{2}M(?:0[1-9]|1[0-2])", period):
        raise ValueError("RSS requires an explicit publication-declaration month")
    end = period_end(period)
    if end >= local_time(cutoff).date():
        raise ValueError("RSS review month must be closed before the zoned cutoff")
    return end


def field(item, name, *, required=False):
    nodes = item.findall(name)
    if len(nodes) > 1 or nodes and len(nodes[0]):
        raise ValueError(f"RSS {name} must be one scalar declaration")
    value = (nodes[0].text or "").strip() if nodes else None
    if required and not value:
        raise ValueError(f"RSS item lacks {name}")
    return value or None


def parse(inputs, period, cutoff):
    end = window(period, cutoff)
    native, artifacts, captures = [], [], []
    for content, source in inputs:
        feed = identity(source)
        if len(content) > MAX_BYTES:
            raise ValueError("RSS XML exceeds reviewed byte bound")
        try:
            tree = etree.fromstring(
                content, etree.XMLParser(resolve_entities=False, no_network=True, recover=False)
            )
        except etree.XMLSyntaxError as exc:
            raise ValueError("RSS XML is malformed") from exc
        if tree.getroottree().docinfo.doctype or tree.tag != "rss" or tree.get("version") != "2.0":
            raise ValueError("Require RSS2.0 without DOCTYPE/entities")
        channels = tree.findall("channel")
        if len(channels) != 1:
            raise ValueError("Expected exactly one RSS channel")
        channel = channels[0]
        link = field(channel, "link", required=True)
        validate_url(link, ["news.google.com"])
        title = " ".join(field(channel, "title", required=True).split())
        language = "es-419" if feed["feed_id"] == "google_es" else "en-US"
        suffix = "Noticias" if language == "es-419" else "News"
        if (
            title != f'"{feed["query_term"]}" - Google {suffix}'
            or urlsplit(link).path != "/search"
            or parse_qs(urlsplit(link).query) != parse_qs(urlsplit(feed["query_url"]).query)
            or field(channel, "language", required=True) != language
            or field(channel, "generator", required=True) != "NFE/5.0"
        ):
            raise ValueError("RSS channel identity/query/locale differs from its physical capture")
        try:
            built = parsedate_to_datetime(field(channel, "lastBuildDate", required=True))
        except (ValueError, TypeError, OverflowError) as exc:
            raise ValueError("RSS channel build declaration is malformed") from exc
        if built is None or built.tzinfo is None or built > local_time(source["downloaded_at"]):
            raise ValueError("RSS channel build needs timezone and must precede capture")
        items = channels[0].findall("item")
        if len(items) > 250 or len(tree.findall(".//item")) != len(items):
            raise ValueError("RSS items exceed bound or escape channel scope")
        captured = local_time(source["downloaded_at"])
        if captured > local_time(cutoff):
            raise ValueError("RSS capture is after cutoff")
        artifact_id = stable_id(
            "rss_artifact", source["source_file"], source["sha256"], source["downloaded_at"]
        )
        artifacts.append(
            dict(
                artifact_id=artifact_id,
                source_file=source["source_file"],
                source_hash=source["sha256"],
                source_system="rss",
                captured_at=source["downloaded_at"],
                **feed,
            )
        )
        count = 0
        for index, item in enumerate(items, 1):
            title, url, raw_date = (field(item, key, required=True) for key in ("title", "link", "pubDate"))
            try:
                stamp = parsedate_to_datetime(raw_date)
            except (ValueError, TypeError, OverflowError) as exc:
                raise ValueError("RSS publication declaration is malformed") from exc
            if stamp is None or stamp.tzinfo is None or stamp > captured:
                raise ValueError("RSS publication declaration needs timezone and must precede capture")
            local_day = local_time(stamp.isoformat()).date()
            selected = (local_day.year, local_day.month) == (end.year, end.month)
            publisher = field(item, "source")
            node = item.find("source")
            publisher_url = node.get("url") if node is not None else None
            if publisher_url is not None:
                canonical_url(publisher_url)
            native.append(
                dict(
                    record_id=stable_id(NATIVE, source["source_file"], source["sha256"], index),
                    source_artifact_id=artifact_id,
                    source_file=source["source_file"],
                    source_hash=source["sha256"],
                    source_system="rss",
                    source_locator=f"/rss/channel/item[{index}]",
                    item_1based=index,
                    captured_at=source["downloaded_at"],
                    parser_version=VERSION,
                    **feed,
                    title=title,
                    url_as_reported=url,
                    canonical_url=canonical_url(url),
                    guid=field(item, "guid"),
                    publisher_name_as_declared=publisher,
                    publisher_url_as_declared=publisher_url,
                    pubdate_as_reported=raw_date,
                    published_at_as_declared=stamp.isoformat(),
                    local_publication_date=local_day.isoformat(),
                    selected_month=selected,
                    event_date=None,
                    first_available_at=None,
                    publisher_document_verified=False,
                    agent_eligible=False,
                )
            )
            count += selected
        captures.append(
            dict(
                source_file=source["source_file"],
                raw_items=len(items),
                selected_items=count,
                channel_title_as_declared=field(channel, "title", required=True),
                channel_link_as_declared=link,
                channel_language_as_declared=language,
                channel_built_at_as_declared=built.isoformat(),
            )
        )
    grouped = {}
    for row in native:
        if row["selected_month"]:
            grouped.setdefault((row["canonical_url"], row["local_publication_date"]), []).append(row)
    if not grouped:
        raise ValueError("No dated RSS observations in requested month; no claim of absence")
    facts = [
        dict(
            record_id=stable_id(FACT, period, *key),
            canonical_url=key[0],
            local_publication_date=key[1],
            contributors=sorted(rows, key=lambda r: r["record_id"]),
            event_date=None,
            first_available_at=None,
            publisher_document_verified=False,
            agent_eligible=False,
        )
        for key, rows in sorted(grouped.items())
    ]
    links = [
        dict(
            record_id=row["record_id"],
            table_name=NATIVE,
            link_type="source_artifact",
            target_id=row["source_artifact_id"],
        )
        for row in native
    ]
    for fact in facts:
        for row in fact["contributors"]:
            links.append(
                dict(
                    record_id=fact["record_id"],
                    table_name=FACT,
                    link_type="native_parent",
                    target_id=row["record_id"],
                )
            )
        for artifact_id in sorted({r["source_artifact_id"] for r in fact["contributors"]}):
            links.append(
                dict(
                    record_id=fact["record_id"],
                    table_name=FACT,
                    link_type="source_artifact",
                    target_id=artifact_id,
                )
            )
    observed = sorted({r["local_publication_date"] for r in facts})
    return dict(native=native, gold=facts, artifacts=artifacts, lineage=links), dict(
        captures=captures,
        query_scope=sorted({r["query_url"] for r in artifacts}),
        selected_contributions=sum(r["selected_items"] for r in captures),
        outside_month_native_rows=len(native) - sum(r["selected_items"] for r in captures),
        observed_publication_days=observed,
        unobserved_days=[
            date(end.year, end.month, day).isoformat()
            for day in range(1, calendar.monthrange(end.year, end.month)[1] + 1)
            if date(end.year, end.month, day).isoformat() not in observed
        ],
        missing_days_mean="not_observed_never_no_news",
        opaque_urls_resolved=False,
        article_requests=0,
        complete_month_certified=False,
        publisher_coverage_verified=False,
    )
