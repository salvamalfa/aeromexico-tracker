"""Contract tests for static SEC group reports; fixtures do not prove source availability."""

from __future__ import annotations

import json
import shutil
from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pandas as pd
import pytest

from src.common.storage import save_bronze
from src.source_updates import airport_group_candidate as candidate
from src.source_updates import airport_group_native as native
from src.source_updates import readiness, retained, retained_round
from src.source_updates.catalog import ROOT

PERIOD = "2026M07"
CUTOFF = "2026-10-23T12:00:00-06:00"


def table(rows):
    return (
        "<table>"
        + "".join("<tr>" + "".join("<td>" + str(c) + "</td>" for c in row) + "</tr>" for row in rows)
        + "</table>"
    )


def gap_html():
    header = ["Airport", "Jul-25", "Jul-26", "% Change", "Jan - Jul 25", "Jan - Jul 26", "% Change"]
    text = (
        "GRUPO AEROPORTUARIO DEL PACÍFICO announces preliminary terminal passenger "
        "traffic figures for July 2026 "
        "GUADALAJARA, Mexico, Aug. 05, 2026 "
        "12 Mexican airports operated by GAP; GAP’s airports in Jamaica " + native.CBX
    )
    for market, value in [("Domestic", "1.0"), ("International", "2.0"), ("Total", "3.0")]:
        rows = [header]
        for airport in native.GAP:
            rows.append([airport, value, value, "0.0", "%", value, value, "0.0", "%"])
        total = f"{14 * Decimal(value):.1f}"
        rows.append(["Total", total, total, "0.0", "%", total, total, "0.0", "%"])
        text += "<p>" + market + " Terminal Passengers (in thousands):</p>" + table(rows)
    return ("<html><body>" + text + "</body></html>").encode()


def asur_html():
    text = (
        "ASUR Announces Total Passenger Traffic for July 2026 "
        "Grupo Aeroportuario del Sureste, S.A.B. de C.V. "
        + native.ASUR_SCOPE
        + " Mexico City, August 5, 2026 - "
        "from July 1 to July 31, 2026, and from July 1 to July 31, 2025 "
    )

    def header(title):
        return [
            [title],
            ["", "July", "% Chg", "", "Year to date", "% Chg"],
            ["2025", "2026", "", "2025", "2026"],
        ]

    def counts(label, value):
        return [label, str(value), str(value), "0.0", "", str(value), str(value), "0.0"]

    summary = header("Passenger Traffic Summary")
    for label, total in [
        ("Mexico", 27),
        ("San Juan, Puerto Rico", 27),
        ("Colombia", 27),
        ("Total Traffic", 81),
    ]:
        summary += [
            counts(label, total),
            counts("Domestic Traffic", total // 3),
            counts("International Traffic", 2 * total // 3),
        ]
    detail = header("Mexico Passenger Traffic")
    for label, value in [("Domestic Traffic", 1), ("International Traffic", 2), ("Traffic Total Mexico", 3)]:
        detail.append(counts(label, value * 9))
        for code, name in native.ASUR.items():
            detail.append([code, name, *counts("", value)[1:]])
    return ("<html><body>" + text + table(summary) + table(detail) + "</body></html>").encode()


def original(product):
    cik = "1347557" if product == "gap_traffic" else "1123452"
    return dict(
        source_system="sec_edgar",
        source_file=f"{product}.htm",
        sha256="a" * 64,
        downloaded_at="2026-08-21T00:16:26+00:00",
        source_url=f"https://www.sec.gov/Archives/edgar/data/{cik}/0001/report.htm",
    )


@pytest.fixture(params=["gap_traffic", "asur_traffic"])
def stored(request, tmp_path):
    product = request.param
    workspace = ROOT / "tmp/source-updates" / ("test-airport-group-" + uuid4().hex)
    source = tmp_path / "bronze"
    content = gap_html() if product == "gap_traffic" else asur_html()
    row = original(product)
    path = save_bronze(
        content,
        "sec_edgar",
        product,
        PERIOD,
        "htm",
        row["source_url"],
        "manual",
        bronze_root=source,
        downloaded_at=datetime(2026, 8, 21, tzinfo=UTC),
    )
    selected = {"html": path.relative_to(source).as_posix()}
    saved = retained.retain(workspace, source, product, selected, execute=True)
    try:
        yield workspace, product, saved["run_id"], source, selected
    finally:
        shutil.rmtree(workspace, ignore_errors=True)


def test_complete_candidates_replay_and_readiness(stored):
    workspace, product, run_id, _, _ = stored
    args = (workspace, product, PERIOD, CUTOFF, run_id)
    assert candidate.run(*args)["status"] == "planned_not_executed"
    assert not (workspace / "data/silver").exists()
    result = candidate.run(*args, execute=True)
    assert result["lineage"]["status"] == "passed"
    assert result["latest_source_availability_verified"] is False
    assert result["ready_for_calendar_incorporation"] is False
    assert result["gold_country_scope"] == "MX_only"
    assert result["rows"]["silver/airport_group_native"] == (192 if product == "gap_traffic" else 156)
    airport = pd.read_parquet(workspace / "data/gold/fact_airport_traffic.parquet")
    group = pd.read_parquet(workspace / "data/gold/fact_airport_group_traffic.parquet")
    assert len(airport) == (24 if product == "gap_traffic" else 18)
    assert len(group) == 2 and set(group.country) == {"MX"}
    assert set(group.passengers_total) == ({36000} if product == "gap_traffic" else {27})
    assert airport.operations.isna().all() and airport.cargo_tons.isna().all()
    assert not airport.airport_iata.isin(["MBJ", "KIN"]).any()
    silver = pd.read_parquet(workspace / "data/silver/airport_traffic.parquet")
    assert set(silver.source_precision_passengers) == ({100} if product == "gap_traffic" else {1})
    before = candidate.inventory(workspace)
    assert candidate.run(*args, check=True)["output_sha256"] == result["output_sha256"]
    task = dict(
        id="group",
        product=product,
        period=PERIOD,
        adapter="airport_group",
        workspace=str(workspace),
        receipt_id=run_id,
        required=True,
        candidate_as_of=CUTOFF,
    )
    checked = readiness.check_task(task, CUTOFF)
    assert checked["latest_source_availability_verified"] is False
    assert candidate.inventory(workspace) == before
    with pytest.raises(ValueError, match="immutable"):
        candidate.run(*args, execute=True)
    with pytest.raises(ValueError, match="airport_group_candidate"):
        retained.run(*args, execute=True)


@pytest.mark.parametrize("change", ["gold", "bronze", "receipt", "cutoff", "code", "lock", "extra_output"])
def test_replay_rejects_changed_evidence(stored, monkeypatch, change):
    workspace, product, run_id, _, _ = stored
    args = [workspace, product, PERIOD, CUTOFF, run_id]
    candidate.run(*args, execute=True)
    if change == "gold":
        path = workspace / "data/gold/fact_airport_group_traffic.parquet"
        f = pd.read_parquet(path)
        f.loc[0, "passengers_total"] += 1
        f.to_parquet(path)
    elif change == "bronze":
        next((workspace / "data/bronze").rglob("*.htm")).write_bytes(b"changed")
    elif change == "receipt":
        path = workspace / "receipts" / f"airport-group-{product}-{PERIOD}.json"
        r = json.loads(path.read_text())
        r["publication"] = "approved"
        path.write_text(json.dumps(r))
    elif change == "cutoff":
        args[3] = "2026-10-24T12:00:00-06:00"
    elif change == "code":
        monkeypatch.setattr(candidate, "fingerprints", lambda: {"changed": "0" * 64})
    elif change == "extra_output":
        (workspace / "data/gold/other.parquet").write_bytes(b"extra")
    else:
        (workspace / ".source-update.lock").write_text("other writer")
    with pytest.raises(ValueError):
        candidate.run(*args, check=True)


def test_native_revisions_cover_non_gold_and_scope(stored):
    workspace, product, run_id, _, _ = stored
    inputs, _ = retained.originals(workspace, product, run_id, CUTOFF)
    frame, _ = native.read(product, inputs, PERIOD)
    baseline = workspace / "baselines/prior.parquet"
    baseline.parent.mkdir()
    frame.loc[frame.period_type.eq("year_to_date"), "value"] += 1
    frame.to_parquet(baseline, index=False)
    result = candidate.run(
        workspace, product, PERIOD, CUTOFF, run_id, baseline="baselines/prior.parquet", execute=True
    )
    assert result["revisions"]["changed"] == len(frame) // 2
    assert (
        candidate.run(workspace, product, PERIOD, CUTOFF, run_id, check=True)["revisions"]
        == result["revisions"]
    )
    frame.loc[0, "country"] = "FAKE"
    frame.to_parquet(baseline, index=False)
    with pytest.raises(ValueError):
        candidate.run(workspace, product, PERIOD, CUTOFF, run_id, check=True)


def test_batch_dedicated_dispatch(stored):
    workspace, product, _, source, selected = stored
    batch = workspace.parent / (workspace.name + "-batch")
    try:
        recipe = dict(
            version=1,
            as_of=CUTOFF,
            source_root=str(source),
            items=[dict(product=product, period=PERIOD, originals=selected)],
        )
        result = retained_round.execute(recipe, batch, write=True)
        assert result["status"] == "checks_passed"
        assert result["results"][0]["offline_replay_identical"] is True
    finally:
        shutil.rmtree(batch, ignore_errors=True)


@pytest.mark.parametrize("product,make", [("gap_traffic", gap_html), ("asur_traffic", asur_html)])
@pytest.mark.parametrize(
    "change", ["month", "cik", "scope", "missing", "duplicate", "number", "unit", "future_date"]
)
def test_native_rejects_contract_drift(product, make, change):
    content = make()
    row = original(product)
    if change == "month":
        content = content.replace(b"July 2026", b"August 2026")
    elif change == "cik":
        row["source_url"] = row["source_url"].replace("/data/", "/data/999")
    elif change == "scope":
        content = (
            content.replace(native.CBX.encode(), b"unknown")
            if product == "gap_traffic"
            else content.replace(native.ASUR_SCOPE.encode(), b"unknown")
        )
    elif change == "missing":
        content = (
            content.replace(b"Guadalajara", b"Unknown")
            if product == "gap_traffic"
            else content.replace(b"Cancun", b"Unknown")
        )
    elif change == "duplicate":
        content = (
            content.replace(b"Tijuana*", b"Guadalajara")
            if product == "gap_traffic"
            else content.replace(b"CZM", b"CUN")
        )
    elif change == "number":
        content = (
            content.replace(b"<td>1.0</td>", b"<td></td>", 1)
            if product == "gap_traffic"
            else content.replace(b"<td>27</td>", b"<td>-</td>", 1)
        )
    elif change == "unit":
        content = (
            content.replace(b"in thousands", b"in millions")
            if product == "gap_traffic"
            else content.replace(b"Year to date", b"Year total")
        )
    else:
        row["downloaded_at"] = "2026-07-31T00:00:00Z"
    with pytest.raises(ValueError):
        native.read(product, {"html": (content, row)}, PERIOD)


@pytest.mark.parametrize("value", ["", "-", "1,23", "1.00", "NaN", "-1.0", "1e3", "01.0"])
def test_gap_rounded_count_requires_native_precision(value):
    with pytest.raises(ValueError):
        native.number(value, 1)


def test_rounding_bound_is_mathematical_not_fudge():
    native.reconcile(Decimal("3.1"), [Decimal("1.0"), Decimal("2.0")], "0.1")
    with pytest.raises(ValueError):
        native.reconcile(Decimal("3.2"), [Decimal("1.0"), Decimal("2.0")], "0.1")
    with pytest.raises(ValueError):
        native.reconcile(Decimal(4), [Decimal(1), Decimal(2)], "0")
