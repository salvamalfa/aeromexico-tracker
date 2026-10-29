"""Policy/physical-receipt contracts, synthetic sources explicitly not live extraction."""

import copy
import hashlib
import json
import shutil
from pathlib import Path
from uuid import uuid4

import pytest

from src.source_updates import closed_editions as policy
from src.source_updates import global_readiness as global_gate
from src.source_updates.catalog import ROOT
from src.source_updates.manual_recovery import plan as fallback


@pytest.fixture(params=list(policy.SCOPES))
def item(request):
    product, adapter, period = policy.SCOPES[request.param]
    return dict(
        id=product,
        product=product,
        adapter=adapter,
        period=period,
        candidate_as_of="2026-10-28T15:00:00Z",
        availability={"source_scope": request.param},
    )


def proof(item, **kwargs):
    return policy.evidence(
        item,
        kwargs.pop("cutoff", "2026-11-17T18:00:00Z"),
        kwargs.pop("observed", "2026-10-27"),
        precision="day",
        source_url="https://www.sec.gov/reviewed.htm",
        **kwargs,
    )


def test_reuse_preserves_old_observation_and_never_proclaims_latest(item):
    before = copy.deepcopy(item)
    evidence = proof(item)
    assert item == before
    assert evidence["observed_at_or_day"] == "2026-10-27"
    assert evidence["observation_precision"] == "day"
    assert evidence["accepted_for_requested_period"]
    assert not evidence["source_observation_current_for_round"]
    assert evidence["revision_check"] == dict(
        status="not_checked", checked_at=None, latest_edition_verified=False
    )
    assert evidence["uncertainty"]
    result = dict(
        status="checks_passed",
        latest_source_availability_verified=False,
        source_availability_evidence={"validated_closed_edition": evidence},
    )
    assert policy.accepted(item, result)
    for mutation in ({"period": "2026M10"}, {"product": "gdelt"}, {"adapter": "unsupported"}):
        assert not policy.accepted({**item, **mutation}, result)
    assert not policy.accepted(item, {**result, "status": "blocked"})


def test_new_period_open_or_future_observation_and_known_revision_block(item):
    for mutation in ({"period": "2026M10"}, {"product": "rss"}):
        with pytest.raises(ValueError):
            proof({**item, **mutation})
    for observed in ("2026-09-30", "2026-11-18"):
        with pytest.raises(ValueError):
            proof(item, observed=observed)
    with pytest.raises(ValueError):
        policy.evidence(
            item,
            "2026-10-28T15:00:00Z",
            "2026-10-28T15:01:00Z",
            precision="timestamp",
            source_url="https://www.sec.gov/reviewed.htm",
        )
    item["availability"]["known_new_edition"] = "Official correction detected, not validated"
    with pytest.raises(ValueError, match="new edition"):
        proof(item)
    with pytest.raises(ValueError, match="new edition"):
        policy.binding_fields(item["availability"], {"source_scope"})


@pytest.fixture
def observation():
    root = ROOT / "tmp/source-updates" / ("pytest-revision-" + uuid4().hex)
    (root / "receipts/failures").mkdir(parents=True)
    data = b"explicit synthetic failed response, not source data"
    (root / "receipts/failures/response.bin").write_bytes(data)
    failed = dict(
        file="receipts/failures/response.bin",
        sha256=hashlib.sha256(data).hexdigest(),
        bytes=len(data),
        eligible_as_source_data=False,
    )
    receipt = dict(
        mode="collection",
        run_id="a" * 32,
        started_at="2026-10-29T13:00:00Z",
        finished_at="2026-10-29T13:01:00Z",
        activation="none",
        publication="not_authorized",
        status="incomplete",
        items=[
            dict(
                id="target",
                product="gap_traffic",
                requested_period="2026M09",
                source_url="https://www.sec.gov/reviewed.htm",
                status="access_or_payload_failed",
                http_status=503,
                error_type="RetryableHttpStatusError",
                failed_response=failed,
            )
        ],
    )
    path = root / ("receipts/collection-" + "a" * 32 + ".json")
    path.write_text(json.dumps(receipt))
    yield root, receipt, path
    shutil.rmtree(root)


def test_failed_novelty_check_is_separate_and_physical_evidence_cannot_be_forged(observation):
    root, receipt, path = observation
    scope = "gap_official_manual_target_v1"
    item = dict(
        product="gap_traffic",
        adapter="airport_group",
        period="2026M09",
        candidate_as_of="2026-10-28T15:00:00Z",
        availability=dict(
            source_scope=scope, revision_check=dict(workspace=str(root), run_id="a" * 32, item_id="target")
        ),
    )
    evidence = proof(item)
    assert evidence["revision_check"]["status"] == "failed"
    assert evidence["revision_check"]["checked_at"] == receipt["finished_at"]
    assert evidence["revision_check"]["http_status"] == 503
    assert evidence["observed_at_or_day"] == "2026-10-27"
    for update in ({"requested_period": "2026M10"}, {"source_url": "https://www.sec.gov/different.htm"}):
        changed = copy.deepcopy(receipt)
        changed["items"][0].update(update)
        path.write_text(json.dumps(changed))
        with pytest.raises(ValueError):
            proof(item)
    path.write_text(json.dumps(receipt))
    (root / "receipts/failures/response.bin").write_bytes(b"tampered")
    with pytest.raises(ValueError, match="changed"):
        proof(item)


def test_changed_original_blocks_but_reconstruction_cannot_claim_binary_equivalence(observation):
    root, receipt, path = observation
    raw = b"synthetic newly observed original"
    source = root / "data/bronze/document.htm"
    source.parent.mkdir(parents=True)
    source.write_bytes(raw)
    sha = hashlib.sha256(raw).hexdigest()
    row = receipt["items"][0]
    row.update(
        status="collected_unvalidated",
        http_status=200,
        source_file="document.htm",
        sha256=sha,
        bytes=len(raw),
    )
    record = dict(
        download_method="httpx",
        source_url=row["source_url"],
        sha256=sha,
        bytes=len(raw),
        http_status=200,
        downloaded_at="2026-10-29T13:00:30Z",
    )
    Path(str(source) + ".meta.json").write_text(json.dumps(record))
    path.write_text(json.dumps(receipt))
    item = dict(
        product="gap_traffic",
        adapter="airport_group",
        period="2026M09",
        candidate_as_of="2026-10-28T15:00:00Z",
        availability=dict(
            source_scope="gap_official_manual_target_v1",
            revision_check=dict(workspace=str(root), run_id="a" * 32, item_id="target"),
        ),
    )
    assert proof(item, original_sha=sha)["revision_check"]["status"] == "same_document_bytes"
    with pytest.raises(ValueError, match="Changed official document"):
        proof(item, original_sha="b" * 64)
    assert proof(item)["revision_check"]["status"] == "original_not_equated_to_derivative"
    record["download_method"] = "manual"
    Path(str(source) + ".meta.json").write_text(json.dumps(record))
    with pytest.raises(ValueError, match="manual import"):
        proof(item)


def test_global_keeps_missing_products_required_and_reuse_warning_visible():
    task = dict(
        id="gap",
        product="gap_traffic",
        adapter="airport_group",
        period="2026M09",
        cadence="monthly",
        used=True,
        depends_on=[],
        workspace="tmp/source-updates/contract-only",
        receipt_id="a" * 32,
        candidate_as_of="2026-10-28T15:00:00Z",
        availability={"source_scope": "gap_official_manual_target_v1"},
    )
    # evaluate is a pure policy contract; this synthetic result is not source certification.
    recipe = dict(
        version=1,
        round="monthly",
        as_of="2026-11-17T18:00:00Z",
        monthly_period="2026M09",
        quarterly_period="2026Q3",
        items=[{k: v for k, v in task.items() if k != "availability"}],
        releases=[],
    )
    result = dict(
        status="checks_passed",
        latest_source_availability_verified=False,
        source_availability_evidence={"validated_closed_edition": proof(task)},
    )
    output = global_gate.evaluate(recipe, {"gap": result})
    assert len(global_gate.REQUIRED["monthly"]) + len(global_gate.REQUIRED["quarterly"]) == 21
    assert "monthly:afac_airports:missing" in output["blockers"]
    assert "monthly:gdelt:missing" not in output["blockers"]
    assert "monthly:editorial_news:not_verified" in output["blockers"]
    assert not output["news_task"]["prepared"]
    assert "gap:current_source_availability_not_verified" not in output["calendar_blockers"]
    assert "gap:closed_edition_latest_revision_not_certified" in output["coverage_warnings"]
    assert not output["ready_for_calendar_incorporation"] and not output["ready_for_automatic_execution"]
    assert output["activation"] == "none" and output["publication"] == "not_authorized"


def test_manual_fallback_is_only_an_explicit_handoff_and_preserves_failure():
    item = dict(
        product="afac_airports",
        period="2026M09",
        id="airports",
        url="https://www.gob.mx/afac/acciones-y-programas/estadisticas-280404",
    )
    failure = dict(http_status=403, status="access_or_payload_failed")
    result = fallback(item, failure, "a" * 32)
    assert result["official_url"] == item["url"] and result["programmatic_http_status"] == 403
    assert result["status"] == "pending_official_browser_attempt" and not result["manual_download_completed"]
    assert result["network_requests"] == 0 and result["activation"] == "none"
    assert failure == dict(http_status=403, status="access_or_payload_failed")
