"""Read-only source consumers for the explicit C-over-unserved-B composition."""

import json
import os
import tempfile
from pathlib import Path

from src.analysis_agent import lifecycle as flow
from src.publish import afac_history_contract as contract
from src.publish import afac_history_members as members
from src.publish import afac_history_scope as scope
from src.publish.afac_history_parent import parent_inventory
from src.publish.afac_history_update import authority, request_inputs

PROFILE = "src.publish.afac_history_scope"


def request_path(repo):
    return Path(os.environ.get(
        "AFAC_HISTORY_RELEASE_REQUEST",
        str(repo / "tmp/source-updates/afac-history-correction-20261104/request.json"),
    ))


def missing_inputs(repo):
    path = request_path(repo)
    if not path.is_file():
        return [str(path)]
    _, request = request_inputs(repo, path)
    try:
        parent_inventory(repo, request["parent_inputs"])
    except FileNotFoundError as error:
        return [str(error.filename)]
    return []


def replay_all(site, repo):
    """Recheck original 8/16 under602, then the exact four native replacements."""
    from tests._quarterly_story_parity import publication

    publication(site, repo)
    anchor = scope.anchor(repo)
    _, request = request_inputs(repo, request_path(repo))
    assert request["candidate_parent"] == anchor["scope"]["candidate_parent"]
    assert authority(repo, request, anchor["scope"]) == (
        anchor["authorization_sha256"], anchor["source_audit_sha256"],
    )
    with flow.writer(flow.ROOT):
        original = scope.replay_retained_approvals(
            repo, site, request["parent_inputs"], flow.ROOT,
        )
        parent, parent_raw, before, parent_spec = contract.parent_public(repo, request["candidate_parent"])
        with tempfile.TemporaryDirectory(prefix="parity-native-unserved-parent-") as temporary:
            parent_site = contract.materialize_site(Path(temporary) / "site", parent_raw, before)
            units, replacements, _ = members.replay(repo, request, parent_site, before)
    assert original["producer_code_version"] == contract.ORIGINAL_PRODUCER
    assert original["scope_sha256"] == request["candidate_parent"]["scope_sha256"]
    assert original["retained_q2_replayed"] == 4 and original["outputs_verified"] == 16
    assert units == anchor["members"]
    assert contract.pins(replacements) == anchor["scope"]["data_files"]
    assert original["authorized"] == parent["analysis_manifest"]
    payloads = []
    for entry in original["authorized"]:
        from src.publish.manifest import analysis_relative_path

        name = "data/v1/" + analysis_relative_path(entry).as_posix()
        assert (site / name).read_bytes() == before[name]
        payloads.append(json.loads(before[name]))
    names = [p["path"] for p in parent_spec["data_files"] if not p["path"].startswith("data/v1/analysis/")]
    assert len(names) == 12 and set(replacements) <= set(names)
    data = {name: replacements.get(name, before[name]) for name in names}
    for name, raw in data.items():
        assert (site / name).read_bytes() == raw, name
    return dict(
        authorized=original["authorized"], payloads=payloads,
        original_parent_replay=original, data=data,
    )
