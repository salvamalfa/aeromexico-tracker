"""Orchestration adversaries; source semantics/scope have independent physical tests."""

import copy
import hashlib
import json
import sys
from contextlib import nullcontext
from types import SimpleNamespace

import pytest

from src.publish import movements_update as update


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(json.dumps(value).encode())
    return path


@pytest.fixture
def env(tmp_path, monkeypatch):
    from src.analysis_agent import entity_adapter
    from src.publish import gate, verify

    site = tmp_path / "site"
    site.mkdir()
    write(site / "publication_manifest.json", {"baseline": True})
    write(site / "data/v1/executive.json", {"unchanged": True})
    write(site / "data/v1/flights/international/2026Q3.json", {"old": True})
    (site / "index.html").write_bytes(b"old frontend")
    contract = write(tmp_path / "contracts/web/flights.schema.json", {"type": "object"})
    profile = write(tmp_path / "tmp/profile.json", {"immutable": "source"})
    original = write(tmp_path / "tmp/original.json", {"original": True})
    records = [write(tmp_path / f"analysis_runs/drafts/{i}.json", {"draft": i}) for i in range(7)]
    target = "data/v1/flights/international/2026Q3.json"
    projection = {
        "source_binding": {
            "product": "aerocivil",
            "period": "2026M07",
            "receipt_id": "a" * 32,
            "candidate_as_of": "2026-10-21T00:00:00Z",
            "output_sha256": {"gold/a": "b" * 64},
        },
        "source_evidence": {"official_confirmation": False},
        "projection_rows": [{"operations": 347}],
        "network_outputs": {target: b'{"movements":347,"departures":null}'},
        "input_files": [str(original)],
    }
    request = {
        "schema_version": "aerocivil_movements_request_v1",
        "source_profile": {"path": str(profile), "sha256": digest(profile.read_bytes())},
        "record_paths": [str(p) for p in records],
        "authorization": None,
    }
    path = write(tmp_path / "tmp/request.json", request)
    old = {
        "analysis_manifest": [{"version": str(i)} for i in range(7)],
        "contracts": {"flights.schema.json": "oldcontract", "financial": "retained"},
    }
    source_calls, cohort_calls, snapshots = [], [], []
    scope = SimpleNamespace(
        ANCHOR="config/publish/aerocivil-movements-release.json",
        PROOF="aerocivil-movements-publication.json",
        TARGETS=[target],
        anchor=lambda repo: None,
        sha=digest,
        encoded=lambda v: json.dumps(v).encode(),
        verify_historical_baseline=lambda *args: copy.deepcopy(old),
        preserved_files=lambda *args: frozenset({"data/v1/executive.json"}),
    )

    def project(*args):
        source_calls.append(True)
        return copy.deepcopy(projection)

    def cohorts(*args):
        cohort_calls.append(True)
        return {"authorized": list(old["analysis_manifest"])}

    def snapshot(*args, **kwargs):
        snapshots.append(True)
        return {str(p): digest(p.read_bytes()) for p in records}

    monkeypatch.setitem(sys.modules, "src.publish.movements_scope", scope)
    monkeypatch.setitem(
        sys.modules, "src.publish.movements_history", SimpleNamespace(source_projection=project)
    )
    monkeypatch.setattr(update, "PATHS", SimpleNamespace(root=tmp_path))
    monkeypatch.setattr(update, "input_snapshot", snapshot)
    monkeypatch.setattr(update, "verify_approval_cohorts", cohorts)
    monkeypatch.setattr(update.manifests, "refuse_if_build_inputs_dirty", lambda: None)
    monkeypatch.setattr(update.manifests, "current_commit", lambda repo: "c" * 40)
    monkeypatch.setattr(entity_adapter, "code_version", lambda: "d" * 64)
    monkeypatch.setattr(gate.flow, "writer", lambda *args: nullcontext())
    monkeypatch.setattr(gate, "_trusted_site_commit", lambda *args: "e" * 40)
    monkeypatch.setattr(gate, "require_trusted_site_baseline", lambda *args, **kwargs: None)
    monkeypatch.setattr(gate, "WEB_DATA_V1", tmp_path / "web/public/data/v1")
    dist = tmp_path / "web/dist"
    dist.mkdir(parents=True)
    (dist / "assets").mkdir()
    (dist / "assets/new.js").write_bytes(b"new UI")
    (dist / "index.html").write_bytes(b'<script src="assets/new.js"></script>')
    monkeypatch.setattr(gate, "build_web", lambda: dist)
    monkeypatch.setattr(update.transport, "witness_remote", lambda *args: {"checked": True})
    monkeypatch.setattr(update.transport, "_git", lambda *args: ("e" * 40).encode())
    monkeypatch.setattr(verify, "_verify_site", lambda *args, **kwargs: [])
    swaps = []

    def assemble(prepared, entries, out, **kwargs):
        kwargs["validate_candidate"](prepared)
        swaps.append(copy.deepcopy(entries))
        assert (prepared / "data/v1/executive.json").read_bytes() == b'{"unchanged": true}'
        assert (prepared / target).read_bytes() == projection["network_outputs"][target]
        assert kwargs["contracts"] == {
            **old["contracts"],
            "flights.schema.json": digest(contract.read_bytes()),
        }
        return {"analysis_manifest": entries}

    monkeypatch.setattr(gate, "assemble_site", assemble)
    monkeypatch.setattr(gate, "write_receipt", lambda *args: {"manifest_sha256": "f" * 64})
    result = SimpleNamespace(**locals())
    return result


def authorize(env):
    inspected = update.inspect_movements(env.path)
    value = {
        "schema_version": "aerocivil_movements_authorization_v1",
        "status": "authorized",
        "scope": inspected["authority_scope"],
        "owner_consent": {
            "source_reference": "synthetic-fixture-parent",
            "instruction": "synthetic fixture consent",
            "received_at": "2026-10-30T19:00:00Z",
        },
    }
    raw = json.dumps(value).encode()
    auth = env.tmp_path / "analysis_runs/dashboard_updates/authorizations" / (digest(raw) + ".json")
    auth.parent.mkdir(parents=True)
    auth.write_bytes(raw)
    env.request["authorization"] = {"path": str(auth), "sha256": digest(raw)}
    write(env.path, env.request)
    spec = {**inspected["anchor"], "authorization_sha256": digest(raw)}
    anchor_path = write(env.tmp_path / env.scope.ANCHOR, spec)
    env.scope.anchor = lambda repo: json.loads(anchor_path.read_bytes())
    return spec, auth


def test_inspection_replays_source_and_cohorts_preserves_site(env):
    before = {p.relative_to(env.site): p.read_bytes() for p in env.site.rglob("*") if p.is_file()}
    result = update.inspect_movements(env.path)
    assert result["status"] == "movement_pins_inspected_not_published"
    assert len(env.source_calls) == len(env.cohort_calls) == 2
    assert result["anchor"]["source_binding"]["period"] == "2026M07"
    assert result["anchor"]["period_id"] == "2026Q3"
    assert {p.relative_to(env.site): p.read_bytes() for p in env.site.rglob("*") if p.is_file()} == before
    assert not (env.tmp_path / env.scope.ANCHOR).exists()


def test_prepare_requires_actual_authority_and_never_creates_it(env):
    with pytest.raises(ValueError, match="owner"):
        update.prepare_movements(env.path)
    assert not (env.tmp_path / "analysis_runs/dashboard_updates/authorizations").exists()


def test_publish_preserves_seven_entries_and_financial_data(env):
    authorize(env)
    result = update.publish_movements(env.path, env.site)
    assert result["manifest"]["analysis_manifest"] == env.old["analysis_manifest"]
    assert env.swaps == [env.old["analysis_manifest"]]


@pytest.mark.parametrize("mutation", ["revoked", "source", "producer", "output", "consent", "alias"])
def test_authority_rejects_wrong_release_or_revocation(env, mutation):
    spec, auth = authorize(env)
    value = json.loads(auth.read_bytes())
    if mutation == "revoked":
        value["status"] = "revoked"
    elif mutation == "source":
        value["scope"]["source_binding"]["period"] = "2026M08"
    elif mutation == "producer":
        value["scope"]["producer_code_version"] = "9" * 64
    elif mutation == "output":
        value["scope"]["network_files"][0]["sha256"] = "9" * 64
    elif mutation == "alias":
        value["scope"]["product"] = "aeromexico_financials"
    else:
        value["owner_consent"]["instruction"] = " "
    raw = json.dumps(value).encode()
    new = auth.with_name(digest(raw) + ".json")
    new.write_bytes(raw)
    env.request["authorization"] = {"path": str(new), "sha256": digest(raw)}
    spec["authorization_sha256"] = digest(raw)
    with pytest.raises(ValueError, match="revoked, incomplete"):
        update._authority(env.request, spec, env.tmp_path)


@pytest.mark.parametrize("change", ["source", "authority", "record", "request"])
def test_mutation_after_build_refuses_atomic_swap(env, monkeypatch, change):
    from src.publish import gate

    _, auth = authorize(env)

    def build():
        target = {"source": env.original, "authority": auth, "record": env.records[0], "request": env.path}[
            change
        ]
        target.write_bytes(target.read_bytes() + b" ")
        return env.dist

    monkeypatch.setattr(gate, "build_web", build)
    with pytest.raises(ValueError):
        update.publish_movements(env.path, env.site)
    assert not env.swaps


def test_mutation_inside_slow_candidate_verifier_refuses_swap(env, monkeypatch):
    from src.publish import verify

    authorize(env)

    def slow(*args, **kwargs):
        env.original.write_bytes(b"changed")
        return []

    monkeypatch.setattr(verify, "_verify_site", slow)
    with pytest.raises(ValueError, match="final swap"):
        update.publish_movements(env.path, env.site)
    assert not env.swaps


def test_publication_never_falls_back_after_scope_failure(env):
    authorize(env)
    env.scope.preserved_files = lambda *args: (_ for _ in ()).throw(ValueError("bad scope"))
    with pytest.raises(ValueError, match="bad scope"):
        update.publish_movements(env.path, env.site)
    assert not env.swaps


@pytest.mark.parametrize("mode", ["extra", "missing", "unencoded"])
def test_replay_output_scope_is_closed(env, mode):
    if mode == "extra":
        env.projection["network_outputs"]["data/v1/executive.json"] = b"financial mutation"
    elif mode == "missing":
        env.projection["network_outputs"].clear()
    else:
        env.projection["network_outputs"][env.target] = {"movements": 347}
    with pytest.raises(ValueError):
        update.inspect_movements(env.path)


def test_source_closure_path_escape_and_symlink_rejected(env):
    outside = env.tmp_path.parent / "outside-source.json"
    outside.write_bytes(b"outside")
    env.projection["input_files"] = [str(outside)]
    with pytest.raises(ValueError, match="outside"):
        update.inspect_movements(env.path)
    link = env.tmp_path / "tmp/link.json"
    link.symlink_to(env.original)
    env.projection["input_files"] = [str(link)]
    with pytest.raises(ValueError, match="symlink"):
        update.inspect_movements(env.path)


def test_other_destination_rejected_before_writing(env):
    with pytest.raises(ValueError, match="tracked site"):
        update.publish_movements(env.path, env.tmp_path / "other")
    assert not (env.tmp_path / "other").exists()


def test_revocation_discovered_by_second_cohort_replay_prevents_swap(env, monkeypatch):
    authorize(env)
    calls = []

    def cohorts(*args):
        calls.append(True)
        if len(calls) == 2:
            raise ValueError("historical approval revoked")
        return {"authorized": env.old["analysis_manifest"]}

    monkeypatch.setattr(update, "verify_approval_cohorts", cohorts)
    with pytest.raises(ValueError, match="revoked"):
        update.publish_movements(env.path, env.site)
    assert len(calls) == 2
    assert not env.swaps


def test_source_projection_changed_by_second_replay_prevents_swap(env, monkeypatch):
    authorize(env)
    calls = []

    def project(*args):
        calls.append(True)
        value = copy.deepcopy(env.projection)
        if len(calls) == 2:
            value["projection_rows"][0]["operations"] = 348
        return value

    monkeypatch.setattr(update, "_project", project)
    with pytest.raises(ValueError, match="binding"):
        update.publish_movements(env.path, env.site)
    assert not env.swaps


def test_frontend_differs_from_reviewed_pin_blocks_before_swap(env, monkeypatch):
    from src.publish import gate

    authorize(env)

    def build():
        (env.dist / "assets/new.js").write_bytes(b"unreviewed UI")
        return env.dist

    monkeypatch.setattr(gate, "build_web", build)
    with pytest.raises(ValueError, match="frontend"):
        update.publish_movements(env.path, env.site)
    assert not env.swaps


def test_empty_physical_source_closure_cannot_be_trusted(env):
    env.projection["input_files"] = []
    with pytest.raises(ValueError, match="physical evidence"):
        update.inspect_movements(env.path)


def test_source_profile_pin_cannot_be_renamed_to_another_content(env):
    env.profile.write_bytes(b'{"other":"source"}')
    with pytest.raises(ValueError, match="SHA-256"):
        update.inspect_movements(env.path)


def test_owner_authority_timezone_is_not_invented(env):
    spec, auth = authorize(env)
    value = json.loads(auth.read_bytes())
    value["owner_consent"]["received_at"] = "2026-10-30T19:00:00"
    raw = json.dumps(value).encode()
    new = auth.with_name(digest(raw) + ".json")
    new.write_bytes(raw)
    request = {**env.request, "authorization": {"path": str(new), "sha256": digest(raw)}}
    spec["authorization_sha256"] = digest(raw)
    with pytest.raises(ValueError, match="timezone"):
        update._authority(request, spec, env.tmp_path)
