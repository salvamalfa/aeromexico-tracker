"""Transport an explicitly approved prior News pin only to its original verifier.

The new externally pinned index remains mandatory. The owner's immutable News
batch names both the old raw bytes and canonical approval pin; neither identity
is nominated by the historical file being checked.
"""

from __future__ import annotations

import hashlib
import json
import os

from src.conversational_analytics.evidence_index import EvidenceIndex, canonical_index_sha256

from . import editorial as transport
from .issuer_scope import verify_historical_baseline as released_verifier

BATCH = "config/news/approved-batch-20261102.json"
BATCH_SHA256 = "4360ccb2f4c47188743f1976c50a4752f868fdd79174bd8566cb8ffea0aaf3c5"
INDEX = "config/chat/evidence/approved-index.json"
PIN = "CHAT_EVIDENCE_APPROVED_INDEX_SHA256"


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def historical_environment(repo, spec):
    """Refuse any changed authority, baseline index, prior record or current pin."""
    raw = (repo / BATCH).read_bytes()
    if sha(raw) != BATCH_SHA256 or transport._git(repo, "show", f"HEAD:{BATCH}") != raw:
        raise ValueError("Historical News transport requires the exact committed owner batch")
    batch = json.loads(raw)
    current_raw = (repo / INDEX).read_bytes()
    current = EvidenceIndex(repo / INDEX)  # Requires the NEW external pin normally.
    if (
        current.sha256 != batch["approved_index_canonical_sha256"]
        or sha(current_raw) != batch["approved_index_raw_sha256"]
        or len(current.records) != batch["index_records"]
    ):
        raise ValueError("Current News authority differs from the owner's approved batch")
    manifest, _ = transport.baseline(repo, spec)
    old_raw = transport._git(repo, "show", f"{spec['baseline_commit']}:{INDEX}")
    if transport._git(repo, "show", f"{manifest['code_commit']}:{INDEX}") != old_raw:
        raise ValueError("Historical verifier and its exact baseline use different News indexes")
    decision = batch["decision"]
    old = json.loads(old_raw)
    if (
        sha(old_raw) != decision["base_index_raw_sha256"]
        or canonical_index_sha256(old) != decision["base_index_canonical_sha256"]
        or len(old["records"]) != 10
        or [r["id"] for r in old["records"]] != batch["preserved_record_ids"]
    ):
        raise ValueError("Historical News index differs from the explicitly approved prior cohort")
    prior_ids = set(batch["preserved_record_ids"])
    retained = [r for r in json.loads(current_raw)["records"] if r["id"] in prior_ids]
    if retained != old["records"]:
        raise ValueError("The approved prior News records changed in the current index")
    environment = dict(os.environ)
    environment[PIN] = decision["base_index_canonical_sha256"]
    return environment


def verify_historical_baseline(repo, spec, site):
    return released_verifier(repo, spec, site, environment=historical_environment(repo, spec))
