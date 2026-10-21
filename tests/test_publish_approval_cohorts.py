"""An expanded publication retains exact, independently replayed approval cohorts."""

import copy
import hashlib
import json
import subprocess

import pytest

from src.publish import approval_cohorts as cohorts


def git(root, *args):
    return subprocess.check_output(["git", *args], cwd=root, text=True).strip()


def commit(root):
    git(root, "add", ".")
    git(root, "commit", "-qm", "test provenance")
    return git(root, "rev-parse", "HEAD")


def entry(period, char):
    return {k: period if k == "period_id" else char * 64 for k in cohorts.ANALYSIS_MANIFEST_FIELDS}


def payload_file(period, raw):
    return {
        "path": f"data/v1/analysis/{period}.json",
        "bytes": len(raw),
        "sha256": hashlib.sha256(raw).hexdigest(),
    }


@pytest.fixture
def publication(tmp_path):
    root = tmp_path
    git(root, "init", "-q")
    git(root, "config", "user.name", "Test")
    git(root, "config", "user.email", "test@example.invalid")
    (root / "code").write_text("original implementation")
    old_code = commit(root)
    old_entry, new_entry = entry("2026Q2", "a"), entry("2026Q3", "b")
    old_raw, new_raw = b'{"thesis":"old"}', b'{"thesis":"new"}'
    old_row, new_row = payload_file("2026Q2", old_raw), payload_file("2026Q3", new_raw)
    baseline = {"code_commit": old_code, "analysis_manifest": [old_entry], "files": [old_row]}
    manifest = root / "site/publication_manifest.json"
    manifest.parent.mkdir()
    raw = json.dumps(baseline).encode()
    manifest.write_bytes(raw)
    target = root / "site" / old_row["path"]
    target.parent.mkdir(parents=True)
    target.write_bytes(old_raw)
    original = commit(root)
    anchor = {
        "schema_version": "preserved_analysis_anchor_v1",
        "published_site_commit": original,
        "published_manifest_sha256": hashlib.sha256(raw).hexdigest(),
        "implementation_commit": old_code,
    }
    path = root / cohorts.ANCHOR
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(anchor))
    trusted = commit(root)
    (root / "code").write_text("new implementation")
    new_code = commit(root)
    config = {
        "schema_version": cohorts.SCHEMA,
        "cohorts": [
            {"implementation_commit": new_code, "analysis_manifest": [new_entry], "files": [new_row]}
        ],
    }
    (root / cohorts.CONFIG).write_text(json.dumps(config))
    commit(root)
    pending = {"entry": new_entry, "file": new_row, "bytes": new_raw}
    return dict(
        root=root,
        trusted=trusted,
        baseline=baseline,
        pending=pending,
        config=config,
        old_code=old_code,
        new_code=new_code,
        manifest=manifest,
    )


def expanded(p):
    baseline = copy.deepcopy(p["baseline"])
    baseline["code_commit"] = p["new_code"]
    baseline["analysis_manifest"].append(p["pending"]["entry"])
    baseline["files"].append(p["pending"]["file"])
    p["manifest"].write_text(json.dumps(baseline))
    (p["root"] / "site" / p["pending"]["file"]["path"]).write_bytes(p["pending"]["bytes"])
    return commit(p["root"]), baseline


def test_pending_cohort_and_next_publication_keep_both_verifiers(publication):
    p = publication
    plan, payloads = cohorts.approval_plan(p["root"], p["trusted"], p["baseline"], pending=p["pending"])
    assert [g["implementation_commit"] for g in plan] == [p["old_code"], p["new_code"]]
    assert len(payloads) == 2
    future, baseline = expanded(p)
    assert cohorts.approval_plan(p["root"], future, baseline) == (plan, payloads)
    # A later presentation commit must still select the original two verifiers.
    (p["root"] / "code").write_text("later presentation")
    later = commit(p["root"])
    assert cohorts.approval_plan(p["root"], later, baseline) == (plan, payloads)


@pytest.mark.parametrize(
    "field", ["version", "content_hash", "approval_event", "audit_hash", "evidence_fingerprint", "entity_key"]
)
def test_changed_approval_cannot_inherit_a_cohort(publication, field):
    p = publication
    future, baseline = expanded(p)
    config = copy.deepcopy(p["config"])
    config["cohorts"][0]["analysis_manifest"][0][field] = "c" * 64
    (p["root"] / cohorts.CONFIG).write_text(json.dumps(config))
    changed = commit(p["root"])
    with pytest.raises(ValueError):
        cohorts.approval_plan(p["root"], changed, baseline)


@pytest.mark.parametrize(
    "change", ["orphan", "overlap", "duplicate_file", "size", "bool_size", "hash", "nonancestor", "schema"]
)
def test_invalid_or_uncovered_cohort_provenance_fails_closed(publication, change):
    p = publication
    _, baseline = expanded(p)
    config = copy.deepcopy(p["config"])
    cohort = config["cohorts"][0]
    if change == "orphan":
        config["cohorts"] = []
    elif change == "overlap":
        config["cohorts"] *= 2
    elif change == "duplicate_file":
        cohort["files"] *= 2
    elif change == "size":
        cohort["files"][0]["bytes"] += 1
    elif change == "bool_size":
        cohort["files"][0]["bytes"] = True
    elif change == "hash":
        cohort["files"][0]["sha256"] = "f" * 64
    elif change == "nonancestor":
        cohort["implementation_commit"] = "f" * 40
    else:
        config["schema_version"] = "unknown"
    (p["root"] / cohorts.CONFIG).write_text(json.dumps(config))
    changed = commit(p["root"])
    with pytest.raises(ValueError):
        cohorts.approval_plan(p["root"], changed, baseline)


def test_working_changes_and_unexpected_pending_pins_are_rejected(publication):
    p = publication
    with pytest.raises(ValueError, match="provenance changed"):
        cohorts.approval_plan(p["root"], p["trusted"], p["baseline"])
    (p["root"] / cohorts.CONFIG).write_text(json.dumps(p["config"]) + " ")
    with pytest.raises(ValueError, match="provenance changed"):
        cohorts.approval_plan(p["root"], p["trusted"], p["baseline"], pending=p["pending"])
    config = copy.deepcopy(p["config"])
    config["cohorts"] = []
    (p["root"] / cohorts.CONFIG).write_text(json.dumps(config))
    commit(p["root"])
    with pytest.raises(ValueError, match="exactly one"):
        cohorts.approval_plan(p["root"], p["trusted"], p["baseline"], pending=p["pending"])


@pytest.mark.parametrize("bad", ["approval", "payload", "missing_payload", "replay_failure"])
def test_each_selected_verifier_must_replay_the_exact_authorization_and_payload(
    publication, monkeypatch, bad
):
    from src.publish import frozen_data

    p = publication
    future, baseline = expanded(p)
    paths = []
    for selected in baseline["analysis_manifest"]:
        path = p["root"] / (selected["period_id"] + ".json")
        path.write_text(
            json.dumps({"draft": {"period_id": selected["period_id"]}, "version": selected["version"]})
        )
        paths.append(path)
    calls = []

    def replay(selected, code, ledger, **kwargs):
        calls.append(code)
        index = 0 if code == p["old_code"] else 1
        result = {
            "authorized": [copy.deepcopy(baseline["analysis_manifest"][index])],
            "payloads": [{"thesis": "old" if index == 0 else "new"}],
        }
        if index:
            if bad == "approval":
                result["authorized"][0]["approval_event"] = "f" * 64
            elif bad == "payload":
                result["payloads"][0]["thesis"] = "changed"
            elif bad == "missing_payload":
                result["payloads"] = []
            else:
                raise ValueError("full ledger replay refused")
        return result

    monkeypatch.setattr(frozen_data, "verify_baseline_approvals", replay)
    with pytest.raises(ValueError):
        cohorts.verify_approval_cohorts(paths, p["root"], future, baseline, p["root"] / "ledger")
    assert calls == [p["old_code"], p["new_code"]]


@pytest.mark.local_data
def test_final_publication_can_revalidate_all_five_theses_for_the_next_gate(request):
    from pathlib import Path
    from src.analysis_agent import lifecycle
    from src.publish.manifest import analysis_identity

    root = Path(__file__).resolve().parents[1]
    baseline = json.loads((root / "site/publication_manifest.json").read_bytes())
    entries = baseline["analysis_manifest"]
    if not any(analysis_identity(e) == ("AEROMEXICO", "2026Q3") for e in entries):
        if request.config.getoption("--require-local-data"):
            pytest.fail("The required five-thesis quarterly publication is missing")
        pytest.skip("The quarterly publication has not been assembled in this checkout")
    paths = []
    for selected in entries:
        path = root / "analysis_runs/drafts"
        if "entity_key" in selected:
            path /= selected["entity_key"]
        paths.append(path / selected["period_id"] / f"{selected['version']}.json")
    trusted = git(root, "rev-parse", "HEAD")
    result = cohorts.verify_approval_cohorts(paths, root, trusted, baseline, lifecycle.ROOT)
    assert len(result["cohorts"]) == 2
    assert len(result["authorized"]) == len(result["payloads"]) == len(entries) == 5
    assert [cohorts._analysis_manifest_entry(a) for a in result["authorized"]] == entries
