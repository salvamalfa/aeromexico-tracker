"""A semantic correction matches source cells exactly and preserves unrelated approved data."""

from copy import deepcopy

import pandas as pd
import pytest
from test_recorded_movements import frame, public_network

from src.publish.movements_projection import (
    BINDING_OUTPUTS,
    CAPTURES,
    COLUMNS,
    HISTORICAL_SHA,
    JULY_SHA,
    Q2_SHA,
    SOURCE_COUNTS,
    TARGETS,
    project_coverage,
    project_file,
    project_network,
    projection_frame,
)


def fixture():
    observations = frame()
    observations["source_hash"] = HISTORICAL_SHA
    before = public_network(observations)
    route = before["routes"][0]
    del route["recorded_movements"]
    route.update(departures=30, operation_status="operated_observed", source_label="Colombia · Aerocivil")
    route["coverage_note"] = (
        "Meses: 07 · Colombia · Aerocivil · Vuelos por celda operador/ruta/sentido/mes: 30 observed"
    )
    route["directions"][0]["departures"] = 30
    route["flight_components"] = [
        dict(
            carrier_key="AEROMEXICO",
            origin_iata="MEX",
            destination_iata="BOG",
            period_id="2026M07",
            kind="observed",
            departures=30,
            source_label="Colombia · Aerocivil",
            source_hashes=[HISTORICAL_SHA],
        )
    ]
    before["coverage_by_source"] = {"Colombia · Aerocivil": ["2026M07"]}
    july = observations.copy()
    july["source_hash"] = JULY_SHA
    return before, pd.concat([observations, july], ignore_index=True)


def test_source_counts_preserved_while_departures_and_yoy_are_cleared():
    before, source = fixture()
    expected = deepcopy(before)
    after = project_network(before, source)
    assert before == expected
    route = after["routes"][0]
    assert route["recorded_movements"]["count"] == 30
    assert route["departures"] is None and route["previous"]["departures"] is None
    assert route["flight_components"] == []
    assert route["directions"][0]["departures"] is None
    for field in ("passengers", "seats", "load_factor", "monthly"):
        assert route[field] == before["routes"][0][field]
    assert "30 observed" not in route["coverage_note"]
    assert route["recorded_movements"]["observed_months"] == ["2026M07"]


@pytest.mark.parametrize(
    "mutation", ["count", "operator", "hash", "month", "direction", "duplicate", "missing"]
)
def test_baseline_cell_mutation_cannot_be_relabelled_as_semantics_only(mutation):
    before, source = fixture()
    cell = before["routes"][0]["flight_components"][0]
    if mutation == "count":
        cell["departures"] += 1
    if mutation == "operator":
        cell["carrier_key"] = "VOLARIS"
    if mutation == "hash":
        cell["source_hashes"] = [JULY_SHA]
    if mutation == "month":
        cell["period_id"] = "2026M06"
    if mutation == "direction":
        cell["origin_iata"], cell["destination_iata"] = "BOG", "MEX"
    if mutation == "duplicate":
        before["routes"][0]["flight_components"].append(deepcopy(cell))
    if mutation == "missing":
        source = source.iloc[:0]
    with pytest.raises(ValueError, match="original|source|historical|scope"):
        project_network(before, source)


def test_unrelated_observed_estimated_and_scheduled_components_are_preserved():
    before, source = fixture()
    route = before["routes"][0]
    cell = {
        **route["flight_components"][0],
        "kind": "estimated",
        "source_label": "AeroDataBox",
        "departures": 12,
        "source_hashes": [],
    }
    route["flight_components"].append(cell)
    route["departures"] = 42
    after = project_network(before, source)["routes"][0]
    assert after["departures"] == 12 and after["flight_components"] == [cell]
    assert after["recorded_movements"]["count"] == 30
    assert after["operation_status"] == "estimated_from_retained_frequencies"


def test_coverage_only_subtracts_its_original_movement_contribution():
    sources, rows = [], []
    for entity, operator in [("AEROMEXICO", "AMX"), ("VIVA_AEROBUS", "VIV"), ("VOLARIS", "VOI")]:
        for month in ["2026M04", "2026M05", "2026M06"]:
            sources.append(dict(source_hash=Q2_SHA, operator_icao=operator, period_id=month, operations=2))
        for period in ["2026M04", "2026M05", "2026M06", "2026Q2"]:
            for scope in ["domestic", "international"]:
                rows.append(
                    dict(
                        entity=entity,
                        period_id=period,
                        scope=scope,
                        observed_regular=100,
                        estimated=50,
                        official_regular=200,
                    )
                )
    before = dict(map_coverage=dict(rows=rows), untouched={"financial": 7})
    after = project_coverage(before, pd.DataFrame(sources))
    assert after["untouched"] == before["untouched"]
    for old, new in zip(rows, after["map_coverage"]["rows"], strict=True):
        assert new["observed_regular"] == (
            100 if old["scope"] == "domestic" else 94 if old["period_id"] == "2026Q2" else 98
        )
        assert new["estimated"] == 50 and new["official_regular"] == 200


def synthetic_projection():
    rows, originals = [], []
    for source, (size, total) in SOURCE_COUNTS.items():
        for i in range(size):
            row = frame().iloc[0].to_dict()
            row.update(
                source_hash=source,
                commercial_designator_as_reported=f"P{i}",
                source_locator=f"record:{i + 1}",
                operations=float(total - size + 1 if i == 0 else 1),
                downloaded_at=CAPTURES[source][1],
            )
            rows.append({k: row[k] for k in COLUMNS})
        originals.append(
            dict(
                sha256=source,
                bytes=CAPTURES[source][0],
                downloaded_at=CAPTURES[source][1],
                source_url="https://www.datos.gov.co",
                metadata_sha256="a" * 64,
            )
        )
    binding = dict(
        product="aerocivil",
        period="2026M07",
        receipt_id="b" * 32,
        candidate_as_of="2026-10-21T01:06:33.087948+00:00",
        output_sha256={key: "c" * 64 for key in BINDING_OUTPUTS},
    )
    return rows, dict(originals=originals, airport_reference={}, source_binding=binding)


def test_complete_reviewed_source_editions_dates_bindings_and_row_counts_are_required():
    rows, evidence = synthetic_projection()
    assert len(projection_frame(rows, evidence)) == 219
    for mutation in ["count", "date", "rows", "binding", "eligibility", "provisional"]:
        bad_rows, bad_evidence = deepcopy(rows), deepcopy(evidence)
        if mutation == "count":
            bad_rows[0]["operations"] += 1
        if mutation == "date":
            bad_evidence["originals"][0]["downloaded_at"] = "2099-12-31T00:00:00Z"
        if mutation == "rows":
            bad_rows.pop()
        if mutation == "binding":
            bad_evidence["source_binding"]["period"] = "2026M08"
        if mutation == "eligibility":
            bad_rows[0]["agent_eligible"] = True
        if mutation == "provisional":
            bad_rows[0]["source_flight_type_code"] = "N"
        with pytest.raises(ValueError):
            projection_frame(bad_rows, bad_evidence)
    assert len(TARGETS) == 39
    with pytest.raises(ValueError):
        project_file("data/v1/analysis/2026Q3.json", {}, pd.DataFrame())


def test_previous_departures_require_matching_prior_original_and_preserve_independent_evidence():
    before, source = fixture()
    before["routes"][0]["previous"]["departures"] = 30
    with pytest.raises(ValueError, match="Previous.*original"):
        project_network(before, source)
    prior = source.copy()
    prior["period_id"] = "2025M07"
    complete = pd.concat([source, prior], ignore_index=True)
    assert project_network(before, complete)["routes"][0]["previous"]["departures"] is None
    old = before["routes"][0]
    estimate = {
        **old["flight_components"][0],
        "kind": "estimated",
        "source_label": "AeroDataBox",
        "departures": 12,
        "source_hashes": [],
    }
    old["flight_components"].append(estimate)
    old["previous"]["departures"] = 15
    assert project_network(before, source)["routes"][0]["previous"]["departures"] == 15
