"""Exact new-map source adapter; historical route and analysis surfaces are preserved."""

from __future__ import annotations

import hashlib
import json

from src.config import PATHS
from src.dashboard.official_routes_contract import PUBLIC_PATH, encoded
from src.source_updates.official_routes import fingerprints
from src.source_updates.official_routes_sources import physical, replay as source_replay
from src.web_export.privacy import check_privacy

TARGETS = frozenset({PUBLIC_PATH})
CONTRACTS = frozenset({"official-routes.schema.json"})
ADDED_TARGETS = TARGETS


def _replay(profile, repo=PATHS.root):
    if set(profile) != {"schema_version", "period", "selection", "code_sha256", "dataset_version",
                        "output_sha256", "activation", "publication", "retained_approvals"} or (
        profile["schema_version"] != "official_route_profile_v1" or profile["activation"] != "none"
        or profile["publication"] != "not_authorized"
    ):
        raise ValueError("Official source profile is not a closed, inactive review package")
    if profile["code_sha256"] != fingerprints(repo):
        raise ValueError("Official source producer/reference changed after certification")
    selection_path = physical(profile["selection"], repo)
    selection = json.loads(selection_path.read_bytes())
    if profile["period"] != max(item["period"] for item in selection["afac"]):
        raise ValueError("Official profile release period differs from its AFAC source edition")
    payload, _, files = source_replay(selection, selection_path.parent)
    check_privacy(payload)
    raw = encoded(payload)
    if len(raw) > 8_000_000:
        raise ValueError("Official route payload exceeds the public privacy size budget")
    if payload["dataset_version"] != profile["dataset_version"] or hashlib.sha256(raw).hexdigest() != profile["output_sha256"]:
        raise ValueError("Official source replay differs from its prepared exact output")
    from src.publish.official_routes_approvals import retained_files

    return raw, selection, [selection_path, *files, *[repo / p for p in fingerprints(repo)],
                            *retained_files(profile, repo)]


def replay(profile, baseline):
    raw, selection, files = _replay(profile)
    return dict(
        source_binding=dict(product="official_routes", period=profile["period"],
                            receipt_id=hashlib.sha256(encoded(profile)).hexdigest()[:32],
                            candidate_as_of=selection["source_as_of"], output_sha256={"official_routes": profile["output_sha256"]}),
        projection=dict(profile=profile, dataset_version=profile["dataset_version"], payload_sha256=profile["output_sha256"]),
        input_files=sorted(set(str(p) for p in files)),
    )


def initial_bytes(name):
    if name not in ADDED_TARGETS:
        raise ValueError("Official adapter cannot create an unrelated public surface")
    return b"{}\n"


def public_outputs(before, projection):
    if set(before) != TARGETS or set(projection) != {"profile", "dataset_version", "payload_sha256"}:
        raise ValueError("Official adapter target/projection inventory changed")
    raw, _, _ = _replay(projection["profile"])
    if (projection["dataset_version"], projection["payload_sha256"]) != (
        projection["profile"]["dataset_version"], hashlib.sha256(raw).hexdigest()
    ):
        raise ValueError("Official route output differs from its exact release scope")
    return {PUBLIC_PATH: raw}
