"""Synthetic contract tests; retained official-vintage execution is documented separately."""

import csv
import hashlib
import io
import json
import shutil
from datetime import UTC, datetime
from uuid import uuid4
from zipfile import ZIP_DEFLATED, ZipFile

import pandas as pd
import pytest

from src.common.storage import save_bronze
from src.source_updates import bts_candidate as candidate
from src.source_updates import bts_native as native
from src.source_updates import readiness, retained, retained_round
from src.source_updates.catalog import ROOT

CUTOFF = "2026-10-23T12:00:00-06:00"


def row(month=1, **changes):
    reference = pd.read_csv(ROOT / "config/carrier_crosswalk.csv", dtype=str, keep_default_na=False)
    identity = reference.loc[reference.carrier_key.eq("AEROMEXICO")].iloc[0]
    result = {key: "0.00" for key in native.FIELDS[:9]}
    result.update({key.upper(): str(identity[key]) for key in native.IDENTITY})
    result.update(
        DEPARTURES_SCHEDULED="2.00",
        DEPARTURES_PERFORMED="3.00",
        SEATS="100.00",
        PASSENGERS="70.00",
        DISTANCE="1000.00",
        FREIGHT="10.00",
        MAIL="2.00",
        CARRIER_GROUP="0",
        ORIGIN="MEX",
        ORIGIN_CITY_NAME="Mexico City",
        ORIGIN_COUNTRY="MX",
        ORIGIN_COUNTRY_NAME="Mexico",
        DEST="JFK",
        DEST_CITY_NAME="New York",
        DEST_COUNTRY="US",
        DEST_COUNTRY_NAME="United States",
        AIRCRAFT_TYPE="614",
        AIRCRAFT_CONFIG="1",
        YEAR="2026",
        QUARTER=str((month - 1) // 3 + 1),
        MONTH=str(month),
        CLASS="F",
    )
    result.update(changes)
    return result


def encoded(rows=None, docs=None, extra=False):
    def body(values, fields):
        stream = io.StringIO(newline="")
        writer = csv.DictWriter(stream, fields)
        writer.writeheader()
        writer.writerows(values)
        return stream.getvalue().encode()

    docs = native.DOCUMENTATION if docs is None else docs
    stream = io.BytesIO()
    with ZipFile(stream, "w", compression=ZIP_DEFLATED) as archive:
        archive.writestr(native.DATA_MEMBER, body(rows if rows is not None else [row()], native.FIELDS))
        archive.writestr(
            native.DOC_MEMBER,
            body(
                [dict(SYS_FIELD_NAME=k, FIELD_DESC=v) for k, v in docs.items()],
                ["SYS_FIELD_NAME", "FIELD_DESC"],
            ),
        )
        if extra:
            archive.writestr("../unreviewed.csv", b"new")
    return stream.getvalue()


def inputs(rows=None, docs=None, extra=False):
    content = encoded(rows, docs, extra)
    return {
        "archive": (
            content,
            dict(
                source_system="bts_t100",
                source_file="bts/test.zip",
                sha256=hashlib.sha256(content).hexdigest(),
                downloaded_at="2026-10-19T15:08:27+00:00",
            ),
        )
    }


@pytest.fixture
def stored(tmp_path):
    workspace = ROOT / "tmp/source-updates" / ("test-bts-" + uuid4().hex)
    source = tmp_path / "bronze"
    content = encoded([row(m) for m in range(1, 4)])
    path = save_bronze(
        content,
        "bts_t100",
        "international_segment_all_carriers_mexico",
        "2026",
        "zip",
        "https://www.transtats.bts.gov/DL_SelectFields.aspx?requested_year=2026",
        "manual",
        bronze_root=source,
        downloaded_at=datetime(2026, 10, 19, tzinfo=UTC),
    )
    selected = {"archive": path.relative_to(source).as_posix()}
    saved = retained.retain(workspace, source, "bts_segments", selected, execute=True)
    try:
        yield workspace, saved["run_id"], source, selected
    finally:
        shutil.rmtree(workspace, ignore_errors=True)


def test_full_candidate_replay_and_readiness(stored):
    workspace, run_id, _, _ = stored
    args = (workspace, "bts_segments", "2026M03", CUTOFF, run_id)
    assert candidate.run(*args)["status"] == "planned_not_executed"
    assert not (workspace / "data/silver").exists()
    result = candidate.run(*args, execute=True)
    assert len(result["output_sha256"]) == 7
    assert result["complete_month_certified"] is False
    assert result["selected_month_observations_certified"] is True
    assert result["latest_source_availability_verified"] is False
    assert result["first_publication_date"] is None and result["release_lag_days"] is None
    assert result["native_rows_projected"] == 1 and result["native_rows_outside_projection"] == 2
    before = candidate.inventory(workspace)
    assert candidate.run(*args, check=True)["output_sha256"] == result["output_sha256"]
    task = dict(
        id="bts",
        product="bts_segments",
        period="2026M03",
        adapter="bts",
        workspace=str(workspace),
        receipt_id=run_id,
        required=True,
        candidate_as_of=CUTOFF,
    )
    assert "source_does_not_certify_complete_month" in readiness.check_task(task, CUTOFF)["source_conditions"]
    assert candidate.inventory(workspace) == before
    assert "config/carrier_crosswalk.csv" in result["code_files"]
    assert "data/gold/dim_carrier.parquet" in result["code_files"]
    fact = pd.read_parquet(workspace / "data/gold/fact_route_traffic.parquet").iloc[0]
    assert fact.freight_kg == pytest.approx(4.5359237)
    assert fact.mail_kg == pytest.approx(0.90718474)
    assert fact.ask_km == pytest.approx(160934.4)
    assert fact.rpk_km == pytest.approx(112654.08)
    assert fact.load_factor == 0.7 and fact.departures_performed == 3
    assert fact.period_id == "2026M03"
    bridge = pd.read_parquet(workspace / "data/gold/bridge_record_lineage.parquet")
    assert (
        len(bridge.loc[bridge.table_name.eq("fact_route_traffic") & bridge.link_type.eq("parent_record")])
        == 1
    )
    with pytest.raises(ValueError, match="immutable"):
        candidate.run(*args, execute=True)
    with pytest.raises(ValueError, match="bts_candidate"):
        retained.run(*args, execute=True)


def test_previous_month_and_quality_issue_scope():
    data, result = native.read(
        "bts_segments", inputs([row(1, SEATS="13.00", PASSENGERS="14.00"), row(2)]), "2026M02"
    )
    assert len(data) == 2 and result["native_quality_issues"][0]["period_id"] == "2026M01"
    assert data.loc[data.month.eq(1)].load_factor.iloc[0] > 1
    with pytest.raises(ValueError, match="passengers above"):
        native.read("bts_segments", inputs([row(1, SEATS="13.00", PASSENGERS="14.00"), row(2)]), "2026M01")
    data, result = native.read("bts_segments", inputs([row(1), row(2)]), "2026M01")
    assert result["observed_max_period"] == "2026M02" and result["projected_period"] == "2026M01"


@pytest.mark.parametrize(
    "changes",
    [
        {"MONTH": "13"},
        {"QUARTER": "2"},
        {"YEAR": "2025"},
        {"CLASS": "Z"},
        {"AIRCRAFT_CONFIG": "9"},
        {"AIRCRAFT_CONFIG": "4"},  # not in the reviewed segment configurations
        {"AIRCRAFT_TYPE": "0094"},
        {"AIRCRAFT_TYPE": "094.0"},
        {"AIRCRAFT_TYPE": "+94"},
        {"AIRCRAFT_TYPE": "000"},
        {"AIRLINE_ID": "019393"},
        {"SEATS": ""},
        {"PASSENGERS": "-1.00"},
        {"FREIGHT": "1.50"},
        {"DISTANCE": "0.00"},
        {"DEST_COUNTRY": "CA"},
        {"AIRLINE_ID": "12345"},
        {"UNIQUE_CARRIER_NAME": "Fuzzy Aeromexico"},
        {"SEATS": "1000000000000.00", "DISTANCE": "1000000000000.00"},
    ],
)
def test_native_drift_and_invalid_values_fail(changes):
    with pytest.raises(ValueError):
        native.read("bts_segments", inputs([row(**changes)]), "2026M01")


def test_reviewed_aircraft_code_padding_and_combined_configuration_keep_original_tokens():
    frame, details = native.read(
        "bts_segments", inputs([row(AIRCRAFT_TYPE="094", AIRCRAFT_CONFIG="3")]), "2026M01"
    )
    assert frame.aircraft_type.iloc[0] == 94 and frame.aircraft_config.iloc[0] == 3
    assert json.loads(frame.source_row_json.iloc[0])["AIRCRAFT_TYPE"] == "094"
    assert details["zero_padded_aircraft_type_tokens"] == {"094": 1}
    assert details["combined_aircraft_configuration_rows"] == 1
    assert details["complete_month_certified"] is details["operator_coverage_verified"] is False


def test_aircraft_padding_never_silently_merges_distinct_source_rows():
    with pytest.raises(ValueError, match="Duplicate Silver grain"):
        native.read("bts_segments", inputs([row(AIRCRAFT_TYPE="094"), row(AIRCRAFT_TYPE="94")]), "2026M01")


def test_no_missing_month_or_duplicate_grain_or_dictionary_drift():
    for rows in [[row(1), row(3)], [row(1), row(1)]]:
        with pytest.raises(ValueError):
            native.read("bts_segments", inputs(rows), "2026M01")
    docs = {**native.DOCUMENTATION, "FREIGHT": "Non-Stop Segment Freight Transported (kg)"}
    with pytest.raises(ValueError, match="dictionary"):
        native.read("bts_segments", inputs(docs=docs), "2026M01")
    with pytest.raises(ValueError, match="members"):
        native.read("bts_segments", inputs(extra=True), "2026M01")


@pytest.mark.parametrize("kind", ["gold", "source", "receipt", "code", "cutoff", "lock", "baseline"])
def test_immutable_replay_tampering(stored, monkeypatch, kind):
    workspace, run_id, _, _ = stored
    args = [workspace, "bts_segments", "2026M03", CUTOFF, run_id]
    candidate.run(*args, execute=True)
    if kind == "gold":
        path = workspace / "data/gold/fact_route_traffic.parquet"
        frame = pd.read_parquet(path)
        frame.loc[0, "passengers"] = 50
        frame.to_parquet(path, index=False)
    elif kind == "source":
        next((workspace / "data/bronze").rglob("*.zip")).write_bytes(b"wrong")
    elif kind == "receipt":
        path = workspace / "receipts/bts-bts_segments-2026M03.json"
        receipt = json.loads(path.read_text())
        receipt["complete_month_certified"] = True
        path.write_text(json.dumps(receipt))
    elif kind == "code":
        monkeypatch.setattr(candidate, "fingerprints", lambda: {"modified.py": "0" * 64})
    elif kind == "cutoff":
        args[3] = "2026-10-23T12:01:00-06:00"
    elif kind == "lock":
        (workspace / ".source-update.lock").write_text("active")
    with pytest.raises(ValueError):
        candidate.run(
            *args, check=True, **({"baseline": "baselines/new.parquet"} if kind == "baseline" else {})
        )


def test_full_grain_revisions_and_retrospective_rows(stored):
    workspace, run_id, _, _ = stored
    data, _ = native.read("bts_segments", inputs([row(1), row(2)]), "2026M02")
    (workspace / "baselines").mkdir()
    data.to_parquet(workspace / "baselines/previous.parquet", index=False)
    result = candidate.run(
        workspace,
        "bts_segments",
        "2026M03",
        CUTOFF,
        run_id,
        execute=True,
        baseline="baselines/previous.parquet",
    )
    changes = result["revisions"]
    assert changes["added"] == 1 and changes["unchanged"] == 2
    assert changes["historical_changes"] == {"added": 0, "removed": 0, "changed": 0, "unchanged": 2}
    assert changes["newer_month_rows"] == 1
    candidate.run(workspace, "bts_segments", "2026M03", CUTOFF, run_id, check=True)


def test_batch_routes_bts_to_dedicated_complete_adapter(stored):
    workspace, _, source, selected = stored
    batch = workspace.parent / ("test-bts-batch-" + uuid4().hex)
    try:
        result = retained_round.execute(
            dict(
                version=1,
                as_of=CUTOFF,
                source_root=str(source),
                items=[dict(product="bts_segments", period="2026M03", originals=selected)],
            ),
            batch,
            write=True,
        )
        assert result["status"] == "checks_passed"
        assert len(result["results"][0]["rows"]) == 7
    finally:
        shutil.rmtree(batch, ignore_errors=True)


@pytest.mark.parametrize("adapter", ["retained", "government"])
def test_readiness_rejects_bypassing_complete_bts_adapter(stored, adapter):
    workspace, run_id, _, _ = stored
    task = dict(
        id="bts",
        product="bts_segments",
        period="2026M03",
        adapter=adapter,
        workspace=str(workspace),
        receipt_id=run_id,
        required=True,
        candidate_as_of=CUTOFF,
    )
    recipe = dict(version=1, as_of=CUTOFF, required_items=["bts"], items=[task])
    with pytest.raises(ValueError, match="complete dedicated adapter"):
        readiness.preflight(recipe, workspace.parent / ("test-bts-readiness-" + uuid4().hex))
    task["adapter"] = "bts"
    assert (
        readiness.preflight(recipe, workspace.parent / ("test-bts-readiness-" + uuid4().hex))[0]["adapter"]
        == "bts"
    )
