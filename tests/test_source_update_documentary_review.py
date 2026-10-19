"""Documentary audits fail closed without changing curated facts or candidate status."""

from copy import deepcopy
import hashlib
import json

import pytest

from src.conversational_analytics.evidence_index import candidate_content_sha256
from src.source_updates import news_cut, primary_review as review


def retained(tmp_path, body, name="feed.xml", system="rss"):
    root = tmp_path / "bronze"
    root.mkdir(exist_ok=True)
    row = {
        "source_file": name,
        "source_system": system,
        "source_url": "https://news.google.com/rss/search?q=Aeromexico",
        "bytes": len(body),
        "sha256": hashlib.sha256(body).hexdigest(),
        "downloaded_at": "2026-10-19T01:00:00Z",
        "logical_key": "rss|google_es|current|xml",
    }
    (root / name).write_bytes(body)
    (root / (name + ".meta.json")).write_text(json.dumps(row))
    (root / "_manifest.jsonl").write_text(json.dumps(row) + "\n")
    return root, row


def test_original_body_sidecar_and_manifest_are_independently_checked(tmp_path):
    root, row = retained(tmp_path, b"abc")
    assert review.original(root, row).read_bytes() == b"abc"
    (root / "feed.xml.meta.json").write_text(json.dumps({**row, "source_url": "https://example.com"}))
    with pytest.raises(ValueError, match="sidecar"):
        review.original(root, row)
    (root / "feed.xml").write_bytes(b"abd")
    with pytest.raises(ValueError, match="hash/size"):
        review.original(root, row)


def test_original_path_escape_and_symlink_rejected(tmp_path):
    root, row = retained(tmp_path, b"abc")
    with pytest.raises(ValueError, match="traversal"):
        review.original(root, {**row, "source_file": "../feed.xml"})
    (root / "alias.xml").symlink_to(root / "feed.xml")
    with pytest.raises(ValueError, match="symlinks"):
        review.within(root, "alias.xml")


def test_exact_json_value_projection_and_html_offset(tmp_path):
    p = tmp_path / "source.json"
    p.write_text('{"forms":["6-K","20-F","6-K"]}')
    evidence = {
        "locator": {"json_pointer": "/forms"},
        "value": ["20-F", "6-K"],
        "projection": "sorted distinct forms observed; not an exhaustive lifetime catalogue",
    }
    review.verify_evidence(evidence, p, {})
    with pytest.raises(ValueError, match="value mismatch"):
        review.verify_evidence({**evidence, "value": ["20-F"]}, p, {})
    p.write_text("<html><body><p>Annual   statement</p></body></html>")
    excerpt = {
        "locator": {"normalized_char_start": 0, "normalized_char_end": 16},
        "excerpt": "Annual statement",
        "matched_phrase": "Annual",
    }
    review.verify_evidence(excerpt, p, {})
    with pytest.raises(ValueError, match="excerpt mismatch"):
        review.verify_evidence({**excerpt, "excerpt": "Annual judgement"}, p, {})


def test_review_checks_code_version_and_never_approves(tmp_path):
    root, row = retained(tmp_path, b'{"cik":"0001561861"}', "source.json")
    (tmp_path / "input.py").write_text("# reviewed input\n")
    bundle = {
        "schema_version": 1,
        "agent_eligible": False,
        "local_inputs": {"input.py": review.sha(tmp_path / "input.py")},
        "sources": {"a": row},
        "evidence": {"cik": {"source_id": "a", "locator": {"json_pointer": "/cik"}, "value": "0001561861"}},
        "carriers": {
            "AEROMEXICO": {
                "attribute_assessments": {
                    "cik": {"agent_eligible": False, "evidence_ids": ["cik"], "status": "qualified_support"}
                }
            }
        },
    }
    result = review.verify(bundle, {"old_public": root}, tmp_path)
    assert result["attribute_assessments"] == 1 and not result["silver_gold_certification"]
    changed = deepcopy(bundle)
    changed["carriers"]["AEROMEXICO"]["attribute_assessments"]["cik"]["agent_eligible"] = True
    with pytest.raises(ValueError, match="cannot confer"):
        review.verify(changed, {"old_public": root}, tmp_path)
    (tmp_path / "input.py").write_text("# changed\n")
    with pytest.raises(ValueError, match="local inputs changed"):
        review.verify(bundle, {"old_public": root}, tmp_path)


def rss(items):
    return (
        "<rss><channel>"
        + "".join(
            f"<item><title>{title}</title><link>{url}</link><pubDate>{stamp}</pubDate></item>"
            for title, url, stamp in items
        )
        + "</channel></rss>"
    ).encode()


def test_monthly_rss_preserves_contributors_local_cut_and_missing_not_zero(tmp_path):
    root, _ = retained(
        tmp_path,
        rss(
            [
                ("One", "https://example.com/a?utm_source=feed", "Tue, 01 Sep 2026 05:59:59 GMT"),
                ("Two", "https://example.com/a", "Tue, 01 Sep 2026 06:00:00 GMT"),
                ("Two revision", "https://example.com/a#top", "Tue, 01 Sep 2026 07:00:00 GMT"),
                ("October", "https://example.com/oct", "Thu, 01 Oct 2026 06:00:00 GMT"),
            ]
        ),
    )
    result = news_cut.rss_cut(root, "2026-09", "2026-10-19T12:00:00-06:00")
    assert result["selected_dated_urls"] == 1 and result["selected_contributions"] == 2
    assert len(result["records"][0]["contributors"]) == 2
    assert len(result["days_not_observed_in_selected_captures"]) == 29
    assert result["missing_days_mean"] == "not_observed_never_no_news"
    assert not result["silver_gold_certification"] and result["writes"] == 0


def test_rss_future_and_naive_dates_are_diagnostics_not_news(tmp_path):
    root, _ = retained(
        tmp_path,
        rss(
            [
                ("Future", "https://example.com/a", "Tue, 20 Oct 2026 12:00:00 GMT"),
                ("Naive", "https://example.com/b", "Tue, 01 Sep 2026 12:00:00"),
            ]
        ),
    )
    result = news_cut.rss_cut(root, "2026-09", "2026-10-19T12:00:00-06:00")
    assert result["selected_dated_urls"] == 0 and len(result["rejected_items"]) == 2
    assert result["coverage"].startswith("partial_metadata")


def test_rss_external_entity_declaration_rejected(tmp_path):
    body = b'<!DOCTYPE rss [<!ENTITY secret SYSTEM "file:///etc/passwd">]><rss><channel/></rss>'
    root, _ = retained(tmp_path, body)
    with pytest.raises(ValueError, match="DOCTYPE"):
        news_cut.rss_cut(root, "2026-09", "2026-10-19T12:00:00-06:00")


def candidate():
    row = {
        "id": "a",
        "story_id": "a",
        "kind": "news",
        "review_status": "candidate_unapproved",
        "source": {"url": "https://example.com/doc", "sha256": "a" * 64},
        "published_at": "2026-09-30",
        "first_captured_at": "2026-10-15T04:29:40Z",
        "verified_at": "2026-10-15T04:29:40Z",
        "event_date": None,
        "event_end_date": None,
    }
    row["candidate_content_sha256"] = candidate_content_sha256(row)
    return {
        "schema": "monthly_news_candidate_v1",
        "coverage": "Partial selected documents",
        "cut_at": "2026-10-15T04:29:56Z",
        "records": [row],
    }


def test_candidate_self_hash_does_not_assert_body_verification_or_approval():
    payload = candidate()
    result = news_cut.candidate_cut(payload)
    assert result["self_hashes_valid"] and not result["source_bodies_reverified"]
    payload["records"][0]["event_date"] = "2026-09-29"
    with pytest.raises(ValueError, match="content hash"):
        news_cut.candidate_cut(payload)


@pytest.mark.parametrize("mutation", ["approval", "duplicate", "date_order"])
def test_candidate_rejects_activation_duplicates_and_false_date_order(mutation):
    payload = candidate()
    row = payload["records"][0]
    if mutation == "approval":
        row["review"] = {"decision": "owner_approved"}
    elif mutation == "duplicate":
        payload["records"].append(deepcopy(row))
    else:
        row["published_at"] = "2026-10-20"
        row["candidate_content_sha256"] = candidate_content_sha256(
            {k: v for k, v in row.items() if k != "candidate_content_sha256"}
        )
    with pytest.raises(ValueError):
        news_cut.candidate_cut(payload)
