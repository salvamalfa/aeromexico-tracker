"""Physical current RSS query snapshots; no complete-month or publisher-body claim."""

import json
from pathlib import Path

from src.ingest.news.rss_gdelt import RSS_FEEDS
from src.source_updates import availability as physical
from src.source_updates.catalog import bronze_aliases, load_catalog, product_map
from src.source_updates.rss_retention import identity


def verify(item, result, cutoff):
    binding = item["availability"]
    root = physical.preflight(binding, item["workspace"])
    if set(binding) != physical.RSS_FIELDS:
        raise ValueError("RSS requires its two canonical physical feed item roles")
    before = physical.collection_inventory(root)
    receipt_path = root / "receipts" / f"collection-{binding['run_id']}.json"
    receipt_hash = physical.sha(receipt_path)
    receipt = json.loads(receipt_path.read_text())
    expected = dict(
        run_id=binding["run_id"],
        mode="collection",
        status="collected_unvalidated",
        activation="none",
        publication="not_authorized",
    )
    if any(receipt.get(k) != v for k, v in expected.items()) or len(receipt.get("items", [])) != 2:
        raise ValueError("RSS requires one immutable two-feed successful acquisition receipt")
    manifest = [json.loads(line) for line in (root / "data/bronze/_manifest.jsonl").read_text().splitlines()]
    if (
        len(manifest) != 2
        or len({r["source_file"] for r in manifest}) != 2
        or ({r["source_file"] for r in manifest} != {r.get("source_file") for r in receipt["items"]})
    ):
        raise ValueError("RSS physical manifest must identify exactly its two unique query captures")
    source = load_catalog()[product_map()["rss"]["source_key"]]
    aliases = bronze_aliases("rss")
    captured = []
    for feed, identifier in binding["feed_items"].items():
        rows = [r for r in receipt["items"] if r.get("id") == identifier]
        if len(rows) != 1:
            raise ValueError("RSS physical feed collection item absent or duplicated")
        row = rows[0]
        if (
            row.get("product") != "rss"
            or row.get("status") != "collected_unvalidated"
            or row.get("requested_period") != "current"
            or any(row.get(k) != RSS_FEEDS[feed] for k in ("source_url", "response_url"))
        ):
            raise ValueError("RSS physical query must match its canonical feed and locale exactly")
        path, record = physical.artifact(root, row, cutoff, source["allowed_hosts"], receipt, aliases)
        if identity(record)["feed_id"] != feed:
            raise ValueError("RSS logical capture identity differs from the selected locale feed")
        captured.append(
            dict(
                feed_id=feed,
                source_file=row["source_file"],
                source_hash=row["sha256"],
                source_system="rss",
                captured_at=record["downloaded_at"],
                query_url=record["source_url"],
                query_term=identity(record)["query_term"],
            )
        )
    artifact_path = Path(item["workspace"]) / "data/gold/rss_source_artifacts.json"
    bundle = json.loads(artifact_path.read_text())
    fields = set(captured[0])
    actual = [{k: row.get(k) for k in fields} for row in bundle["rows"]]
    if (
        bundle.get("period") != item["period"]
        or sorted(actual, key=lambda r: r["feed_id"]) != sorted(captured, key=lambda r: r["feed_id"])
        or set(result.get("query_scope", [])) != {RSS_FEEDS[k] for k in binding["feed_items"]}
        or result.get("complete_month_certified") is not False
        or result.get("publisher_coverage_verified") is not False
        or result.get("article_requests") != 0
        or result.get("first_publication_date") is not None
        or result.get("scope")
        != "retained_RSS_declared_metadata_partial_queries_not_publisher_body_verification"
    ):
        raise ValueError("RSS verified native artifacts or limits do not bind both physical query snapshots")
    if physical.sha(receipt_path) != receipt_hash or physical.collection_inventory(root) != before:
        raise ValueError("RSS physical query snapshot changed during verification")
    return dict(
        collection_receipt_sha256=receipt_hash,
        physical_collection_files=before,
        feeds=captured,
        discovery_contract_product="rss",
        availability_basis="both_canonical_current_query_responses_not_a_complete_month_or_feed_archive",
        review_period=item["period"],
        latest_available_period=None,
        first_publication_date=None,
        round_as_of=cutoff,
        complete_month_certified=False,
        publisher_coverage_verified=False,
        agent_eligible=False,
    )
