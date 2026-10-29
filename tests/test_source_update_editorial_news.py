"""Synthetic editorial contracts; the September native readings are checked separately."""

import copy
import json
import shutil
from uuid import uuid4

import pytest

from src.pipeline.offline import block_network
from src.source_updates import editorial_news as subject
from src.source_updates import round_tasks
from src.source_updates.catalog import ROOT, plan


@pytest.fixture
def workspace():
    root = ROOT / "tmp/source-updates" / ("pytest-editorial-" + uuid4().hex)
    yield root
    if root.exists():
        shutil.rmtree(root)


def payload():
    source = dict(
        url="https://publisher.example/release?utm_source=sample",
        publisher="Synthetic publisher",
        title="Synthetic route announcement",
        published_on="2026-09-08",
        observed_at="2026-10-28T23:00:00Z",
        method="native_web",
        source_kind="official",
        publisher_page_read=True,
        evidence_note="Synthetic fixture, not an actual publisher reading.",
        event_date="2027-03-28",
        event_end_date=None,
    )
    event = dict(
        event_key="synthetic-new-route-2027",
        title="Synthetic new route",
        summary="A route was announced for 2027. Synthetic contract fixture.",
        category="route",
        companies=["Aeroméxico"],
        impact_note="Synthetic capacity impact for this fixture.",
        event_date="2027-03-28",
        event_end_date=None,
        sources=[source],
    )
    return dict(
        schema="editorial_news_review_v1",
        period="2026M09",
        as_of="2026-10-29T00:00:00Z",
        reviewer="Synthetic contract fixture",
        searches=[
            dict(
                query="Synthetic September query",
                checked_at="2026-10-28T23:10:00Z",
                method="native_web",
                scope_note="Synthetic month scope",
                outcome="completed",
            )
        ],
        events=[event],
        exclusions=[],
        empty_selection_reason=None,
    )


def test_one_calendar_plan_keeps_editorial_task_and_optional_discovery_visible():
    result = plan("combined", "2026-10-29T00:00:00Z", "2026Q3")
    assert result["calendar_count"] == 1
    rows = result["calendar_tasks"]
    assert sum(r.get("id") == "editorial_news" for r in rows) == 1
    assert next(r for r in rows if r["id"] == "editorial_news")["period"] == "2026M09"
    assert {r["status"] for r in rows if r["id"] in {"rss", "gdelt"}} == {"optional_editorial_discovery"}
    assert result["network_requests"] == 0 and result["activation"] == "none"


def test_event_dedup_preserves_different_publisher_days_and_chronological_observations():
    value = payload()
    duplicate = copy.deepcopy(value["events"][0])
    source = duplicate["sources"][0]
    source.update(
        url="https://news.example/another-article",
        source_kind="journalism",
        published_on="2026-09-07",
        observed_at="2026-10-28T17:30:00-06:00",
    )
    value["events"].extend([duplicate, copy.deepcopy(duplicate)])
    before = copy.deepcopy(value)
    candidates, result = subject.prepare(value)
    assert value == before and result["events"] == 1
    assert result["source_observations"] == 2 and result["exact_contributions_deduplicated"] == 1
    row = candidates["records"][0]
    assert row["published_at"] == "2026-09-08" and row["first_reported_on"] == "2026-09-07"
    assert row["event_date"] == "2027-03-28" and candidates["period"] == "2026M09"
    assert row["first_captured_at"] == "2026-10-28T23:00:00Z"
    assert row["verified_at"] == "2026-10-28T17:30:00-06:00"
    assert row["source"]["sha256"] == subject.sha(subject.encoded(row["publisher_observations"][0]))
    assert all(s["original_page_sha256"] is None for s in row["publisher_observations"])
    assert row["source"]["json_pointer"] == "/records/0/publisher_observations/0"
    assert row["review_status"] == "candidate_unapproved" and not result["ready_for_publication"]


@pytest.mark.parametrize(
    "attack",
    [
        "wrong_month",
        "unread_publisher",
        "rumor",
        "promotion",
        "blank_impact",
        "future_read",
        "future_search",
        "approval",
        "private_url",
        "ipv6_loopback",
        "unbound_event",
        "conflicting_event",
        "conflicting_article",
    ],
)
def test_unverified_or_inconsistent_editorial_records_never_become_candidates(attack):
    value = payload()
    row, source = value["events"][0], value["events"][0]["sources"][0]
    if attack == "wrong_month":
        source["published_on"] = "2026-10-01"
    elif attack == "unread_publisher":
        source["publisher_page_read"] = False
    elif attack in {"rumor", "promotion"}:
        row["category"] = attack
    elif attack == "blank_impact":
        row["impact_note"] = "  "
    elif attack == "future_read":
        source["observed_at"] = "2026-10-30T00:00:00Z"
    elif attack == "future_search":
        value["searches"][0]["checked_at"] = "2026-10-30T00:00:00Z"
    elif attack == "approval":
        value["approval_granted"] = True
    elif attack == "private_url":
        source["url"] = "https://127.0.0.1/source"
    elif attack == "ipv6_loopback":
        source["url"] = "https://[::ffff:127.0.0.1]/publisher"
    elif attack == "unbound_event":
        source["event_date"] = None
    elif attack == "conflicting_event":
        other = copy.deepcopy(row)
        other["summary"] = "A contradictory selection"
        value["events"].append(other)
    else:
        other = copy.deepcopy(row)
        other["event_key"] = "another-event"
        value["events"].append(other)
    with pytest.raises(ValueError):
        subject.prepare(value)


def test_empty_selection_is_a_scoped_review_not_no_news_or_an_invented_quota():
    value = payload()
    value["events"] = []
    with pytest.raises(ValueError):
        subject.prepare(value)
    value["empty_selection_reason"] = "No relevant selection in this bounded synthetic review."
    candidate, result = subject.prepare(value)
    assert candidate["records"] == [] and result["selection_outcome"] == "reviewed_no_relevant_selection"
    assert "not exhaustive" in result["coverage"] and result["editorial_approval_required"]
    value["searches"][0]["outcome"] = "access_failed"
    with pytest.raises(ValueError):
        subject.prepare(value)
    value["searches"][0]["outcome"] = "completed"
    value["exclusions"] = [
        dict(
            url="https://publisher.example/unavailable", reason="Access failed", state="pending_verification"
        )
    ]
    with pytest.raises(ValueError):
        subject.prepare(value)
    value["exclusions"] = []
    value["searches"][0]["method"] = "rss"
    with pytest.raises(ValueError):
        subject.prepare(value)
    value["searches"] = []
    with pytest.raises(ValueError):
        subject.prepare(value)


def test_real_files_replay_exactly_without_network_and_reject_input_output_authority_or_code_drift(
    workspace, monkeypatch
):
    with block_network():
        result = subject.run(workspace, payload())
        assert result["status"] == "planned_not_written" and not workspace.exists()
        accepted = subject.run(workspace, payload(), execute=True)
        assert accepted["status"] == "checks_passed"
        snapshot = {p.name: p.read_bytes() for p in workspace.iterdir()}
        assert subject.run(workspace, check=True)["receipt_sha256"]
        assert snapshot == {p.name: p.read_bytes() for p in workspace.iterdir()}
    with pytest.raises(ValueError):
        subject.run(workspace, payload(), execute=True)
    with pytest.raises(ValueError):
        subject.run(workspace, payload(), check=True)
    for name in ("review-input.json", "candidates.json", "receipt.json"):
        file = workspace / name
        original = file.read_bytes()
        if name == "receipt.json":
            tampered = json.loads(original)
            tampered["publication"] = "forged_approval"
            file.write_bytes(subject.encoded(tampered))
        else:
            file.write_bytes(original + b" ")
        with pytest.raises(ValueError):
            subject.run(workspace, check=True)
        file.write_bytes(original)
    (workspace / ".source-update.lock").write_text("synthetic active writer")
    with pytest.raises(ValueError):
        subject.run(workspace, check=True)
    (workspace / ".source-update.lock").unlink()
    receipt = workspace / "receipt.json"
    receipt.write_bytes(receipt.read_bytes() + b" ")
    with pytest.raises(ValueError):
        subject.run(workspace, check=True)
    receipt.write_bytes(snapshot["receipt.json"])
    actual = subject.fingerprints
    monkeypatch.setattr(subject, "fingerprints", lambda: {**actual(), "changed": "a" * 64})
    with pytest.raises(ValueError):
        subject.run(workspace, check=True)


def test_selected_candidate_receipt_is_bound_to_the_same_month_and_cutoff(workspace):
    subject.run(workspace, payload(), execute=True)
    binding = dict(
        workspace=str(workspace), receipt_sha256=subject.sha((workspace / "receipt.json").read_bytes())
    )
    recipe = dict(
        round="combined",
        monthly_period="2026M09",
        as_of="2026-10-29T01:00:00Z",
        items=[],
        editorial_news=binding,
    )
    assert round_tasks.editorial_result(recipe)["status"] == "checks_passed"
    receipt = workspace / "receipt.json"
    original = receipt.read_bytes()
    receipt.write_bytes(original + b" ")
    assert round_tasks.editorial_result(recipe)["status"] == "blocked"
    receipt.write_bytes(original)
    assert round_tasks.editorial_result({**recipe, "monthly_period": "2026M08"})["status"] == "blocked"
    assert round_tasks.editorial_result({**recipe, "as_of": "2026-10-28T23:30:00Z"})["status"] == "blocked"
    assert (
        round_tasks.editorial_result({**recipe, "editorial_news": {**binding, "receipt_sha256": "a" * 64}})[
            "status"
        ]
        == "blocked"
    )
    with pytest.raises(ValueError):
        round_tasks.binding_preflight({**recipe, "items": [{"id": "editorial_news"}]})


def test_same_month_semantic_revision_keeps_prior_candidate_immutable(workspace):
    original = workspace / "prior"
    current = workspace / "current"
    subject.run(original, payload(), execute=True)
    prior = {p.name: p.read_bytes() for p in original.iterdir()}
    value = payload()
    value["events"][0]["summary"] = "Changed synthetic summary, never an approval."
    result = subject.run(current, value, execute=True, baseline=original / "candidates.json")
    assert result["revisions"]["changed"] == 1 and result["revisions"]["added"] == 0
    assert prior == {p.name: p.read_bytes() for p in original.iterdir()}
    assert subject.run(current, check=True)["revisions"] == result["revisions"]
