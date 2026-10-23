"""Independent adversarial BTS certification checks; synthetic inputs prove contracts only."""

from __future__ import annotations

import json
import shutil
from datetime import UTC, datetime
from uuid import uuid4

import pandas as pd
import pytest
from test_source_update_bts_candidate import CUTOFF, encoded, inputs, row

from src.common.storage import save_bronze
from src.source_updates import bts_candidate as candidate
from src.source_updates import bts_gold as gold
from src.source_updates import bts_native as native
from src.source_updates import retained
from src.source_updates.catalog import ROOT


@pytest.fixture
def workspace_factory(tmp_path):
    created = []

    def make(rows):
        workspace = ROOT / "tmp/source-updates" / ("test-bts-independent-" + uuid4().hex)
        created.append(workspace)
        source = tmp_path / uuid4().hex
        original = save_bronze(
            encoded(rows),
            "bts_t100",
            "international_segment_all_carriers_mexico",
            "2026",
            "zip",
            "https://www.transtats.bts.gov/DL_SelectFields.aspx?requested_year=2026",
            "manual",
            bronze_root=source,
            downloaded_at=datetime(2026, 10, 19, tzinfo=UTC),
        )
        receipt = retained.retain(
            workspace,
            source,
            "bts_segments",
            {"archive": original.relative_to(source).as_posix()},
            execute=True,
        )
        return workspace, receipt["run_id"]

    yield make
    for workspace in created:
        shutil.rmtree(workspace, ignore_errors=True)


def test_literal_classes_native_locators_and_zero_capacity_remain_observed():
    rows = [
        row(CLASS=code, AIRCRAFT_TYPE=str(614 + index), SEATS="0.00", PASSENGERS="0.00")
        for index, code in enumerate(["F", "G", "L", "P"])
    ]
    frame, evidence = native.read("bts_segments", inputs(rows), "2026M01")
    assert set(frame["class"]) == {"F", "G", "L", "P"}
    assert frame.load_factor.isna().all()
    assert sorted(frame.source_row) == [2, 3, 4, 5]
    assert {json.loads(value)["CLASS"] for value in frame.source_row_json} == {"F", "G", "L", "P"}
    assert evidence["service_classes_interpreted"] is False
    assert evidence["operator_coverage_verified"] is False
    assert evidence["complete_month_certified"] is False


@pytest.mark.parametrize("field", native.IDENTITY)
def test_identity_requires_each_exact_dot_entity_code_and_name_field(field):
    replacement = "999999" if field == "airline_id" else "UNAPPROVED"
    with pytest.raises(ValueError, match="Unmapped"):
        native.read("bts_segments", inputs([row(**{field.upper(): replacement})]), "2026M01")


def test_ambiguous_reference_mapping_blocks_without_name_fallback(tmp_path, monkeypatch):
    reference = pd.read_csv(ROOT / "config/carrier_crosswalk.csv", dtype=str, keep_default_na=False)
    extra = reference.loc[reference.carrier_key.eq("AEROMEXICO")].iloc[[0]].copy()
    extra["carrier_key"] = "WRONG_AFFILIATE"
    (tmp_path / "config").mkdir()
    pd.concat([reference, extra]).to_csv(tmp_path / "config/carrier_crosswalk.csv", index=False)
    monkeypatch.setattr(native, "ROOT", tmp_path)
    with pytest.raises(ValueError, match="Ambiguous"):
        native.read("bts_segments", inputs([row()]), "2026M01")


def test_configuration_aggregation_uses_weighted_capacity_and_complete_lineage(workspace_factory):
    rows = [
        row(SEATS="100.00", PASSENGERS="50.00", DISTANCE="100.00", FREIGHT="10.00"),
        row(AIRCRAFT_CONFIG="2", SEATS="200.00", PASSENGERS="180.00", DISTANCE="200.00"),
        row(CLASS="L", SEATS="10.00", PASSENGERS="5.00", DISTANCE="300.00"),
    ]
    workspace, run_id = workspace_factory(rows)
    result = candidate.run(workspace, "bts_segments", "2026M01", CUTOFF, run_id, execute=True)
    facts = pd.read_parquet(workspace / "data/gold/fact_route_traffic.parquet")
    scheduled = facts.loc[facts.service_class.eq("F")].iloc[0]
    assert len(facts) == 2
    assert scheduled.seats == 300 and scheduled.passengers == 230
    assert scheduled.asm_miles == 50_000 and scheduled.rpm_miles == 41_000
    assert scheduled.load_factor == 0.82
    assert scheduled.distance_miles == 150 and scheduled.distance_km == pytest.approx(241.4016)
    assert scheduled.freight_kg == pytest.approx(9.0718474)
    assert scheduled.departures_scheduled == 4 and scheduled.departures_performed == 6
    silver = pd.read_parquet(workspace / "data/silver/bts_t100_segment.parquet")
    bridge = pd.read_parquet(workspace / "data/gold/bridge_record_lineage.parquet")
    parents = bridge.loc[
        bridge.record_id.eq(scheduled.record_id) & bridge.link_type.eq("parent_record"), "parent_record_id"
    ]
    assert set(parents) == set(silver.loc[silver["class"].eq("F"), "record_id"])
    assert len(parents) == 2
    assert result["native_rows_projected"] == 3
    assert result["distance_aggregation"] == "native_unweighted_median_never_sum"


def test_carrier_dimension_validity_cannot_be_bypassed(tmp_path, monkeypatch):
    frame, details = native.read("bts_segments", inputs([row()]), "2026M01")
    carriers = pd.read_parquet(ROOT / "data/gold/dim_carrier.parquet")
    carriers.loc[carriers.carrier_key.eq("AEROMEXICO"), "valid_from"] = datetime(2026, 2, 1).date()
    (tmp_path / "data/gold").mkdir(parents=True)
    carriers.to_parquet(tmp_path / "data/gold/dim_carrier.parquet", index=False)
    monkeypatch.setattr(gold, "ROOT", tmp_path)
    with pytest.raises(ValueError, match="validity"):
        gold.frames(tmp_path, "bts_segments", "2026M01", frame, details)


def test_retrospective_add_change_remove_count_as_historical_not_new_release(workspace_factory):
    old_rows = [row(1), row(2), row(2, AIRCRAFT_TYPE="615")]
    new_rows = [row(1, PASSENGERS="71.00"), row(2), row(2, AIRCRAFT_TYPE="616"), row(3)]
    before, _ = native.read("bts_segments", inputs(old_rows), "2026M02")
    workspace, run_id = workspace_factory(new_rows)
    (workspace / "baselines").mkdir()
    before.to_parquet(workspace / "baselines/previous.parquet", index=False)
    result = candidate.run(
        workspace,
        "bts_segments",
        "2026M02",
        CUTOFF,
        run_id,
        execute=True,
        baseline="baselines/previous.parquet",
    )
    revisions = result["revisions"]
    assert revisions["historical_changes"] == {"added": 1, "removed": 1, "changed": 1, "unchanged": 1}
    assert revisions["newer_month_rows"] == 1
    assert result["observed_max_period"] == "2026M03"
    facts = pd.read_parquet(workspace / "data/gold/fact_route_traffic.parquet")
    assert set(facts.period_id) == {"2026M02"}
    assert set(facts.aircraft_type) == {614, 616}


@pytest.mark.parametrize("period_id", ["2026M12", None])
def test_revision_baseline_cannot_relabel_native_month(workspace_factory, period_id):
    workspace, run_id = workspace_factory([row(1), row(2)])
    before, _ = native.read("bts_segments", inputs([row(1)]), "2026M01")
    before["period_id"] = period_id
    (workspace / "baselines").mkdir()
    before.to_parquet(workspace / "baselines/previous.parquet", index=False)
    with pytest.raises(ValueError):
        candidate.run(
            workspace,
            "bts_segments",
            "2026M02",
            CUTOFF,
            run_id,
            execute=True,
            baseline="baselines/previous.parquet",
        )
    assert not (workspace / "data/gold").exists()


def test_reconciliation_totals_do_not_overflow_between_valid_fact_groups(workspace_factory):
    # Each ASM group stays below2**53, while their total exceeds signed int64.
    rows = [
        row(AIRCRAFT_TYPE=str(index + 1), SEATS="1000000000.00", DISTANCE="9000000.00")
        for index in range(1025)
    ]
    workspace, run_id = workspace_factory(rows)
    result = candidate.run(workspace, "bts_segments", "2026M01", CUTOFF, run_id, execute=True)
    assert result["native_sum_reconciliations"]["asm_miles"] == 9_225_000_000_000_000_000


@pytest.mark.parametrize("table", ["bts_t100_segment", "bridge_record_lineage", "dim_route"])
def test_replay_rejects_native_locator_lineage_or_dimension_tampering(workspace_factory, table):
    workspace, run_id = workspace_factory([row()])
    candidate.run(workspace, "bts_segments", "2026M01", CUTOFF, run_id, execute=True)
    layer = "silver" if table == "bts_t100_segment" else "gold"
    path = workspace / "data" / layer / (table + ".parquet")
    frame = pd.read_parquet(path)
    if table == "bts_t100_segment":
        frame.loc[0, "source_row"] = 999
    elif table == "bridge_record_lineage":
        frame = frame.iloc[:-1]
    else:
        frame.loc[0, "distance_miles"] += 1
    frame.to_parquet(path, index=False)
    before = candidate.inventory(workspace)
    with pytest.raises(ValueError, match="Output differs"):
        candidate.run(workspace, "bts_segments", "2026M01", CUTOFF, run_id, check=True)
    assert candidate.inventory(workspace) == before
