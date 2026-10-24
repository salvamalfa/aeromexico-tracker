"""Adversarial RSS checks, independent of the certifier implementation tests."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest
from lxml import etree

from src.source_updates.readiness import inventory
from src.source_updates.rss_candidate import revisions, run
from src.source_updates.rss_contract import envelopes, validate_bundle, validate_gold
from src.source_updates.rss_native import parse
from src.source_updates.rss_retention import inputs, retain
from tests.test_source_update_rss import CUTOFF, PERIOD, item, prepared, source, xml
from tests.test_source_update_rss import roots as shared_roots

roots = shared_roots


def bundle(roots, values=None):
    _, original = roots
    row = source(original, values)
    tables, detail = parse([((original / row["source_file"]).read_bytes(), row)], PERIOD, CUTOFF)
    return envelopes(tables, PERIOD, detail["query_scope"])


def test_identical_items_have_distinct_physical_parents_at_local_month_edges(roots):
    values = [
        item("August locally", published="2026-09-01T05:59:59+00:00"),
        item("September starts", published="2026-09-01T06:00:00+00:00"),
        item("September starts", published="2026-09-01T06:00:00+00:00"),
        item("September ends", published="2026-10-01T05:59:59+00:00"),
        item("October locally", published="2026-10-01T06:00:00+00:00"),
    ]
    data = bundle(roots, values)
    assert validate_bundle(data) == dict(native_rows=5, gold_rows=2, artifacts=1, links=10)
    native, gold = data["native"]["rows"], data["gold"]["rows"]
    assert [r["selected_month"] for r in native] == [False, True, True, True, False]
    assert [r["item_1based"] for r in native] == [1, 2, 3, 4, 5]
    assert len({r["record_id"] for r in native}) == 5
    assert len(gold[0]["contributors"]) == 2
    assert {r["source_locator"] for r in gold[0]["contributors"]} == {
        "/rss/channel/item[2]",
        "/rss/channel/item[3]",
    }
    assert [r["local_publication_date"] for r in gold] == ["2026-09-01", "2026-09-30"]


def test_opaque_google_identifiers_and_meaningful_queries_remain_separate(roots):
    urls = [
        "https://news.google.com/rss/articles/AAA?oc=5&utm_source=feed#fragment",
        "https://news.google.com/rss/articles/AAA?oc=5",
        "https://news.google.com/rss/articles/AAA?oc=6",
        "https://news.google.com/rss/articles/BBB?oc=5",
    ]
    data = bundle(roots, [item(url=u) for u in urls])
    assert len(data["gold"]["rows"]) == 3
    grouped = {r["canonical_url"]: r for r in data["gold"]["rows"]}
    assert len(grouped[urls[1]]["contributors"]) == 2
    assert {r["url_as_reported"] for r in grouped[urls[1]]["contributors"]} == set(urls[:2])
    assert all(r["publisher_document_verified"] is False for r in data["native"]["rows"])
    assert not any("language" in r or "carrier" in r for r in data["native"]["rows"])


@pytest.mark.parametrize(
    "change", ["missing_channel", "double_channel", "duplicate_build", "nested_title", "naive_build"]
)
def test_channel_structure_is_certified_before_any_output(roots, change):
    raw, _ = xml([item()])
    tree = etree.fromstring(raw)
    channel = tree.find("channel")
    if change == "missing_channel":
        tree.remove(channel)
    elif change == "double_channel":
        tree.append(copy.deepcopy(channel))
    elif change == "duplicate_build":
        channel.append(copy.deepcopy(channel.find("lastBuildDate")))
    elif change == "nested_title":
        etree.SubElement(channel.find("title"), "b").text = "hidden"
    else:
        channel.find("lastBuildDate").text = "Fri, 02 Oct 2026 12:00:00"
    candidate, run_id, _ = prepared(roots, content=etree.tostring(tree))
    with pytest.raises(ValueError):
        run(candidate, PERIOD, CUTOFF, run_id, execute=True)
    assert not (candidate / "data/gold").exists()


def test_invalid_outside_month_item_is_not_silently_dropped(roots):
    invalid = item("Outside month", published="2026-08-01T06:00:00+00:00")
    invalid["link"] = "file:///private/source"
    candidate, run_id, _ = prepared(roots, [item(), invalid])
    with pytest.raises(ValueError):
        run(candidate, PERIOD, CUTOFF, run_id, execute=True)
    assert not (candidate / "data/silver").exists()


@pytest.mark.parametrize("change", ["body", "sidecar", "manifest", "receipt", "extra_file"])
def test_bronze_and_retention_tampering_block_without_partial_gold(roots, change):
    candidate, run_id, row = prepared(roots)
    bronze = candidate / "data/bronze"
    body = bronze / row["source_file"]
    if change == "body":
        body.write_bytes(body.read_bytes() + b" ")
    elif change == "sidecar":
        path = Path(str(body) + ".meta.json")
        meta = json.loads(path.read_text())
        meta["source_url"] = "https://news.google.com/rss/search?q=Other"
        path.write_text(json.dumps(meta))
    elif change == "manifest":
        with (bronze / "_manifest.jsonl").open("a") as stream:
            stream.write(json.dumps({**row, "logical_key": "rss|google_en|current|xml"}) + "\n")
    elif change == "receipt":
        path = candidate / "receipts" / f"rss-retained-{run_id}.json"
        receipt = json.loads(path.read_text())
        receipt["network_requests"] = 1
        path.write_text(json.dumps(receipt))
    else:
        (bronze / "unselected.xml").write_text("<rss/>")
    with pytest.raises(ValueError):
        run(candidate, PERIOD, CUTOFF, run_id, execute=True)
    assert not (candidate / "data/gold").exists()
    assert not (candidate / "receipts/rss-2026M09.json").exists()


@pytest.mark.parametrize("change", ["alias", "locale", "duplicate_query", "credential"])
def test_capture_identity_cannot_be_relabelled(roots, change):
    root, original = roots
    row = source(original)
    if change == "alias":
        row["source_system"] = "gdelt"
    elif change == "locale":
        row["logical_key"] = "rss|google_en|current|xml"
    elif change == "duplicate_query":
        row["source_url"] += "&q=Other"
    else:
        row["source_url"] = row["source_url"].replace("https://", "https://user:pass@")
    (original / "_manifest.jsonl").write_text(json.dumps(row) + "\n")
    Path(str(original / row["source_file"]) + ".meta.json").write_text(json.dumps(row))
    with pytest.raises(ValueError):
        retain(root / "candidate", original, [row["source_file"]], execute=True)
    assert not (root / "candidate").exists()


@pytest.mark.parametrize(
    "change", ["parent_omitted", "bridge_omitted", "bridge_extra", "borrowed_artifact", "eligibility"]
)
def test_complete_domain_and_all_parents_are_enforced(roots, change):
    data = bundle(roots, [item("first"), item("second")])
    if change == "parent_omitted":
        data["gold"]["rows"][0]["contributors"].pop()
    elif change == "bridge_omitted":
        data["lineage"]["rows"].pop()
    elif change == "bridge_extra":
        extra = copy.deepcopy(data["lineage"]["rows"][0])
        extra["target_id"] = "f" * 64
        data["lineage"]["rows"].append(extra)
    elif change == "borrowed_artifact":
        data["native"]["rows"][0]["source_artifact_id"] = "f" * 64
    else:
        data["gold"]["rows"][0]["agent_eligible"] = True
    with pytest.raises((ValueError, KeyError)):
        validate_bundle(data)


@pytest.mark.parametrize(
    "field,value",
    [
        ("source_artifact_id", "f" * 64),
        ("feed_id", "google_en"),
        ("publisher_url_as_declared", "javascript:alert(1)"),
    ],
)
def test_baseline_rejects_internally_impossible_provenance(roots, field, value):
    prior = bundle(roots)["gold"]
    prior["rows"][0]["contributors"][0][field] = value
    with pytest.raises(ValueError):
        validate_gold(prior)


def test_same_scope_title_change_is_revision_and_outside_baseline_is_rejected(roots):
    root, _ = roots
    data = bundle(roots)["gold"]
    folder = root / "candidate/baselines"
    folder.mkdir(parents=True)
    path = folder / "prior.json"
    path.write_text(json.dumps(data))
    current = copy.deepcopy(data)
    current["rows"][0]["contributors"][0]["title"] = "Corrected declaration"
    result = revisions(folder.parent, "baselines/prior.json", current)
    assert result["changed"] == 1 and result["added"] == result["removed"] == 0
    outside = folder.parent / "outside.json"
    outside.write_text(json.dumps(data))
    with pytest.raises(ValueError):
        revisions(folder.parent, "outside.json", current)


def test_readonly_replay_rejects_accepted_receipt_tampering_and_preserves_files(roots):
    candidate, run_id, _ = prepared(roots)
    run(candidate, PERIOD, CUTOFF, run_id, execute=True)
    path = candidate / "receipts/rss-2026M09.json"
    receipt = json.loads(path.read_text())
    receipt["selected_contributions"] += 1
    path.write_text(json.dumps(receipt))
    before = inventory(candidate)
    with pytest.raises(ValueError):
        run(candidate, PERIOD, CUTOFF, run_id, check=True)
    assert inventory(candidate) == before


def test_capture_cutoff_and_closed_local_month_are_distinct_guards(roots):
    candidate, run_id, _ = prepared(roots)
    with pytest.raises(ValueError, match="after requested cutoff"):
        inputs(candidate, run_id, "2026-10-02T05:59:59-06:00")
    with pytest.raises(ValueError, match="closed"):
        run(candidate, PERIOD, "2026-09-30T23:59:59-06:00", run_id, execute=True)
    assert not (candidate / "data/gold").exists()
