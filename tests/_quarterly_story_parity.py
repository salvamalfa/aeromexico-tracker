"""Strict test consumers for the explicitly reviewed Q3 replacement publication."""

import copy
import io
import json
import math
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

from scripts.check_pages_publication import verifier_for
from src.publish import manifest as manifests
from src.publish import quarterly_story_scope as scope
from src.publish.editorial import _git
from src.publish.financial_scope import sha

PROFILE = "src.publish.quarterly_story_scope"


def industry_projection(before, after):
    """Check sums/ASK weights independently, then undo only the declared slot."""
    period = "2026Q3"
    original = before["entities"]["INDUSTRY"]
    industry = after["entities"]["INDUSTRY"]
    assert period not in original["views"]
    assert not any(r["period_id"] == period for r in original["records"])
    rows = [r for r in industry["records"] if r["period_id"] == period]
    assert len(rows) == 1, "Missing or duplicated Industry quarter"
    row = rows[0]
    inputs = []
    for entity in sorted(scope.ENTITIES - {"INDUSTRY"}):
        selected = [r for r in before["entities"][entity]["records"] if r["period_id"] == period]
        assert len(selected) == 1
        inputs.append(selected[0])
    ask = math.fsum(r["ask_km"] for r in inputs)
    assert ask > 0
    expected = {k: math.fsum(r[k] for r in inputs) for k in ("ask_km", "passengers", "rpk_km")}
    for key in ("rask_cents_per_km", "cask_cents_per_km", "cask_ex_fuel_cents_per_km", "load_factor"):
        expected[key] = math.fsum(r[key] * r["ask_km"] for r in inputs) / ask
    expected["unit_margin_cents_per_km"] = expected["rask_cents_per_km"] - expected["cask_cents_per_km"]
    for key, value in expected.items():
        assert type(row[key]) in (int, float) and math.isfinite(row[key])
        assert math.isclose(row[key], value, rel_tol=1e-12, abs_tol=1e-10), key
    assert row["load_factor_basis"] == "reported"
    assert all(r["load_factor_basis"] == "reported" for r in inputs)
    view = industry["views"][period]
    assert view["period_id"] == period and view["conclusions"] == []
    assert "vista previa" not in view["narrative"]["headline"].lower()
    keys = {k: k for k in ("rask_cents_per_km", "cask_cents_per_km", "ask_km", "load_factor", "passengers")}
    assert len(view["kpis"]) == len(keys)
    assert {k["key"] for k in view["kpis"]} == set(keys)
    for kpi in view["kpis"]:
        key = keys[kpi["key"]]
        assert math.isclose(kpi["value"], expected[key], rel_tol=1e-12, abs_tol=1e-10)
        for comparison, previous in (("qoq", "2026Q2"), ("yoy", "2025Q3")):
            prior = [r for r in original["records"] if r["period_id"] == previous]
            assert len(prior) == 1
            assert kpi[comparison]["available"] is True
            assert math.isclose(
                kpi[comparison]["raw"], expected[key] / prior[0][key] - 1, rel_tol=1e-10, abs_tol=1e-10
            )
    for comparison, previous in (("margin_qoq", "2026Q2"), ("margin_yoy", "2025Q3")):
        prior = next(r for r in original["records"] if r["period_id"] == previous)
        assert view[comparison]["available"] is True
        assert math.isclose(
            view[comparison]["raw"],
            expected["unit_margin_cents_per_km"] - prior["unit_margin_cents_per_km"],
            rel_tol=1e-10,
            abs_tol=1e-10,
        )
    assert set(row) == set(expected) | {"period_id", "period_label", "load_factor_basis"}
    assert row["period_label"] == inputs[0]["period_label"] == view["period_label"]
    restored = copy.deepcopy(after)
    block = restored["entities"]["INDUSTRY"]
    block["records"] = [r for r in block["records"] if r["period_id"] != period]
    del block["views"][period]
    assert industry["quarter_count"] == original["quarter_count"] + 1
    assert industry["last_period"] == period
    block["quarter_count"], block["last_period"] = original["quarter_count"], original["last_period"]
    assert after["metadata"]["default_period"] == period
    restored["metadata"]["default_period"] = before["metadata"]["default_period"]
    assert restored == before, "Replacement changed financial history outside Industry Q3/default"
    return before


def publication(site, repo):
    assert verifier_for(site, repo) == PROFILE
    problems = scope.verify_story(site, repo)
    assert not problems, problems
    spec = scope.anchor(repo)
    old_raw = _git(repo, "show", f"{spec['baseline_commit']}:site/publication_manifest.json")
    assert sha(old_raw) == spec["baseline_manifest_sha256"]
    old = json.loads(old_raw)
    for field, entities, period in (
        ("analysis_manifest", scope.ENTITIES, "2026Q3"),
        ("retained_analysis_manifest", scope.ENTITIES, "2026Q2"),
        ("superseded_analysis_manifest", scope.ENTITIES - {"INDUSTRY"}, "2026Q3"),
    ):
        scope.analysis_slots(spec[field], entities, period)
    assert sorted(old["analysis_manifest"], key=manifests.analysis_sort_key) == sorted(
        spec["retained_analysis_manifest"] + spec["superseded_analysis_manifest"],
        key=manifests.analysis_sort_key,
    )
    current = manifests.load_manifest(site)
    assert current["analysis_manifest"] == sorted(
        spec["retained_analysis_manifest"] + spec["analysis_manifest"], key=manifests.analysis_sort_key
    )
    assert len(current["analysis_manifest"]) == 8
    inherited = scope.preserved_files(site, repo, spec)
    for entry in spec["retained_analysis_manifest"] + spec["superseded_analysis_manifest"]:
        name = "data/v1/" + manifests.analysis_relative_path(entry).as_posix()
        pin = next(p for p in old["files"] if p["path"] == name)
        raw = _git(repo, "show", f"{spec['baseline_commit']}:site/{name}")
        assert sha(raw) == pin["sha256"] and len(raw) == pin["bytes"]
        if entry in spec["retained_analysis_manifest"]:
            assert name in inherited and (site / name).read_bytes() == raw
        else:
            replacement = next(
                e
                for e in spec["analysis_manifest"]
                if manifests.analysis_identity(e) == manifests.analysis_identity(entry)
            )
            assert replacement["version"] != entry["version"]
    before = json.loads(_git(repo, "show", f"{spec['baseline_commit']}:site/data/v1/executive.json"))
    after = json.loads((site / "data/v1/executive.json").read_bytes())
    industry_projection(before, after)
    return spec, old, before


def _record_path(repo, entry):
    path = repo / "analysis_runs/drafts"
    if "entity_key" in entry:
        path /= entry["entity_key"]
    return path / entry["period_id"] / (entry["version"] + ".json")


def missing_records(site, repo):
    spec, _, _ = publication(site, repo)
    return [
        str(path)
        for entry in spec["analysis_manifest"]
        + spec["retained_analysis_manifest"]
        + spec["superseded_analysis_manifest"]
        if not (path := _record_path(repo, entry)).is_file()
    ]


def replay_data(site, repo):
    """Rebuild the twelve data outputs from the exact retained release request."""
    from src.publish.quarterly_story_data import outputs
    from src.publish.quarterly_story_update import authority, request_inputs
    from src.publish.source_data_scope import pins

    spec, _, _ = publication(site, repo)
    path = Path(
        os.environ.get(
            "QUARTERLY_STORY_RELEASE_REQUEST",
            str(repo / "tmp/source-updates/story-release-final/request.json"),
        )
    )
    request, _, records, packages = request_inputs(path)
    identities = sorted((r["draft"]["entity_key"], r["version"], r["content_hash"]) for r in records)
    assert identities == sorted(
        (r["entity_key"], r["version"], r["content_hash"]) for r in spec["scope"]["records"]
    )
    assert authority(request, spec["scope"]) == (
        spec["authorization_sha256"],
        spec["independent_audit_sha256"],
    )
    archive = _git(repo, "archive", spec["baseline_commit"], "site/data/v1")
    with tempfile.TemporaryDirectory(prefix="parity-story-normal-data-") as folder:
        base = Path(folder)
        with tarfile.open(fileobj=io.BytesIO(archive)) as stream:
            stream.extractall(base, filter="data")
        rebuilt = outputs(request["sources"], base / "site", packages)
    expected = [p for p in spec["data_files"] if not p["path"].startswith("data/v1/analysis/")]
    assert len(rebuilt) == len(expected) == 12
    assert pins(rebuilt) == expected
    for name, raw in rebuilt.items():
        assert (site / name).read_bytes() == raw
    return rebuilt


def _new_replay(paths, repo, commit, ledger):
    """Use committed producer code, physical source workspaces and real ledger."""
    from src.publish.issuer_replay_inputs import _inventory, _relative
    from src.publish.replay_directories import materialize_directory

    archive = _git(
        repo, "archive", commit, "src", "scripts", "contracts", "config", "uv.lock", "web", ".agents"
    )
    with tempfile.TemporaryDirectory(prefix="parity-story-source-") as folder:
        base = Path(folder)
        with tarfile.open(fileobj=io.BytesIO(archive)) as stream:
            stream.extractall(base, filter="data")
        materialize_directory(repo / "analysis_runs", base / "analysis_runs")
        materialize_directory(repo / "data", base / "data")
        workspaces = set()
        for path in paths:
            record = json.loads(path.read_bytes())
            package_path = repo / "analysis_runs/evidence" / (record["draft"]["package_id"] + ".json")
            package = json.loads(package_path.read_bytes())
            for source in package["source_packages"].values():
                if "workspace" in source:
                    workspaces.add(_relative(source["workspace"], workspace=True))
        for relative in workspaces:
            source, target = repo / relative, base / relative
            inventory = _inventory(source)
            for name, identity in inventory.items():
                raw = (source / name).read_bytes()
                assert (sha(raw), len(raw)) == identity
                (target / name).parent.mkdir(parents=True, exist_ok=True)
                (target / name).write_bytes(raw)
                shutil.copystat(source / name, target / name, follow_symlinks=False)
            assert _inventory(source) == _inventory(target) == inventory
        script = """import json,sys
from pathlib import Path
from src.publish.gate import _verify_under_lock, _analysis_payload
records=[json.loads(Path(p).read_bytes()) for p in json.loads(sys.argv[1])]
entries=_verify_under_lock(records,Path(sys.argv[2]))
print(json.dumps(dict(authorized=[e[1] for e in entries],payloads=[_analysis_payload(*e) for e in entries])))
"""
        result = subprocess.run(
            [sys.executable, "-B", "-c", script, json.dumps([str(p) for p in paths]), str(ledger)],
            cwd=base,
            capture_output=True,
            text=True,
            encoding="utf-8",
            env={**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"},
        )
        if result.returncode:
            diagnostics = repo / "tmp/approval-replay-diagnostics"
            diagnostics.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", suffix=".stderr.txt", dir=diagnostics, delete=False
            ) as stream:
                stream.write(result.stderr)
            raise AssertionError("Pinned story producer refused full source/approval replay")
        return json.loads(result.stdout)


def replay(site, repo):
    from src.analysis_agent import lifecycle as flow
    from src.publish import frozen_data
    from src.publish.approval_cohorts import approval_plan
    from src.publish.records import _analysis_manifest_entry

    spec, old, _ = publication(site, repo)
    raw = (site / "publication_manifest.json").read_bytes()
    trusted = None
    for ref in ("origin/master", "HEAD"):
        if _git(repo, "show", f"{ref}:site/publication_manifest.json") == raw:
            trusted = _git(repo, "rev-parse", ref).decode().strip()
            break
    assert trusted is not None, "Commit the exact gate output before source parity replay"
    groups, _ = approval_plan(repo, spec["baseline_commit"], old)
    pairs, cohorts = [], []
    with flow.writer(flow.ROOT):
        for group in groups:
            entries = group["analysis_manifest"]
            assert entries, "An empty cohort is not an approval"
            if all(e in spec["retained_analysis_manifest"] for e in entries):
                result = frozen_data.verify_baseline_approvals(
                    [_record_path(repo, e) for e in entries],
                    group["implementation_commit"],
                    flow.ROOT,
                    include_public_payloads=True,
                )
                assert [_analysis_manifest_entry(a) for a in result["authorized"]] == entries
                assert len(result["payloads"]) == len(entries)
                pairs.extend(zip(result["authorized"], result["payloads"]))
                cohorts.append(group)
            else:
                assert entries and all(e in spec["superseded_analysis_manifest"] for e in entries)
                for entry in entries:
                    record = json.loads(_record_path(repo, entry).read_bytes())
                    state = flow.state(record)
                    assert state["state"] in {"approved", "published"}
                    assert record["content_hash"] == entry["content_hash"]
                    assert record["draft"]["evidence_fingerprint"] == entry["evidence_fingerprint"]
                    assert state["approval"]["event_hash"] == entry["approval_event"]
                    assert state["audit"]["audit_hash"] == entry["audit_hash"]
        entries = spec["analysis_manifest"]
        result = _new_replay([_record_path(repo, e) for e in entries], repo, trusted, flow.ROOT)
        assert [_analysis_manifest_entry(a) for a in result["authorized"]] == entries
        assert len(result["payloads"]) == len(entries)
        pairs.extend(zip(result["authorized"], result["payloads"]))
        cohorts.append(dict(implementation_commit=trusted, analysis_manifest=entries))
    pairs.sort(key=lambda pair: manifests.analysis_sort_key(_analysis_manifest_entry(pair[0])))
    expected = manifests.load_manifest(site)["analysis_manifest"]
    assert len(pairs) == 8 and [_analysis_manifest_entry(a) for a, _ in pairs] == expected
    for entry, (_, payload) in zip(expected, pairs):
        public = site / "data/v1" / manifests.analysis_relative_path(entry)
        assert json.loads(public.read_bytes()) == payload
    return dict(authorized=[a for a, _ in pairs], payloads=[p for _, p in pairs], cohorts=cohorts)
