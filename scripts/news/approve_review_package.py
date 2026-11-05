"""Record an explicit owner decision for an immutable reviewed News package.

No implicit approval, network calls, deployments or environment updates.
The decision must be supplied from the actual owner response, separately from
the proposal. Default mode only validates and reports the proposed transition.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from copy import deepcopy
from datetime import datetime
from pathlib import Path

from src.conversational_analytics.evidence_index import (
    APPROVED_OWNER_ID,
    _approved,
    candidate_content_sha256,
    canonical_index_sha256,
)


def encoded(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False, indent=2) + "\n").encode()


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def validate(package, decision, baseline):
    body = {key: value for key, value in package.items() if key != "proposal_sha256"}
    fingerprint = sha(
        json.dumps(body, ensure_ascii=False, sort_keys=True, allow_nan=False, separators=(",", ":")).encode()
    )
    if (
        package.get("schema") != "monthly_news_batch_approval_proposal_v1"
        or package.get("status") != "owner_review_required"
        or fingerprint != package.get("proposal_sha256")
        or decision.get("proposal_sha256") != fingerprint
    ):
        raise ValueError("Owner decision must identify the exact immutable review proposal")
    if (
        decision.get("owner_id") != APPROVED_OWNER_ID
        or decision.get("decision") != "owner_approved"
        or decision.get("response_origin") != "explicit_owner_chat_response"
        or not decision.get("question")
        or not decision.get("quoted_response")
        or not decision.get("decision_reference")
    ):
        raise ValueError("An explicit owner response, actor and decision reference are required")
    at = datetime.fromisoformat(decision["recorded_at"].replace("Z", "+00:00"))
    if at.tzinfo is None:
        raise ValueError("Decision registration time must include its actual timezone")
    if (
        sha(baseline) != decision["base_index_raw_sha256"]
        or canonical_index_sha256(json.loads(baseline)) != decision["base_index_canonical_sha256"]
    ):
        raise ValueError("Approved baseline differs from the explicitly selected index")
    proposed = package["proposed_index_records"]
    item_hashes = {item["record"]["id"]: item["candidate_content_sha256"] for item in proposed}
    if (
        len(item_hashes) != len(proposed)
        or len(proposed) != package["candidate_count"]
        or item_hashes != decision.get("approved_item_hashes")
    ):
        raise ValueError("Decision must bind every exact proposed item, without additions or omissions")
    for item in proposed:
        record = item["record"]
        if (
            record.get("kind") != "news"
            or "review" in record
            or candidate_content_sha256(record) != item["candidate_content_sha256"]
        ):
            raise ValueError("Only the exact normalized news records in the reviewed package may be approved")
    return fingerprint


def prepare(package, decision, baseline):
    fingerprint = validate(package, decision, baseline)
    payload = json.loads(baseline)
    previous = deepcopy(payload["records"])
    existing = {record["id"] for record in previous}
    if existing & set(decision["approved_item_hashes"]):
        raise ValueError("Reviewed item IDs already exist; do not silently renew an approval")
    receipts = []
    for item in package["proposed_index_records"]:
        record = deepcopy(item["record"])
        receipt_id = "owner-news-" + fingerprint[:16] + ":" + record["id"]
        receipt = {
            "receipt_id": receipt_id,
            "candidate_id": record["id"],
            "decision": "owner_approved",
            "owner_id": decision["owner_id"],
            "approved_at": decision["recorded_at"],
            "source_sha256": record["source"]["sha256"],
            "excerpt_sha256": sha(record["description"].encode()),
            "candidate_content_sha256": item["candidate_content_sha256"],
            "decision_reference": decision["decision_reference"],
            "proposal_sha256": fingerprint,
        }
        record["review"] = {
            "decision": "owner_approved",
            "owner_id": decision["owner_id"],
            "approved_at": decision["recorded_at"],
            "receipt_id": receipt_id,
            "receipt": receipt,
        }
        if not _approved(record):
            raise ValueError("Generated receipt does not satisfy the normal evidence approval contract")
        payload["records"].append(record)
        receipts.append(receipt)
    payload["version"] = "evidence-news-" + decision["recorded_at"][:10] + "-" + fingerprint[:8]
    if payload["records"][: len(previous)] != previous:
        raise ValueError("Historical approved records changed")
    index_raw = encoded(payload)
    proof = {
        "schema": "news_batch_approval_v1",
        "decision": decision,
        "proposal_sha256": fingerprint,
        "approved_items": [
            {
                "id": r["candidate_id"],
                "candidate_content_sha256": r["candidate_content_sha256"],
                "receipt_id": r["receipt_id"],
            }
            for r in receipts
        ],
        "preserved_record_ids": [record["id"] for record in previous],
        "approved_index_raw_sha256": sha(index_raw),
        "approved_index_canonical_sha256": canonical_index_sha256(payload),
        "index_records": len(payload["records"]),
        "news_records": sum(row.get("kind") == "news" for row in payload["records"]),
        "approval_scope": "only_the_reviewed_news_items_no_analysis_or_map_approval",
    }
    return index_raw, receipts, proof


def run(package_path, decision_path, index_path, workspace, proof_path, *, execute=False):
    baseline = index_path.read_bytes()
    package = json.loads(package_path.read_bytes())
    decision = json.loads(decision_path.read_bytes())
    index_raw, receipts, proof = prepare(package, decision, baseline)
    if not execute:
        return {"mode": "dry_run", "writes": 0, "records_to_approve": len(receipts), **proof}
    if workspace.exists() or proof_path.exists():
        raise ValueError("Approval records are immutable; choose new destinations")
    workspace.mkdir(parents=True)
    (workspace / "baseline-index.json").write_bytes(baseline)
    (workspace / "proposal.json").write_bytes(package_path.read_bytes())
    (workspace / "owner-decision.json").write_bytes(decision_path.read_bytes())
    (workspace / "receipts").mkdir()
    for receipt in receipts:
        (workspace / "receipts" / (receipt["candidate_id"] + ".json")).write_bytes(encoded(receipt))
    if index_path.read_bytes() != baseline:
        raise ValueError("Approved index changed concurrently; activation was not performed")
    proof_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = index_path.with_suffix(index_path.suffix + ".news-update")
    if temporary.exists():
        raise ValueError("An index update is already in progress")
    temporary.write_bytes(index_raw)
    temporary.replace(index_path)
    proof_path.write_bytes(encoded(proof))
    (workspace / "activation.json").write_bytes(encoded(proof))
    return {"mode": "owner_decision_recorded", **proof}


def check(workspace, index_path, proof_path):
    package = json.loads((workspace / "proposal.json").read_bytes())
    decision = json.loads((workspace / "owner-decision.json").read_bytes())
    expected, receipts, proof = prepare(package, decision, (workspace / "baseline-index.json").read_bytes())
    if index_path.read_bytes() != expected or proof_path.read_bytes() != encoded(proof):
        raise ValueError("Activated index/proof differs from the exact owner-approved transition")
    if (workspace / "activation.json").read_bytes() != encoded(proof):
        raise ValueError("Activation receipt changed")
    for receipt in receipts:
        if (workspace / "receipts" / (receipt["candidate_id"] + ".json")).read_bytes() != encoded(receipt):
            raise ValueError("Per-item approval receipt changed")
    return {"mode": "checked", **proof}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("package", "decision", "index", "workspace", "proof"):
        parser.add_argument("--" + name, type=Path, required=name not in {"package", "decision"})
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--execute", action="store_true")
    mode.add_argument("--check", action="store_true")
    args = parser.parse_args()
    result = (
        check(args.workspace, args.index, args.proof)
        if args.check
        else run(args.package, args.decision, args.index, args.workspace, args.proof, execute=args.execute)
    )
    print(
        json.dumps(
            {
                key: result[key]
                for key in (
                    "mode",
                    "proposal_sha256",
                    "approved_index_raw_sha256",
                    "approved_index_canonical_sha256",
                    "index_records",
                    "news_records",
                )
            },
            ensure_ascii=False,
        )
    )
