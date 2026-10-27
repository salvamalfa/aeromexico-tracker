"""Synthetic binding contracts; only the separately retained originals prove real extraction."""

import hashlib
import json
import shutil
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import httpx
import pandas as pd
import pytest

from src.common.storage import save_bronze
from src.source_updates import availability, readiness, retained, series_candidate, series_native
from src.source_updates import banxico_calendar as calendar
from src.source_updates.catalog import ROOT
from src.source_updates.collection import collect
from src.source_updates.recipes import macro_round
from tests.test_source_update_series_independent import BANXICO_URL, banxico_bytes, original

CUTOFF = "2026-10-27T06:30:00-06:00"
METHOD = (
    "<table><tr><td>FIX <sup>2/</sup></td><td>Publicación DOF <sup>3/</sup></td>"
    "<td>Para pagos <sup>4/</sup></td></tr><tr><td class='notasNotas'><b>2/</b> "
    "El tipo de cambio FIX es determinado por el Banco de México los días hábiles bancarios "
    "con base en un promedio de las cotizaciones.</td></tr></table>"
).encode("latin1")


@pytest.fixture
def inputs(monkeypatch):
    # Narrow fixture-only edition pin; this never approves/captures this synthetic page.
    monkeypatch.setattr(calendar, "METHOD_SHA", hashlib.sha256(METHOD).hexdigest())
    days = pd.date_range("2026-07-01", "2026-09-30")
    selected = {
        "SF43718": [d for d in days if d.weekday() < 5 and str(d.date()) != "2026-09-16"],
        "SP1": [d for d in days if d.day == 1],
        "SF61745": list(days),
    }
    values = {}
    for role, dates in selected.items():
        body = banxico_bytes(
            role,
            [(d.strftime("%d/%m/%Y"), "10") for d in dates],
            metadata_changes={"Título": "Fecha de determinación (FIX)"} if role == "SF43718" else {},
        )
        values[role] = original(body, "banxico_sie", role, BANXICO_URL, "csv")
    body, row = original(METHOD, "banxico_sie", "SF43718_methodology", calendar.METHOD_URL, "html")
    row["logical_key"] = "banxico_sie|SF43718_methodology|current|html"
    values["fix_methodology"] = body, row
    return values


def changed_body(inputs, role, body):
    result = deepcopy(inputs)
    row = result[role][1]
    row.update(sha256=hashlib.sha256(body).hexdigest(), bytes=len(body))
    result[role] = body, row
    return result


def test_exact_universes_and_legacy_roles(inputs):
    for period, counts in (("2026M09", (21, 1, 30)), ("2026Q3", (65, 3, 92))):
        silver, details = series_native.read("banxico", inputs, period)
        proof = details["observation_calendar"]
        assert details["calendar_completeness_certified"]
        assert [proof["series"][s]["observed_count"] for s in ("SF43718", "SP1", "SF61745")] == list(counts)
        assert proof["date_basis"] == "native_date_labels_without_UTC_conversion"
        assert proof["series"]["SF61745"]["completeness_basis"] == (
            "full_daily_universe_sufficient_not_inferred_provider_schedule"
        )
        assert all(r["provider_schedule_inferred"] is False for r in proof["series"].values())
        assert silver["macro_indicators"].date.dt.tz is None
        assert proof["first_publication_date"] is proof["release_lag_days"] is None
    _, old = series_native.read(
        "banxico", {k: v for k, v in inputs.items() if k != "fix_methodology"}, "2026M09"
    )
    assert "observation_calendar" not in old
    assert all(not r["calendar_completeness_certified"] for r in old["coverage"].values())
    body = inputs["SF61745"][0].replace(b"12/07/2026,10\r\n", b"")
    _, details = series_native.read("banxico", changed_body(inputs, "SF61745", body), "2026Q3")
    assert not details["calendar_completeness_certified"]
    assert details["observation_calendar"]["series"]["SF61745"]["missing_dates"] == ["2026-07-12"]


def test_equal_counts_wrong_dates_missing_values_and_duplicates(inputs):
    # A banking holiday replacing a business date has the same row count, but a different universe.
    body = inputs["SF43718"][0].replace(b"15/09/2026", b"16/09/2026")
    _, details = series_native.read("banxico", changed_body(inputs, "SF43718", body), "2026M09")
    proof = details["observation_calendar"]["series"]["SF43718"]
    assert proof["expected_count"] == proof["observed_count"] == 21
    assert proof["missing_dates"] == ["2026-09-15"] and proof["unexpected_dates"] == ["2026-09-16"]
    assert not details["calendar_completeness_certified"]
    for role, before, after in (
        ("SF61745", b"15/09/2026,10", b"15/09/2026,NaN"),
        ("SF61745", b"15/09/2026,10", b"15/09/2026,10\r\n15/09/2026,10"),
        ("SP1", b"01/09/2026", b"02/09/2026"),
    ):
        body = inputs[role][0].replace(before, after)
        with pytest.raises(ValueError):
            series_native.read("banxico", changed_body(inputs, role, body), "2026M09")


def test_methodology_hash_identity_metadata_and_roles_fail_closed(inputs, monkeypatch):
    for field, value in (
        ("source_url", BANXICO_URL),
        ("logical_key", "banxico_sie|SP1|current|html"),
        ("http_status", 503),
        ("sha256", "0" * 64),
        ("source_system", "eia"),
    ):
        bad = deepcopy(inputs)
        bad["fix_methodology"][1][field] = value
        with pytest.raises(ValueError, match="methodology"):
            series_native.read("banxico", bad, "2026M09")
    # Coherent self-rehashed replacement still cannot replace the reviewed edition.
    bad = changed_body(inputs, "fix_methodology", METHOD.replace(b"FIX", b"DOF"))
    with pytest.raises(ValueError, match="reviewed physical"):
        series_native.read("banxico", bad, "2026M09")
    with monkeypatch.context() as fixture_pin:
        fixture_pin.setattr(calendar, "METHOD_SHA", bad["fix_methodology"][1]["sha256"])
        with pytest.raises(ValueError, match="note2"):
            series_native.read("banxico", bad, "2026M09")
    for bad in ({k: v for k, v in inputs.items() if k != "SP1"}, {**inputs, "unreviewed": inputs["SP1"]}):
        with pytest.raises(ValueError, match="canonical product input roles"):
            series_native.read("banxico", bad, "2026M09")
    body = inputs["SF43718"][0].replace(b"determinaci\xf3n", b"publicaci\xf3n")
    with pytest.raises(ValueError, match="determinación"):
        series_native.read("banxico", changed_body(inputs, "SF43718", body), "2026M09")
    with pytest.raises(ValueError, match="Unverified banking calendar for 2027"):
        calendar.certify(inputs, "2027M01")


@pytest.fixture
def candidate(inputs, tmp_path):
    workspace = ROOT / "tmp/source-updates" / ("test-banxico-calendar-" + uuid4().hex)
    source = tmp_path / "bronze"
    selected = {}
    for role, (body, row) in inputs.items():
        _, entity, period, extension = row["logical_key"].split("|")
        path = save_bronze(
            body,
            "banxico_sie",
            entity,
            period,
            extension,
            row["source_url"],
            "manual",
            bronze_root=source,
            downloaded_at=datetime(2026, 10, 27, 12, 15, tzinfo=UTC),
        )
        selected[role] = path.relative_to(source).as_posix()
    receipt = retained.retain(workspace, source, "banxico", selected, execute=True)
    try:
        yield workspace, receipt["run_id"]
    finally:
        shutil.rmtree(workspace, ignore_errors=True)


def test_integral_candidate_propagates_proof_without_numeric_methodology_parent(candidate):
    workspace, receipt = candidate
    args = workspace, "banxico", "2026M09", CUTOFF, receipt
    assert series_candidate.run(*args)["status"] == "planned_not_executed"
    result = series_candidate.run(*args, execute=True)
    assert result["calendar_completeness_certified"] and result["lineage"]["status"] == "passed"
    assert result["first_publication_date"] is result["release_lag_days"] is None
    artifacts = pd.read_parquet(workspace / "data/gold/dim_source_artifact.parquet")
    bridge = pd.read_parquet(workspace / "data/gold/bridge_record_lineage.parquet")
    method = artifacts.loc[artifacts.source_url.eq(calendar.METHOD_URL)]
    assert len(artifacts) == 4 and len(method) == 1
    assert not bridge.artifact_id.isin(method.artifact_id).any()
    before = readiness.inventory(workspace)
    checked = series_candidate.run(*args, check=True)
    assert checked["output_sha256"] == result["output_sha256"] and readiness.inventory(workspace) == before
    item = dict(
        id="banxico",
        product="banxico",
        period="2026M09",
        adapter="series",
        workspace=str(workspace),
        receipt_id=receipt,
        required=True,
        candidate_as_of=CUTOFF,
    )
    task = readiness.check_task(item, CUTOFF)
    assert task["calendar_completeness_certified"]
    assert "publication_calendar_completeness_not_verified" not in task["source_conditions"]
    assert "retained_original_does_not_verify_current_source_availability" in task["source_conditions"]
    proof = calendar.verify_candidate(item, result, CUTOFF)
    assert proof == result["observation_calendar"]
    with pytest.raises(ValueError, match="after requested cutoff"):
        calendar.verify_candidate(item, result, "2026-10-27T06:00:00-06:00")
    changed = deepcopy(result)
    changed["observation_calendar"]["series"]["SF61745"]["complete"] = False
    with pytest.raises(ValueError, match="evidence changed"):
        calendar.verify_candidate(item, changed, CUTOFF)
    # Receipt tamper is rejected without writes, including a plausible false calendar flag.
    path = workspace / "receipts/series-banxico-2026M09.json"
    accepted = json.loads(path.read_text())
    accepted["calendar_completeness_certified"] = False
    path.write_text(json.dumps(accepted))
    before = readiness.inventory(workspace)
    with pytest.raises(ValueError, match="evidence changed"):
        series_candidate.run(*args, check=True)
    assert readiness.inventory(workspace) == before


def test_physical_proof_cannot_be_reclassified_or_borrowed(candidate):
    workspace, receipt = candidate
    result = series_candidate.run(workspace, "banxico", "2026M09", CUTOFF, receipt, execute=True)
    proof = deepcopy(result["observation_calendar"])
    proof["inputs"]["fix_methodology"] = proof["inputs"]["SP1"]
    with pytest.raises(ValueError, match="four distinct"):
        calendar.verify_workspace(workspace, "2026M09", proof)
    method = (
        workspace / "data/bronze" / result["observation_calendar"]["inputs"]["fix_methodology"]["source_file"]
    )
    sidecar = method.with_name(method.name + ".meta.json")
    meta = json.loads(sidecar.read_text())
    meta["http_status"] = 404
    sidecar.write_text(json.dumps(meta))
    with pytest.raises(ValueError, match="sidecar"):
        calendar.verify_workspace(workspace, "2026M09", result["observation_calendar"])


def test_direct_helper_requires_safe_workspace_and_regular_physical_inputs(candidate, tmp_path):
    workspace, receipt = candidate
    inputs, _ = retained.originals(workspace, "banxico", receipt, CUTOFF)
    _, details = series_native.read("banxico", inputs, "2026M09")
    proof = details["observation_calendar"]
    assert calendar.verify_workspace(workspace, "2026M09", proof) == proof
    with pytest.raises(ValueError, match="child of this checkout"):
        calendar.verify_workspace(tmp_path, "2026M09", proof)
    bronze = workspace / "data/bronze"
    raw = bronze / proof["inputs"]["fix_methodology"]["source_file"]
    target = tmp_path / "outside.html"
    target.write_bytes(METHOD)
    # All three direct-reader paths reject non-regular entries before attempting a read.
    for path in (bronze / "_manifest.jsonl", raw, raw.with_name(raw.name + ".meta.json")):
        saved = path.read_bytes()
        path.unlink()
        try:
            path.mkdir()
            with pytest.raises(ValueError, match="regular physical"):
                calendar.verify_workspace(workspace, "2026M09", proof)
            path.rmdir()
            path.symlink_to(target)
            with pytest.raises(ValueError, match="symlinks"):
                calendar.verify_workspace(workspace, "2026M09", proof)
            path.unlink()
        finally:
            if path.is_symlink():
                path.unlink()
            elif path.is_dir():
                path.rmdir()
            path.write_bytes(saved)
    assert calendar.verify_workspace(workspace, "2026M09", proof) == proof


def test_canonical_availability_propagates_only_the_replayed_calendar(inputs):
    root = ROOT / "tmp/source-updates" / ("test-banxico-availability-" + uuid4().hex)
    source = root / "offline-staging"
    collection = root / "collection"

    # Synthetic request adapter only. No official extraction is claimed by this test.
    class Client:
        def __init__(self, *args, **kw):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def request(self, method, url, **kw):
            role = kw["data"]["series"]
            body = inputs[role][0]
            if role == "SF61745":
                body = body.replace(b"12/07/2026,10\r\n", b"")
            return httpx.Response(200, content=body, request=httpx.Request(method, url))

    try:
        cutoff = (datetime.now(UTC) + timedelta(seconds=2)).isoformat()
        selection = macro_round("banxico", "2026M09", cutoff)["selection"]
        collected = collect(selection, collection, execute=True, client_factory=Client)
        cutoff = (datetime.now(UTC) + timedelta(seconds=2)).isoformat()
        shutil.copytree(collection / "data/bronze", source)
        method = save_bronze(
            METHOD,
            "banxico_sie",
            "SF43718_methodology",
            "current",
            "html",
            calendar.METHOD_URL,
            "manual",
            bronze_root=source,
            downloaded_at=datetime.fromisoformat(collected["started_at"]),
        )
        selected = {
            r["logical_key"].split("|")[1]: r["source_file"]
            for r in [json.loads(line) for line in (source / "_manifest.jsonl").read_text().splitlines()]
            if r["logical_key"].split("|")[1] != "SF43718_methodology"
        }
        selected["fix_methodology"] = method.relative_to(source).as_posix()
        binding = dict(
            workspace=str(collection),
            run_id=collected["run_id"],
            series_items={r["entity"]: r["id"] for r in selection["items"]},
        )
        for period in ("2026M09", "2026Q3"):
            workspace = root / period
            receipt = retained.retain(workspace, source, "banxico", selected, execute=True)
            result = series_candidate.run(
                workspace, "banxico", period, cutoff, receipt["run_id"], execute=True
            )
            item = dict(
                id="banxico",
                product="banxico",
                period=period,
                adapter="series",
                workspace=str(workspace),
                receipt_id=receipt["run_id"],
                required=True,
                candidate_as_of=cutoff,
                availability=binding,
            )
            before = readiness.inventory(root)
            proof = availability.verify(item, result, cutoff)
            assert proof["calendar_completeness_certified"] is (period == "2026M09")
            assert proof["observation_calendar"] == result["observation_calendar"]
            if period == "2026Q3":
                assert proof["availability_basis"] == (
                    "current_canonical_responses_with_observation_calendar_not_certified"
                )
            task = readiness.check_task(item, cutoff, round_as_of=cutoff)
            assert task["latest_source_availability_verified"]
            assert task["calendar_completeness_certified"] is (period == "2026M09")
            assert ("publication_calendar_completeness_not_verified" in task["source_conditions"]) is (
                period == "2026Q3"
            )
            assert readiness.inventory(root) == before
            forged = deepcopy(result)
            forged["calendar_completeness_certified"] = not result["calendar_completeness_certified"]
            with pytest.raises(ValueError, match="physical series/methodology replay"):
                availability.verify(item, forged, cutoff)
    finally:
        shutil.rmtree(root, ignore_errors=True)
