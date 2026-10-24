"""RSS contracts use synthetic feeds; actual retention evidence is tested separately."""

from __future__ import annotations

import hashlib
import json
import shutil
from datetime import datetime
from email.utils import format_datetime
from pathlib import Path
from urllib.parse import urlencode
from uuid import uuid4

import pytest
from lxml import etree

from src.source_updates import global_readiness, readiness
from src.source_updates.catalog import ROOT
from src.source_updates.rss_candidate import OUTPUTS, batch, run
from src.source_updates.rss_contract import validate_bundle
from src.source_updates.rss_native import parse
from src.source_updates.rss_retention import retain

CUTOFF = "2026-10-23T16:00:00-06:00"
PERIOD = "2026M09"


def item(title="Synthetic title", url="https://example.test/one", published="2026-09-01T06:30:00+00:00"):
    return dict(
        title=title,
        link=url,
        pubDate=format_datetime(datetime.fromisoformat(published)),
        source="Synthetic publisher",
        guid="synthetic-guid",
    )


def xml(items, feed="google_es", query="Aeromexico airline"):
    params = dict(
        q=query,
        hl="es-419" if feed == "google_es" else "en-US",
        gl="MX" if feed == "google_es" else "US",
        ceid="MX:es-419" if feed == "google_es" else "US:en",
    )
    tree = etree.Element("rss", version="2.0")
    channel = etree.SubElement(tree, "channel")
    for key, value in dict(
        title=f'"{query}" - Google ' + ("Noticias" if feed == "google_es" else "News"),
        link="https://news.google.com/search?" + urlencode(params),
        language=params["hl"],
        generator="NFE/5.0",
        lastBuildDate="Fri, 02 Oct 2026 12:00:00 GMT",
    ).items():
        etree.SubElement(channel, key).text = value
    for values in items:
        node = etree.SubElement(channel, "item")
        for key, value in values.items():
            child = etree.SubElement(node, key)
            child.text = value
            if key == "source":
                child.set("url", "https://example.test")
    return etree.tostring(tree, xml_declaration=True, encoding="UTF-8"), params


def source(
    root, items=None, *, feed="google_es", index=1, content=None, status=200, query="Aeromexico airline"
):
    raw, params = xml(items if items is not None else [item()], feed, query)
    if content is not None:
        raw = content
    relative = f"news/rss/rss_{feed}_current_20261002T1200{index:02d}Z.xml"
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)
    row = dict(
        source_file=relative,
        source_system="rss",
        source_url="https://news.google.com/rss/search?" + urlencode(params),
        logical_key=f"rss|{feed}|current|xml",
        downloaded_at=f"2026-10-02T12:00:{index:02d}+00:00",
        sha256=hashlib.sha256(raw).hexdigest(),
        bytes=len(raw),
        http_status=status,
    )
    Path(str(path) + ".meta.json").write_text(json.dumps(row))
    with (root / "_manifest.jsonl").open("a") as stream:
        stream.write(json.dumps(row) + "\n")
    return row


@pytest.fixture
def roots():
    root = ROOT / "tmp/source-updates" / ("rss-synthetic-" + uuid4().hex)
    original = root / "original"
    original.mkdir(parents=True)
    try:
        yield root, original
    finally:
        shutil.rmtree(root, ignore_errors=True)


def prepared(roots, items=None, **kwargs):
    root, original = roots
    row = source(original, items, **kwargs)
    candidate = root / "candidate"
    saved = retain(candidate, original, [row["source_file"]], execute=True)
    return candidate, saved["run_id"], row


def payloads(candidate):
    return {kind: json.loads((candidate / "data" / path).read_text()) for kind, path in OUTPUTS.items()}


def test_full_domain_dedup_preserves_all_variants_and_mexico_day(roots):
    root, original = roots
    values = [
        item("outside", published="2026-09-01T05:30:00+00:00"),
        item("first", url="https://example.test/one?utm_source=x"),
        item("variant", published="2026-09-01T08:30:00+00:00"),
        item("next day", published="2026-09-02T08:30:00+00:00"),
    ]
    a = source(original, values, index=1)
    b = source(original, values, index=2)
    workspace = root / "candidate"
    saved = retain(workspace, original, [b["source_file"], a["source_file"]], execute=True)
    result = run(workspace, PERIOD, CUTOFF, saved["run_id"], execute=True)
    data = payloads(workspace)
    validate_bundle(data)
    assert len(data["native"]["rows"]) == 8 and len(data["gold"]["rows"]) == 2
    first, second = data["gold"]["rows"]
    assert len(first["contributors"]) == 4 and len(second["contributors"]) == 2
    assert {r["title"] for r in first["contributors"]} == {"first", "variant"}
    assert result["outside_month_native_rows"] == 2 and result["selected_contributions"] == 6
    assert result["observed_publication_days"] == ["2026-09-01", "2026-09-02"]
    assert len(result["unobserved_days"]) == 28
    assert all(
        r["event_date"] is None and r["publisher_document_verified"] is False for r in data["gold"]["rows"]
    )
    assert result["release_lag_days"] is None and result["latest_available_period"] is None
    assert result["latest_source_availability_verified"] is False and result["article_requests"] == 0
    before = readiness.inventory(workspace)
    assert (
        run(workspace, PERIOD, CUTOFF, saved["run_id"], check=True)["output_sha256"]
        == result["output_sha256"]
    )
    assert readiness.inventory(workspace) == before
    with pytest.raises(ValueError, match="immutable"):
        run(workspace, PERIOD, CUTOFF, saved["run_id"], execute=True)


@pytest.mark.parametrize("status", [None, 403, 429, 503])
def test_http_success_must_be_explicit(roots, status):
    root, original = roots
    row = source(original, status=status)
    with pytest.raises(ValueError):
        retain(root / "candidate", original, [row["source_file"]], execute=True)
    assert not (root / "candidate").exists()


@pytest.mark.parametrize(
    "change",
    [
        "malformed",
        "doctype",
        "wrong_query",
        "wrong_title",
        "wrong_language",
        "wrong_generator",
        "future_build",
        "nested_item",
        "duplicate_title",
    ],
)
def test_changed_or_unsafe_feed_blocks_before_silver_gold(roots, change):
    raw, _ = xml([item()])
    tree = etree.fromstring(raw)
    channel = tree.find("channel")
    if change == "wrong_query":
        channel.find("link").text = channel.findtext("link").replace("Aeromexico", "Other")
    elif change == "wrong_title":
        channel.find("title").text = "Generic RSS error"
    elif change == "wrong_language":
        channel.find("language").text = "en-US"
    elif change == "wrong_generator":
        channel.find("generator").text = "unknown"
    elif change == "future_build":
        channel.find("lastBuildDate").text = "Sat, 03 Oct 2026 12:00:00 GMT"
    elif change == "nested_item":
        etree.SubElement(etree.SubElement(channel, "other"), "item")
    elif change == "duplicate_title":
        etree.SubElement(channel.find("item"), "title").text = "other title"
    content = etree.tostring(tree)
    if change == "malformed":
        content = b"<rss><broken"
    if change == "doctype":
        content = b'<!DOCTYPE rss [<!ENTITY ext SYSTEM "file:///nonexistent">]>' + content
    candidate, run_id, _ = prepared(roots, content=content)
    with pytest.raises(ValueError):
        run(candidate, PERIOD, CUTOFF, run_id, execute=True)
    assert not (candidate / "data/silver").exists() and not (candidate / "data/gold").exists()
    assert not (candidate / "receipts/rss-2026M09.json").exists()


@pytest.mark.parametrize("change", ["naive", "future", "missing", "invalid_url"])
def test_invalid_item_never_silently_disappears(roots, change):
    invalid = item()
    if change == "naive":
        invalid["pubDate"] = "Tue, 01 Sep 2026 06:30:00"
    if change == "future":
        invalid["pubDate"] = "Sat, 03 Oct 2026 12:00:00 GMT"
    if change == "missing":
        invalid.pop("pubDate")
    if change == "invalid_url":
        invalid["link"] = "javascript:alert(1)"
    candidate, run_id, _ = prepared(roots, [item(), invalid])
    with pytest.raises(ValueError):
        run(candidate, PERIOD, CUTOFF, run_id, execute=True)
    assert not (candidate / "data/gold").exists()


@pytest.mark.parametrize("kind", list(OUTPUTS))
def test_replay_detects_output_tampering_without_writes(roots, kind):
    candidate, run_id, _ = prepared(roots)
    run(candidate, PERIOD, CUTOFF, run_id, execute=True)
    path = candidate / "data" / OUTPUTS[kind]
    payload = json.loads(path.read_text())
    payload["agent_eligible"] = True
    path.write_text(json.dumps(payload))
    before = readiness.inventory(candidate)
    with pytest.raises(ValueError):
        run(candidate, PERIOD, CUTOFF, run_id, check=True)
    assert readiness.inventory(candidate) == before


def test_baseline_comparison_ignores_repeated_captures_and_freezes_selection(roots):
    root, original = roots
    a = source(original, index=1)
    b = source(original, index=2)
    prior = root / "prior"
    pa = retain(prior, original, [a["source_file"]], execute=True)
    run(prior, PERIOD, CUTOFF, pa["run_id"], execute=True)
    candidate = root / "candidate"
    pb = retain(candidate, original, [a["source_file"], b["source_file"]], execute=True)
    baseline = candidate / "baselines/prior.json"
    baseline.parent.mkdir()
    baseline.write_bytes((prior / "data" / OUTPUTS["gold"]).read_bytes())
    result = run(candidate, PERIOD, CUTOFF, pb["run_id"], execute=True, baseline="baselines/prior.json")
    assert result["revisions"]["changed"] == 0 and result["revisions"]["unchanged"] == 1
    run(candidate, PERIOD, CUTOFF, pb["run_id"], check=True)
    prior_payload = json.loads(baseline.read_text())
    prior_payload["query_scope"] = ["https://example.test/other"]
    baseline.write_text(json.dumps(prior_payload))
    with pytest.raises(ValueError):
        run(candidate, PERIOD, CUTOFF, pb["run_id"], check=True)


@pytest.mark.parametrize("change", ["month", "scope", "semantics", "parent_date"])
def test_baseline_rejects_incompatible_or_inconsistent_scope(roots, change):
    candidate, run_id, _ = prepared(roots)
    result = parse(
        [
            (p.read_bytes(), json.loads(Path(str(p) + ".meta.json").read_text()))
            for p in (candidate / "data/bronze").rglob("*.xml")
        ],
        PERIOD,
        CUTOFF,
    )
    from src.source_updates.rss_contract import envelopes

    prior = envelopes(result[0], PERIOD, result[1]["query_scope"])["gold"]
    if change == "month":
        prior["period"] = "2026M08"
    if change == "scope":
        prior["query_scope"] = ["https://example.test/other"]
    if change == "semantics":
        prior["date_basis"] = "publisher_verified"
    if change == "parent_date":
        prior["rows"][0]["contributors"][0]["local_publication_date"] = "2026-09-02"
    baseline = candidate / "baselines/prior.json"
    baseline.parent.mkdir()
    baseline.write_text(json.dumps(prior))
    with pytest.raises(ValueError):
        run(candidate, PERIOD, CUTOFF, run_id, execute=True, baseline="baselines/prior.json")
    assert not (candidate / "data/gold").exists()


def test_batch_plan_full_chain_readiness_and_global_stay_closed(roots):
    root, original = roots
    row = source(original)
    recipe = dict(
        version=1, as_of=CUTOFF, source_root=str(original), period=PERIOD, originals=[row["source_file"]]
    )
    assert batch(recipe, root / "batch")["status"] == "planned_not_executed"
    assert not (root / "batch").exists()
    result = batch(recipe, root / "batch", execute=True)
    assert result["status"] == "checks_passed"
    candidate = result["workspace"]
    receipt = result["result"]["retention_run_id"]
    task = dict(
        id="rss",
        product="rss",
        period=PERIOD,
        adapter="rss_retained",
        workspace=candidate,
        receipt_id=receipt,
        required=True,
        candidate_as_of=CUTOFF,
    )
    plan = dict(version=1, as_of=CUTOFF, required_items=["rss"], items=[task])
    checked = readiness.execute(plan, root / "ready", write=True)
    assert checked["status"] == "checks_passed" and checked["ready_for_calendar_incorporation"] is False
    readiness.execute(plan, root / "ready", check=True)
    entry = {k: v for k, v in task.items() if k != "required"}
    entry.update(cadence="monthly", used=True, depends_on=[])
    global_recipe = dict(
        version=1,
        round="monthly",
        as_of=CUTOFF,
        monthly_period=PERIOD,
        quarterly_period="2026Q3",
        items=[entry],
        releases=[],
    )
    final = global_readiness.execute(global_recipe, root / "global", write=True)
    assert final["status"] == "blocked_global_policy" and final["core_ready"] is False
    assert final["ready_for_calendar_incorporation"] is False
    global_readiness.execute(global_recipe, root / "global", check=True)


def test_batch_preserves_failed_stage_receipt_without_gold(roots):
    root, original = roots
    row = source(original, [item(published="2026-08-01T12:00:00+00:00")])
    recipe = dict(
        version=1, as_of=CUTOFF, source_root=str(original), period=PERIOD, originals=[row["source_file"]]
    )
    result = batch(recipe, root / "batch", execute=True)
    assert result["status"] == "blocked" and result["failed_action"] == "certify"
    assert not (Path(result["workspace"]) / "data/gold").exists()
    assert len(list((root / "batch").glob("rss-round-*.json"))) == 1
