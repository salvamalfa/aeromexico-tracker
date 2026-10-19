"""Synthetic adversarial cases for the offline candidate auditor."""

import hashlib
import json
from copy import deepcopy

import pandas as pd
import pytest

from scripts.research.flight_gap_options import (
    apply_options,
    captured_json,
    colombia_capture_pair,
    colombia_cells,
    integer,
    replacement_deltas,
    verified_anac,
)

AIRPORTS = {
    "MMMM": {"airport_iata": "MXX", "country": "MX"},
    "SKAA": {"airport_iata": "CAA", "country": "CO"},
    "SKBB": {"airport_iata": "CBB", "country": "CO"},
}


def native(**values):
    return {
        "anio": "2026",
        "mes": "04",
        "aeropuerto_operacion": "SKAA",
        "origen": "MMMM",
        "destino": "SKAA",
        "empresa": "VIV",
        "explotador": "VIV",
        "tipo_vuelo": "S",
        "trafico": "I",
        "tipo_operacion": "LLEGADA",
        "totaloperaciones": "3",
        **values,
    }


def candidate(value=3):
    return {
        "carrier_key": "VIVA_AEROBUS",
        "origin_iata": "MXX",
        "destination_iata": "CAA",
        "period_id": "2026M04",
        "departures": value,
    }


def test_native_grain_and_count_guard():
    with pytest.raises(ValueError, match="count"):
        colombia_cells([native()], AIRPORTS, 2)
    with pytest.raises(ValueError, match="Duplicate"):
        colombia_cells([native(), native()], AIRPORTS, 2)
    # Different commercial companies preserve distinct native records; operator remains VIV.
    cells = colombia_cells([native(), native(empresa="OTHER")], AIRPORTS, 2)
    assert cells[0]["departures"] == 6
    assert cells[0]["source_locators"] == ["record:1", "record:2"]


@pytest.mark.parametrize(
    "values", [{"tipo_vuelo": "N"}, {"trafico": "N"}, {"origen": "SKBB", "tipo_operacion": "LLEGADA"}]
)
def test_nonregular_domestic_and_third_country_do_not_enter(values):
    assert colombia_cells([native(**values)], AIRPORTS, 1) == []


@pytest.mark.parametrize(
    "values",
    [
        {"tipo_operacion": "SALIDA"},
        {"aeropuerto_operacion": "MMMM"},
        {"explotador": "VVC"},
        {"mes": "07"},
        {"origen": "UNKNOWN"},
    ],
)
def test_scope_and_direction_fail_closed(values):
    with pytest.raises(ValueError):
        colombia_cells([native(**values)], AIRPORTS, 1)


@pytest.mark.parametrize("value", [-1, 2.5, "nan", "inf", True])
def test_noninteger_counts_are_not_operations(value):
    with pytest.raises(ValueError):
        integer(value)


def test_capture_hash_must_match_original(tmp_path):
    path = tmp_path / "capture.json"
    path.write_text("[]")
    (tmp_path / "capture.json.meta.json").write_text(json.dumps({"sha256": "wrong"}))
    with pytest.raises(ValueError, match="hash"):
        captured_json(path)


def test_count_query_must_match_capture_scope_and_original_endpoint():
    base = "https://www.datos.gov.co/resource/jh8x-n6h6.json?%24where=scope"
    records = {"source_url": base + "&%24limit=100"}
    count = {"source_url": base + "&%24select=count%28%2A%29"}
    assert colombia_capture_pair(records, count) == 100
    with pytest.raises(ValueError, match="universes"):
        colombia_capture_pair(records, {"source_url": count["source_url"].replace("scope", "other")})
    with pytest.raises(ValueError, match="source"):
        colombia_capture_pair(
            {"source_url": records["source_url"].replace("www.datos.gov.co", "example.com")}, count
        )


def test_zero_replaces_estimate_negative_deltas_kept_absence_untouched():
    key = ("VIVA_AEROBUS", "MXX", "CAA", "2026M04")
    baseline = {key: {"kind": "estimated", "departures": 5}}
    assert replacement_deltas([], baseline) == []
    changes = replacement_deltas([candidate(0)], baseline)
    assert changes[0]["delta"] == -5
    rows = [
        {
            "entity": "VIVA_AEROBUS",
            "scope": "combined",
            "period_id": "2026Q2",
            "observed_flights": 0,
            "estimated_flights": 9,
            "strict_observed_regular_flights": 0,
            "official_regular_flights": 20,
        }
    ]
    before = deepcopy(rows)
    result = apply_options(rows, changes, [])
    assert rows == before
    assert result[0]["represented_observed_plus_estimated_flights"] == 4
    assert result[0]["official_regular_flights"] == 20
    assert result[0]["target_95_required_flights"] == 19


def test_duplicate_and_observed_source_conflicts_require_review():
    with pytest.raises(ValueError, match="Duplicate"):
        replacement_deltas([candidate(), candidate()], {})
    key = ("VIVA_AEROBUS", "MXX", "CAA", "2026M04")
    with pytest.raises(ValueError, match="conflict"):
        replacement_deltas([candidate()], {key: {"kind": "observed", "source_label": "Other"}})


def test_regularity_proof_changes_strict_only_and_not_other_periods():
    row = {
        "entity": "VIVA_AEROBUS",
        "scope": "combined",
        "period_id": "2026M04",
        "observed_flights": 4,
        "estimated_flights": 2,
        "strict_observed_regular_flights": 1,
        "official_regular_flights": 10,
    }
    result = apply_options([row, {**row, "period_id": "2026M05"}], [], [candidate(3)])
    assert result[0]["represented_observed_plus_estimated_flights"] == 6
    assert result[0]["strict_regular_observed_plus_estimated_flights"] == 6
    assert result[1]["strict_regular_observed_plus_estimated_flights"] == 3


def test_candidate_does_not_relabel_baseline_route_counts_or_source_inventory():
    row = {
        "entity": "VIVA_AEROBUS",
        "scope": "combined",
        "period_id": "2026M04",
        "observed_flights": 4,
        "estimated_flights": 2,
        "strict_observed_regular_flights": 1,
        "official_regular_flights": 10,
        "all_exported_routes": 8,
        "source_labels": "Old",
        "initial_top12_routes": 8,
        "component_source_hashes": "oldhash",
    }
    candidate_row = apply_options([row], [], [])[0]
    for name in ("all_exported_routes", "source_labels", "initial_top12_routes", "component_source_hashes"):
        assert name not in candidate_row
        assert name in row
    assert candidate_row["snapshot"] == "candidate_not_activated"


def anac_fixture(tmp_path, **overrides):
    raw = {
        "EMPRESA_NOME": "AEROVIAS DE MEXICO",
        "GRUPO_DE_VOO": "REGULAR",
        "NATUREZA": "INTERNACIONAL",
        "ANO": 2026,
        "MES": 4,
        "AEROPORTO_DE_ORIGEM_SIGLA": "MMMM",
        "AEROPORTO_DE_DESTINO_SIGLA": "SBBB",
        "DECOLAGENS": 3,
        **overrides,
    }
    path = tmp_path / "anac.json"
    path.write_text(json.dumps([raw]))
    sha = hashlib.sha256(path.read_bytes()).hexdigest()
    gold = pd.DataFrame(
        [
            {
                "source_system": "anac",
                "period_id": "2026M04",
                "source_file": path.name,
                "source_hash": sha,
                "source_locator": "record:1",
                "operator_icao": "AMX",
                "origin_icao": "MMMM",
                "dest_icao": "SBBB",
                "origin_iata": "MXX",
                "dest_iata": "BBB",
                "departures": 3,
            }
        ]
    )
    baseline = {
        ("AEROMEXICO", "MXX", "BBB", "2026M04"): {
            "kind": "observed",
            "source_label": "Brasil ANAC",
            "departures": 3,
            "source_hashes": [sha],
        }
    }
    return gold, baseline


def test_original_anac_class_operator_count_and_hash_are_required(tmp_path):
    gold, baseline = anac_fixture(tmp_path)
    assert verified_anac(gold, tmp_path, baseline)[0]["departures"] == 3
    for field, value in (
        ("GRUPO_DE_VOO", "NAO REGULAR"),
        ("EMPRESA_NOME", "OTHER"),
        ("DECOLAGENS", 4),
        ("MES", 5),
        ("NATUREZA", "DOMESTICA"),
    ):
        gold, baseline = anac_fixture(tmp_path, **{field: value})
        with pytest.raises(ValueError, match="does not prove"):
            verified_anac(gold, tmp_path, baseline)
    gold, baseline = anac_fixture(tmp_path)
    (tmp_path / "anac.json").write_text("[]")
    with pytest.raises(ValueError, match="hash"):
        verified_anac(gold, tmp_path, baseline)


@pytest.mark.parametrize("locator", ["record:0", "record:-1", "1", "record:2", "record:01"])
def test_anac_locator_is_one_based_bounded_and_canonical(tmp_path, locator):
    gold, baseline = anac_fixture(tmp_path)
    gold.loc[0, "source_locator"] = locator
    with pytest.raises(ValueError, match="locator"):
        verified_anac(gold, tmp_path, baseline)


def test_anac_original_cannot_be_reused_for_another_gold_row(tmp_path):
    gold, baseline = anac_fixture(tmp_path)
    with pytest.raises(ValueError, match="Duplicate ANAC original"):
        verified_anac(pd.concat([gold, gold], ignore_index=True), tmp_path, baseline)
