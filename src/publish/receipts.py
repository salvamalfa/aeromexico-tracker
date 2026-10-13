"""Paired local generation receipts and legacy lifecycle compatibility proofs."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.analysis_agent import lifecycle as flow

from . import manifest as manifest_mod
from .records import PublicationRefused


def _pair_paths(store: Path, receipt: dict[str, Any]) -> tuple[Path, Path]:
    key = manifest_mod.manifest_hash(receipt)
    return store / (key + ".intent.json"), store / (key + ".published.json")


def _check_pair(store: Path, receipt: dict[str, Any]) -> None:
    intent, published = _pair_paths(store, receipt)
    if published.exists() and not intent.exists():
        raise PublicationRefused(f"Published receipt lacks its matching intent: {published}")
    if intent.exists() and json.loads(intent.read_bytes()) != receipt:
        raise PublicationRefused(f"Receipt intent does not match its canonical identity: {intent}")
    if published.exists():
        completed = json.loads(published.read_bytes())
        if (
            not isinstance(completed.get("published_at"), str)
            or {key: value for key, value in completed.items() if key != "published_at"} != receipt
        ):
            raise PublicationRefused(f"Published receipt does not match its intent: {published}")


def _write_pair(store: Path, receipt: dict[str, Any]) -> None:
    intent, published = _pair_paths(store, receipt)
    # The canonical intent always exists before the completion marker. A
    # retry may finish an intact intent, but cannot repair an orphan silently.
    if not intent.exists():
        flow.atomic_json(intent, receipt)
    if not published.exists():
        flow.atomic_json(published, receipt | {"published_at": datetime.now(timezone.utc).isoformat()})


def write_receipt(
    manifest: dict[str, Any], authorized: list[dict[str, Any]], out_dir: Path, *, root: Path, store: Path
) -> dict[str, Any]:
    """Keep normal site-directory receipts and paired manifest-file proofs."""
    target = Path(out_dir).resolve() / manifest_mod.MANIFEST_NAME
    target_bytes = target.read_bytes()
    if json.loads(target_bytes) != manifest:
        raise PublicationRefused("Receipt target does not match the generated site manifest")
    # The unchanged lifecycle reader zips these arrays. Their association
    # must survive hash sorting, including legacy Aeroméxico records.
    pairs = sorted((entry["version"], entry["approval_event"]) for entry in authorized)
    receipt = {
        "manifest_sha256": manifest_mod.manifest_hash(manifest),
        "output": str(Path(out_dir).resolve()),
        "code_commit": manifest["code_commit"],
        "periods": sorted(entry["period_id"] for entry in authorized),
        "versions": [version for version, _ in pairs],
        "approval_events": [approval for _, approval in pairs],
    }
    identities = [
        {
            "entity_key": manifest_mod.analysis_identity(entry)[0],
            "period_id": entry["period_id"],
            "version": entry["version"],
            "approval_event": entry["approval_event"],
        }
        for entry in sorted(authorized, key=manifest_mod.analysis_sort_key)
    ]
    if any("entity_key" in entry for entry in authorized):
        receipt["analysis_identities"] = identities
    # The legacy field name html_sha256 hashes this generated manifest file;
    # the provenance explicitly identifies local consumption, not a deploy.
    proof = receipt | {
        "output": str(target),
        "html_sha256": hashlib.sha256(target_bytes).hexdigest(),
        "receipt_type": "gate_site_manifest",
        "proof_scope": "local_generated_site",
        "analysis_identities": identities,
    }
    destinations = [(Path(store), receipt), (Path(root) / "publications", proof)]
    for destination, payload in destinations:
        _check_pair(destination, payload)
    for destination, payload in destinations:
        _write_pair(destination, payload)
    return receipt
