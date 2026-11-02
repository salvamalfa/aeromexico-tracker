"""Adversarial tests of the new test consumer, without publication approvals."""

import copy
import json
from contextlib import nullcontext
from pathlib import Path

import pytest

from tests import _quarterly_story_parity as consumer
from tests import _site_publication_parity as parity


@pytest.fixture
def financial_projection():
    from src.dashboard.financial_periods import with_financial_default
    from src.dashboard.industry_review import build_industry_period

    # Public financial history only; no private ledger or invented approval.
    root = Path(__file__).resolve().parents[1]
    before = json.loads((root / "site/data/v1/executive.json").read_bytes())
    block = before["entities"]["INDUSTRY"]
    block["records"] = [r for r in block["records"] if r["period_id"] != "2026Q3"]
    block["views"].pop("2026Q3", None)
    block["last_period"] = block["records"][-1]["period_id"]
    block["quarter_count"] = len(block["records"])
    after = with_financial_default(build_industry_period(before, "2026Q3", review=False))
    return before, after


def test_industry_consumer_checks_the_complete_real_financial_projection(financial_projection):
    before, after = financial_projection
    snapshot = copy.deepcopy(after)
    assert consumer.industry_projection(before, after) == before
    assert after == snapshot


@pytest.mark.parametrize(
    "mutation",
    [
        "sum",
        "weighted",
        "exfuel",
        "basis",
        "margin",
        "comparative",
        "margin_comparative",
        "history",
        "peer",
        "root",
        "metadata",
        "duplicate",
        "missing",
        "extra_metric",
        "kpi",
        "nan",
    ],
)
def test_industry_consumer_rejects_resigned_semantic_changes(financial_projection, mutation):
    before, after = financial_projection
    block = after["entities"]["INDUSTRY"]
    row = next(r for r in block["records"] if r["period_id"] == "2026Q3")
    view = block["views"]["2026Q3"]
    if mutation == "sum":
        row["passengers"] += 1
    elif mutation == "weighted":
        row["load_factor"] += 0.001
    elif mutation == "exfuel":
        row["cask_ex_fuel_cents_per_km"] += 0.001
    elif mutation == "basis":
        row["load_factor_basis"] = "calculated"
    elif mutation == "margin":
        row["unit_margin_cents_per_km"] += 0.001
    elif mutation == "comparative":
        view["kpis"][0]["yoy"]["raw"] += 0.001
    elif mutation == "margin_comparative":
        view["margin_qoq"]["raw"] += 0.001
    elif mutation == "history":
        block["records"][0]["passengers"] += 1
    elif mutation == "peer":
        after["entities"]["VOLARIS"]["records"][0]["passengers"] += 1
    elif mutation == "root":
        after["records"][0]["passengers"] += 1
    elif mutation == "metadata":
        after["metadata"]["default_period"] = "2026Q2"
    elif mutation == "duplicate":
        block["records"].append(copy.deepcopy(row))
    elif mutation == "missing":
        block["records"].remove(row)
    elif mutation == "extra_metric":
        row["unreviewed_metric"] = 1
    elif mutation == "kpi":
        view["kpis"][0]["value"] += 0.001
    else:
        row["ask_km"] = float("nan")
    with pytest.raises(AssertionError):
        consumer.industry_projection(before, after)


def test_story_consumer_never_falls_back_from_a_failed_strict_verifier(tmp_path, monkeypatch):
    monkeypatch.setattr(parity, "verifier_for", lambda *args: consumer.PROFILE)
    monkeypatch.setattr(consumer.scope, "verify_story", lambda *args: ["source or scope rejected"])
    with pytest.raises(AssertionError, match="source or scope rejected"):
        parity.verify_current_publication(tmp_path, tmp_path, lambda *args: pytest.fail("fallback"))


def test_story_consumer_rejects_an_unknown_profile_before_reading_any_anchor(tmp_path, monkeypatch):
    monkeypatch.setattr(consumer, "verifier_for", lambda *args: "unknown_future_profile")
    monkeypatch.setattr(consumer.scope, "anchor", lambda *args: pytest.fail("unknown scope accepted"))
    with pytest.raises(AssertionError):
        consumer.publication(tmp_path, tmp_path)


@pytest.fixture
def replay_inputs(tmp_path, monkeypatch):
    from src.analysis_agent import lifecycle as flow
    from src.publish import approval_cohorts, frozen_data

    def entry(entity, period, version):
        return dict(
            entity_key=entity,
            period_id=period,
            version=version,
            content_hash=version,
            evidence_fingerprint=version,
            approval_event=version,
            audit_hash=version,
        )

    entities = sorted(consumer.scope.ENTITIES)
    retained = [entry(e, "2026Q2", f"old-{e}") for e in entities]
    new = [entry(e, "2026Q3", f"new-{e}") for e in entities]
    retired = [entry(e, "2026Q3", f"retired-{e}") for e in entities if e != "INDUSTRY"]
    spec = dict(
        analysis_manifest=new,
        retained_analysis_manifest=retained,
        superseded_analysis_manifest=retired,
        baseline_commit="baseline",
    )
    current = dict(analysis_manifest=sorted(retained + new, key=consumer.manifests.analysis_sort_key))
    site = tmp_path / "site"
    site.mkdir()
    (site / "publication_manifest.json").write_bytes(b"current")
    for item in retained + retired + new:
        path = consumer._record_path(tmp_path, item)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(dict(content_hash=item["content_hash"], draft=item)))
    for item in retained + new:
        path = site / "data/v1" / consumer.manifests.analysis_relative_path(item)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(dict(version=item["version"])))
    groups = [
        dict(implementation_commit="q2-code", analysis_manifest=retained),
        dict(implementation_commit="old-q3-code", analysis_manifest=retired),
    ]
    monkeypatch.setattr(consumer, "publication", lambda *args: (spec, {}, {}))
    monkeypatch.setattr(consumer, "_git", lambda *args: b"current" if args[1] == "show" else b"new-code")
    monkeypatch.setattr(consumer.manifests, "load_manifest", lambda *args: current)
    monkeypatch.setattr(approval_cohorts, "approval_plan", lambda *args: (groups, {}))
    monkeypatch.setattr(flow, "writer", lambda *args: nullcontext())
    monkeypatch.setattr(
        flow,
        "state",
        lambda record: dict(
            state="approved",
            approval=dict(event_hash=record["content_hash"]),
            audit=dict(audit_hash=record["content_hash"]),
        ),
    )
    calls = []

    def result(entries):
        return dict(authorized=entries, payloads=[dict(version=e["version"]) for e in entries])

    q2_result, new_result = result(retained), result(new)
    monkeypatch.setattr(
        frozen_data,
        "verify_baseline_approvals",
        lambda paths, code, *args, **kwargs: calls.append((code, paths)) or q2_result,
    )
    monkeypatch.setattr(
        consumer, "_new_replay", lambda paths, repo, code, ledger: calls.append((code, paths)) or new_result
    )
    return site, tmp_path, spec, current, groups, q2_result, new_result, calls


def test_story_replay_consumes_exactly_four_retained_and_four_new_records(replay_inputs):
    site, repo, spec, current, _, _, _, calls = replay_inputs
    result = consumer.replay(site, repo)
    assert result["authorized"] == current["analysis_manifest"]
    assert [code for code, _ in calls] == ["q2-code", "new-code"]
    assert [len(paths) for _, paths in calls] == [4, 4]
    consumed = {str(path) for _, paths in calls for path in paths}
    assert not consumed & {str(consumer._record_path(repo, e)) for e in spec["superseded_analysis_manifest"]}


@pytest.mark.parametrize(
    "mutation", ["extra_q2", "extra_new", "missing_q2", "missing_new", "empty", "old_changed"]
)
def test_story_replay_rejects_incomplete_extra_or_changed_history(replay_inputs, mutation):
    site, repo, spec, _, groups, old, new, _ = replay_inputs
    if mutation == "extra_q2":
        old["payloads"].append(dict(version="unapproved"))
    elif mutation == "extra_new":
        new["payloads"].append(dict(version="unapproved"))
    elif mutation == "missing_q2":
        old["payloads"].pop()
    elif mutation == "missing_new":
        new["authorized"] = new["authorized"][:-1]
    elif mutation == "empty":
        groups[0]["analysis_manifest"] = []
    else:
        path = consumer._record_path(repo, spec["superseded_analysis_manifest"][0])
        record = json.loads(path.read_bytes())
        record["content_hash"] = "changed"
        path.write_text(json.dumps(record))
    with pytest.raises(AssertionError):
        consumer.replay(site, repo)
