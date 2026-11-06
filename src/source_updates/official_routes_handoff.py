"""Opt-in monthly map consumer; preparation never substitutes for release authority."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

PRODUCTS = frozenset({"afac_margins", "bts_segments"})
PUBLIC_PATH = "data/v1/official-routes.json"
CODE = [
    "src/source_updates/official_routes_consumer.py",
    "src/source_updates/official_routes_handoff.py",
    "src/source_updates/official_routes.py",
    "src/source_updates/official_routes_sources.py",
    "src/dashboard/official_routes.py",
    "src/publish/official_routes_projection.py",
]


def reference(ref):
    path = Path(ref["path"])
    if (
        not path.is_absolute()
        or path.resolve() != path
        or not path.is_file()
        or any(p.is_symlink() for p in (path, *path.parents))
        or hashlib.sha256(path.read_bytes()).hexdigest() != ref["sha256"]
    ):
        raise ValueError("Official consumer evidence changed or is not a physical exact reference")
    return path


def selected(source):
    if source is None or source.get("source_binding", {}).get("item", {}).get("product") not in PRODUCTS:
        return False
    ref = source.get("calendar_snapshot")
    if ref is None:
        return False
    calendar = json.loads(reference(ref).read_bytes())
    if "official_routes" not in calendar.get("consumers", []):
        return False
    if (
        calendar.get("coordinator_id") != "airlines-tracker-source-calendar"
        or calendar.get("activation_authorized") is not True
        or not calendar.get("automation_id")
        or "afac_margins" not in calendar.get("conditional_products", [])
        or not calendar.get("run_id")
        or not calendar.get("continuation")
    ):
        raise ValueError("Official consumer requires an explicitly reconciled calendar continuation")
    return True


def same_mode(prior, current):
    if prior and selected(prior) != selected(current):
        raise ValueError("Consumer selection changed: use a NEW versioned outbox/run; retain the old ledger")


def same_originals(prior, current):
    if not selected(current) or prior is None:
        return True
    old_item, old_hashes = _source_hashes(prior)
    item, hashes = _source_hashes(current)
    return (old_item["period"], old_hashes) == (item["period"], hashes)


def _source_hashes(source):
    """Re-read exact checked native outputs, including both AFAC source roles."""
    from scripts.source_update_monthly_handoff import native_item, publication_source_hashes

    item, checked = native_item(source["source_binding"]["item"]), source["checked"]
    if checked.get("status") != "checks_passed":
        raise ValueError("Official consumer requires native source readiness, not an assessment")
    for name, expected in checked["output_sha256"].items():
        if name.startswith("gold/fact_"):
            reference(
                {"path": str(Path(item["workspace"]) / "data" / (name + ".parquet")), "sha256": expected}
            )
    hashes = publication_source_hashes(item, checked)
    if not hashes:
        raise ValueError("Native source has no verified original hashes")
    return item, hashes


def replay_profile(source, profile, root):
    from src.dashboard.official_routes_contract import encoded
    from src.publish.official_routes_projection import _replay

    if not selected(source):
        raise ValueError("Official source consumer was not explicitly selected")
    raw, selection, _ = _replay(profile, repo=root)
    item, hashes = _source_hashes(source)
    role = "afac" if item["product"] == "afac_margins" else "bts"
    entries = [entry for entry in selection[role] if entry["period"] == item["period"]]
    if len(entries) != 1:
        raise ValueError("Official selection does not contain this exact native source edition")
    roles = ("routes", "carriers") if role == "afac" else ("archive",)
    if {entries[0][key]["sha256"] for key in roles} != hashes:
        raise ValueError("Official profile must consume the exact checked original source hashes")
    payload = json.loads(raw)
    binding = dict(
        product="official_routes",
        period=profile["period"],
        receipt_id=hashlib.sha256(encoded(profile)).hexdigest()[:32],
        candidate_as_of=selection["source_as_of"],
        output_sha256={"official_routes": profile["output_sha256"]},
    )
    return raw, payload, binding


def verify_release(job, source, root):
    from src.publish.source_data_scope import anchor, pins, verify_source_data
    from src.publish.source_data_update import authority

    item = source["source_binding"]["item"]
    if (
        job["stage"] != "dashboard"
        or job["release_kind"] != "source_data"
        or job["entity"] is not None
        or job["period"] != item["period"]
    ):
        raise ValueError("Official release must bind the exact monthly source-data job")
    spec = anchor(root)
    if spec["product"] != "official_routes" or spec.get("additional_sources"):
        raise ValueError("Official consumer requires the sole approved official_routes release")
    profile = spec["projection"]["profile"]
    raw, payload, binding = replay_profile(source, profile, root)
    if (
        spec["source_binding"] != binding
        or spec["data_files"] != pins({PUBLIC_PATH: raw})
        or spec["projection"]
        != dict(
            profile=profile,
            dataset_version=payload["dataset_version"],
            payload_sha256=hashlib.sha256(raw).hexdigest(),
        )
    ):
        raise ValueError("Approved official release differs from its exact dataset/profile/coverage pins")
    consent = "analysis_runs/dashboard_updates/authorizations/" + spec["authorization_sha256"] + ".json"
    authority({"authorization": {"path": consent, "sha256": spec["authorization_sha256"]}}, spec, root)
    problems = verify_source_data(root / "site", root)
    if problems:
        raise ValueError(f"Official release failed its real source-data gate: {problems[:3]}")


def verify_nochange(source, profile_path, root):
    """Exact official bytes and trusted served baseline; never use a legacy flight map."""
    from src.publish.source_data_update import physical_path, verify_no_visual_change

    profile_path = physical_path(profile_path, root)
    profile = json.loads(profile_path.read_bytes())
    raw, payload, binding = replay_profile(source, profile, root)
    observed = verify_no_visual_change(profile_path, binding, site=root / "site")
    if observed.get("status") != "no_visual_change" or observed.get("data_files") != [
        {"path": PUBLIC_PATH, "sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)}
    ]:
        raise ValueError("Official unchanged proof does not pin the complete official dataset")
    return {
        **observed,
        "dataset_version": payload["dataset_version"],
        "coverage": [
            {
                k: network[k]
                for k in (
                    "period_id",
                    "scope",
                    "carrier_keys",
                    "expected_months",
                    "observed_months",
                    "availability",
                )
            }
            for network in payload["networks"]
        ],
    }
