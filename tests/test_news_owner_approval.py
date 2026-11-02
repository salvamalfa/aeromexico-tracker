"""Isolated synthetic approval-contract tests; never modify a real corpus."""

import json

import pytest

from scripts.news.approve_review_package import encoded, prepare, sha
from src.conversational_analytics.evidence_index import candidate_content_sha256, canonical_index_sha256


def inputs(kind="news"):
    record = {
        "id": "synthetic-test",
        "kind": kind,
        "description": "Synthetic test summary",
        "source": {"id": "test", "url": "https://www.sec.gov/test", "sha256": "a" * 64},
    }
    digest = candidate_content_sha256(record)
    package = {
        "schema": "monthly_news_batch_approval_proposal_v1",
        "status": "owner_review_required",
        "candidate_count": 1,
        "proposed_index_records": [{"record": record, "candidate_content_sha256": digest}],
    }
    package["proposal_sha256"] = sha(
        json.dumps(
            package, ensure_ascii=False, sort_keys=True, allow_nan=False, separators=(",", ":")
        ).encode()
    )
    baseline = encoded({"schema": "chat_evidence_index_v1", "version": "synthetic-test", "records": []})
    decision = {
        "owner_id": "salvamalfa",
        "decision": "owner_approved",
        "response_origin": "explicit_owner_chat_response",
        "question": "Synthetic test only",
        "quoted_response": "Synthetic fixture; not a real owner decision",
        "recorded_at": "2026-11-02T00:00:00Z",
        "decision_reference": "synthetic-test-only",
        "proposal_sha256": package["proposal_sha256"],
        "approved_item_hashes": {record["id"]: digest},
        "base_index_raw_sha256": sha(baseline),
        "base_index_canonical_sha256": canonical_index_sha256(json.loads(baseline)),
    }
    return package, decision, baseline


def test_no_response_or_missing_item_binding_cannot_issue_receipts():
    package, decision, baseline = inputs()
    decision["quoted_response"] = ""
    with pytest.raises(ValueError, match="explicit owner response"):
        prepare(package, decision, baseline)
    package, decision, baseline = inputs()
    decision["approved_item_hashes"] = {}
    with pytest.raises(ValueError, match="every exact proposed item"):
        prepare(package, decision, baseline)


def test_news_decision_cannot_approve_an_analysis_or_report():
    package, decision, baseline = inputs(kind="report")
    with pytest.raises(ValueError, match="Only the exact normalized news"):
        prepare(package, decision, baseline)
