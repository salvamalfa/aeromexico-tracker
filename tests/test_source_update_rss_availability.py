"""Physical RSS binding contracts, separate from real source acquisition evidence."""

import json
import shutil
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from email.utils import format_datetime
from urllib.parse import parse_qs, urlsplit
from uuid import uuid4
from xml.etree import ElementTree as ET

import httpx
import pytest

from src.ingest.news.rss_gdelt import RSS_FEEDS
from src.source_updates import availability, readiness, rss_candidate, rss_retention
from src.source_updates.catalog import ROOT
from src.source_updates.collection import collect
from src.source_updates.recipes import catalog_selection


def xml(url):
    args = parse_qs(urlsplit(url).query)
    spanish = args["hl"] == ["es-419"]
    tree = ET.Element("rss", version="2.0")
    channel = ET.SubElement(tree, "channel")
    values = dict(
        title='"' + args["q"][0] + '" - Google ' + ("Noticias" if spanish else "News"),
        link=url.replace("/rss/search", "/search"),
        language="es-419" if spanish else "en-US",
        generator="NFE/5.0",
        lastBuildDate=format_datetime(datetime.now(UTC) - timedelta(minutes=1)),
    )
    for key, value in values.items():
        ET.SubElement(channel, key).text = value
    row = ET.SubElement(channel, "item")
    for key, value in dict(
        title="Declared headline",
        link="https://news.google.com/rss/articles/example",
        guid="rss-fixture",
        pubDate="Fri, 18 Sep 2026 18:00:00 GMT",
    ).items():
        ET.SubElement(row, key).text = value
    ET.SubElement(row, "source", url="https://example.com").text = "Declared publisher"
    return ET.tostring(tree, encoding="utf-8")


@pytest.fixture
def physical():
    root = ROOT / "tmp/source-updates" / ("rss-availability-test-" + uuid4().hex)
    collection = root / "collection"
    child = root / "candidate"

    class Client:
        def __init__(self, *args, **kw):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def request(self, method, url, **kw):
            return httpx.Response(200, content=xml(url), request=httpx.Request(method, url))

    selection = catalog_selection("rss")
    assert len(selection["items"]) == 2
    capture = collect(selection, collection, execute=True, client_factory=Client)
    source = collection / "data/bronze"
    kept = rss_retention.retain(child, source, [r["source_file"] for r in capture["items"]], execute=True)
    cutoff = (datetime.now(UTC) + timedelta(seconds=1)).isoformat()
    result = rss_candidate.run(child, "2026M09", cutoff, kept["run_id"], execute=True)
    item = dict(
        id="rss",
        product="rss",
        adapter="rss_retained",
        period="2026M09",
        workspace=str(child),
        receipt_id=kept["run_id"],
        required=True,
        candidate_as_of=cutoff,
        availability=dict(
            workspace=str(collection),
            run_id=capture["run_id"],
            feed_items={r["entity"]: r["id"] for r in selection["items"]},
        ),
    )
    yield dict(
        root=root,
        collection=collection,
        child=child,
        item=item,
        result=result,
        cutoff=cutoff,
        capture=capture,
    )
    shutil.rmtree(root)


def test_two_current_queries_bind_full_candidate_but_not_complete_news_month(physical):
    s = physical
    recipe = dict(version=1, as_of=s["cutoff"], required_items=["rss"], items=[s["item"]])
    target = s["root"] / "readiness"
    accepted = readiness.execute(recipe, target, write=True)
    checked = readiness.execute(recipe, target, check=True)
    row = checked["results"][0]
    assert accepted["ready_for_review"] and row["latest_source_availability_verified"]
    assert not checked["ready_for_calendar_incorporation"]
    proof = row["source_availability_evidence"]
    assert proof["latest_available_period"] is None and proof["first_publication_date"] is None
    assert not proof["complete_month_certified"] and not proof["publisher_coverage_verified"]
    assert not proof["agent_eligible"] and row["scope"].endswith("not_publisher_body_verification")
    assert {r["query_url"] for r in proof["feeds"]} == {RSS_FEEDS[k] for k in ("google_es", "google_en")}
    assert s["result"]["missing_days_mean"] == "not_observed_never_no_news"


def test_binding_rejects_missing_locale_swapped_items_overlap_and_changed_scope(physical):
    s = physical
    variants = []
    for roles in (
        {"google_es": "rss-google_es"},
        {"google_es": "rss-google_es", "google_en": "rss-google_es"},
        {"google_es": "rss-google_en", "google_en": "rss-google_es"},
        {"google_es": [], "google_en": "rss-google_en"},
    ):
        x = deepcopy(s["item"])
        x["availability"]["feed_items"] = roles
        variants.append(x)
    x = deepcopy(s["item"])
    x["workspace"] = str(s["collection"])
    variants.append(x)
    for item in variants:
        with pytest.raises(ValueError):
            availability.verify(item, s["result"], s["cutoff"])
    for change in (
        {"complete_month_certified": True},
        {"publisher_coverage_verified": True},
        {"article_requests": 1},
        {"query_scope": [RSS_FEEDS["google_es"]]},
    ):
        with pytest.raises(ValueError):
            availability.verify(s["item"], {**s["result"], **change}, s["cutoff"])
    with pytest.raises(ValueError, match="explicit round date"):
        availability.verify(
            s["item"], s["result"], (datetime.fromisoformat(s["cutoff"]) + timedelta(days=1)).isoformat()
        )


def test_duplicate_manifest_changed_response_or_bytes_cannot_certify_availability(physical):
    s = physical
    source = s["collection"] / "data/bronze"
    manifest = source / "_manifest.jsonl"
    original = manifest.read_bytes()
    manifest.write_bytes(original + original.splitlines()[0] + b"\n")
    with pytest.raises(ValueError, match="unique query captures"):
        availability.verify(s["item"], s["result"], s["cutoff"])
    manifest.write_bytes(original)
    receipt = s["collection"] / "receipts" / f"collection-{s['capture']['run_id']}.json"
    original = receipt.read_bytes()
    changed = json.loads(original)
    changed["items"][0]["response_url"] = RSS_FEEDS["google_en"]
    receipt.write_text(json.dumps(changed))
    with pytest.raises(ValueError):
        availability.verify(s["item"], s["result"], s["cutoff"])
    receipt.write_bytes(original)
    path = source / s["capture"]["items"][0]["source_file"]
    path.write_bytes(path.read_bytes() + b"changed")
    with pytest.raises(ValueError):
        availability.verify(s["item"], s["result"], s["cutoff"])


def test_recipe_preserves_non_executable_product_states(monkeypatch):
    from src.source_updates import recipes

    original = recipes.describe("rss")
    for state in ("manual", "internal", "disabled"):
        monkeypatch.setattr(recipes, "describe", lambda product: {**original, "state": state})
        with pytest.raises(ValueError, match="explicit acquisition procedure"):
            recipes.catalog_selection("rss")
