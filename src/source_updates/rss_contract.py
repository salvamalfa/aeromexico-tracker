"""Strict RSS candidate envelopes and complete native-to-artifact lineage checks."""

from __future__ import annotations

import json
from email.utils import parsedate_to_datetime
from urllib.parse import parse_qs, urlsplit

from jsonschema import Draft202012Validator, FormatChecker
from jsonschema.exceptions import ValidationError

from src.source_updates.calendar import local_time
from src.source_updates.catalog import ROOT
from src.source_updates.news import canonical_url
from src.source_updates.collection import validate_url
from src.source_updates.rss_native import FACT, NATIVE, VERSION, stable_id

SCHEMA = ROOT / "contracts/source_updates/rss-declared-metadata.schema.json"


def validate(payload):
    try:
        Draft202012Validator(json.loads(SCHEMA.read_text()), format_checker=FormatChecker()).validate(payload)
    except ValidationError as exc:
        raise ValueError("RSS metadata contract failed: " + exc.message) from exc


def envelopes(tables, period, query_scope):
    return {
        kind: dict(
            version=VERSION,
            kind=kind,
            period=period,
            timezone="America/Mexico_City",
            date_basis="rss_declared_publication_not_publisher_body_verification",
            coverage="partial_metadata_in_explicit_retained_queries",
            query_scope=query_scope,
            agent_eligible=False,
            activation="none",
            publication="not_authorized",
            rows=rows,
        )
        for kind, rows in tables.items()
    }


def unique(rows, field):
    indexed = {r[field]: r for r in rows}
    if len(indexed) != len(rows):
        raise ValueError("RSS duplicate observation or artifact identity")
    return indexed


def validate_row(row, period):
    stamp = parsedate_to_datetime(row["pubdate_as_reported"])
    validate_url(row["query_url"], ["news.google.com"])
    query = parse_qs(urlsplit(row["query_url"]).query, keep_blank_values=True)
    locale = {
        "google_es": {"hl": ["es-419"], "gl": ["MX"], "ceid": ["MX:es-419"]},
        "google_en": {"hl": ["en-US"], "gl": ["US"], "ceid": ["US:en"]},
    }[row["feed_id"]]
    if (
        urlsplit(row["query_url"]).path != "/rss/search"
        or set(query) != {"q", "hl", "gl", "ceid"}
        or any(query.get(k) != v for k, v in locale.items())
    ):
        raise ValueError("RSS contributor query identity differs from its feed locale")
    if row["publisher_url_as_declared"] is not None:
        canonical_url(row["publisher_url_as_declared"])
    if (
        stamp is None
        or stamp.tzinfo is None
        or stamp.isoformat() != row["published_at_as_declared"]
        or local_time(stamp.isoformat()) > local_time(row["captured_at"])
        or local_time(stamp.isoformat()).date().isoformat() != row["local_publication_date"]
        or canonical_url(row["url_as_reported"]) != row["canonical_url"]
        or row["source_locator"] != f"/rss/channel/item[{row['item_1based']}]"
        or row["record_id"] != stable_id(NATIVE, row["source_file"], row["source_hash"], row["item_1based"])
        or row["source_artifact_id"]
        != stable_id("rss_artifact", row["source_file"], row["source_hash"], row["captured_at"])
        or row["selected_month"] != (f"{local_time(stamp.isoformat()):%YM%m}" == period)
        or parse_qs(urlsplit(row["query_url"]).query).get("q") != [row["query_term"]]
    ):
        raise ValueError("RSS date/URL/locator/identity/month/query mismatch")


def validate_gold(payload):
    validate(payload)
    if payload["kind"] != "gold":
        raise ValueError("RSS revision baseline must be a Gold metadata envelope")
    unique(payload["rows"], "record_id")
    parents = []
    for fact in payload["rows"]:
        key = (fact["canonical_url"], fact["local_publication_date"])
        if fact["record_id"] != stable_id(FACT, payload["period"], *key):
            raise ValueError("RSS Gold natural grain identity changed")
        for row in fact["contributors"]:
            validate_row(row, payload["period"])
            if (
                not row["selected_month"]
                or (row["canonical_url"], row["local_publication_date"]) != key
                or row["query_url"] not in payload["query_scope"]
            ):
                raise ValueError("RSS Gold contributor escaped its month, dated URL or query scope")
            parents.append(row)
    unique(parents, "record_id")


def validate_bundle(outputs):
    if set(outputs) != {"native", "gold", "artifacts", "lineage"}:
        raise ValueError("RSS complete four-output inventory required")
    for payload in outputs.values():
        validate(payload)
    validate_gold(outputs["gold"])
    periods = {p["period"] for p in outputs.values()}
    scopes = {json.dumps(p["query_scope"]) for p in outputs.values()}
    if len(periods) != 1 or len(scopes) != 1:
        raise ValueError("RSS output periods/query scopes disagree")
    period = periods.pop()
    native = unique(outputs["native"]["rows"], "record_id")
    facts = unique(outputs["gold"]["rows"], "record_id")
    artifacts = unique(outputs["artifacts"]["rows"], "artifact_id")
    if sorted({r["query_url"] for r in artifacts.values()}) != outputs["gold"]["query_scope"]:
        raise ValueError("RSS query scope is not the selected physical artifacts")
    expected_links, grouped = [], {}
    for artifact in artifacts.values():
        if artifact["artifact_id"] != stable_id(
            "rss_artifact", artifact["source_file"], artifact["source_hash"], artifact["captured_at"]
        ):
            raise ValueError("RSS artifact ID changed")
    for row in native.values():
        artifact = artifacts[row["source_artifact_id"]]
        if any(
            row[k] != artifact[k]
            for k in ("source_file", "source_hash", "captured_at", "feed_id", "query_term", "query_url")
        ):
            raise ValueError("RSS native record borrowed another capture's provenance")
        validate_row(row, period)
        expected_links.append(
            dict(
                record_id=row["record_id"],
                table_name=NATIVE,
                link_type="source_artifact",
                target_id=row["source_artifact_id"],
            )
        )
        if row["selected_month"]:
            grouped.setdefault((row["canonical_url"], row["local_publication_date"]), []).append(row)
    if len(grouped) != len(facts):
        raise ValueError("RSS Gold omitted a dated URL group")
    for fact in facts.values():
        key = (fact["canonical_url"], fact["local_publication_date"])
        if (
            fact["record_id"] != stable_id(FACT, period, *key)
            or key not in grouped
            or fact["contributors"] != sorted(grouped[key], key=lambda r: r["record_id"])
        ):
            raise ValueError("RSS Gold contributors differ from complete direct native parents")
        for row in fact["contributors"]:
            expected_links.append(
                dict(
                    record_id=fact["record_id"],
                    table_name=FACT,
                    link_type="native_parent",
                    target_id=row["record_id"],
                )
            )
        for target in sorted({r["source_artifact_id"] for r in fact["contributors"]}):
            expected_links.append(
                dict(
                    record_id=fact["record_id"],
                    table_name=FACT,
                    link_type="source_artifact",
                    target_id=target,
                )
            )
    key = lambda r: json.dumps(r, sort_keys=True)
    if sorted(outputs["lineage"]["rows"], key=key) != sorted(expected_links, key=key):
        raise ValueError("RSS complete exact lineage bridge differs")
    return dict(
        native_rows=len(native), gold_rows=len(facts), artifacts=len(artifacts), links=len(expected_links)
    )
