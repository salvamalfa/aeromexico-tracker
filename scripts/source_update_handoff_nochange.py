"""Physical, replayed no-change checks for product outbox receipts."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


def reference(value):
    path = Path(value["path"])
    if not path.is_absolute() or path.resolve() != path or not path.is_file() or path.is_symlink():
        raise ValueError("No-change proof requires an exact regular evidence file")
    if hashlib.sha256(path.read_bytes()).hexdigest() != value["sha256"]:
        raise ValueError("No-change evidence bytes differ from their reference")
    return path


def verify(job: dict, source: dict, result: dict, expected_binding: dict, root: Path):
    """A no-op preserves the exact old approval; it never certifies a new thesis."""
    proof = json.loads(reference(result["equivalence_proof"]).read_bytes())
    expected_status = "no_material_analysis_change" if job["stage"] == "analysis" else "no_visual_change"
    if result["status"] != expected_status:
        raise ValueError("No-change receipt has the wrong stage")
    if job["stage"] == "dashboard" and job.get("release_kind") == "source_data":
        from src.publish.source_data_update import verify_no_visual_change

        observed = verify_no_visual_change(
            reference(result["source_profile"]), expected_binding, site=root / "site"
        )
        if observed.get("status") != "no_visual_change":
            raise ValueError("Selective source projection did not prove unchanged visible data")
    elif job["entity"] == "AEROMEXICO":
        from scripts.published_am_equivalence import verify as verify_am

        observed = verify_am(
            source["source_binding"]["item"],
            expected_binding,
            reference(result["record"]),
            site=root / "site",
        )
        key = "analysis_status" if job["stage"] == "analysis" else "dashboard_status"
        if observed.get(key) != expected_status:
            raise ValueError("Aeromexico equivalence did not prove this no-change stage")
    else:
        if job["stage"] != "dashboard" or job["release_kind"] != "data":
            raise ValueError("Issuer narrative changes need the complete analysis lifecycle")
        from src.publish.issuer_update import verify_no_visual_change

        observed = verify_no_visual_change(reference(result["package"]), expected_binding, site=root / "site")
        if observed.get("status") != "no_visual_change":
            raise ValueError("Issuer projection did not prove unchanged visible data")
    if observed != proof:
        raise ValueError("No-change receipt differs from the physical equivalence replay")
