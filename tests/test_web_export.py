"""Tests for src/web_export: per-file schema validation, determinism,
loud failure on a missing declared input, and lossless split/recombine.

See docs/arquitectura/auditoria-arquitectura-20260926.md Fase 2 and
src/web_export/README.md.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from src.web_export.executive import export_executive
from src.web_export.flights import export_flights, recombine_flights
from src.web_export.inputs import MissingWebInput, load_web_inputs_config, require_inputs
from src.web_export.writer import dumps_deterministic, write_json


def _load_fixture(name: str) -> dict[str, Any]:
    from src.config import PATHS

    path = PATHS.root / "tests" / "fixtures" / "web" / name
    return json.loads(path.read_text(encoding="utf-8"))


def test_web_inputs_config_declares_the_four_estimate_tables() -> None:
    config = load_web_inputs_config()
    required = set(config["views"]["flights"]["required_for_publish"])
    assert required == {
        "data/gold/fact_route_carrier_domestic_estimate.parquet",
        "data/gold/fact_aeromexico_domestic_capacity_estimate.parquet",
        "data/gold/fact_route_carrier_international_estimate.parquet",
        "data/gold/fact_aeromexico_international_capacity_estimate.parquet",
    }


def test_require_inputs_fails_loudly_when_a_declared_file_is_missing() -> None:
    config = {
        "views": {
            "flights": {
                "required_for_publish": ["data/gold/does_not_exist_fixture.parquet"],
            }
        }
    }
    with pytest.raises(MissingWebInput) as excinfo:
        require_inputs("flights", config)
    message = str(excinfo.value)
    assert "does_not_exist_fixture.parquet" in message
    assert "aeromexico-tracker-data" in message


def test_require_inputs_fails_for_an_undeclared_view() -> None:
    with pytest.raises(MissingWebInput):
        require_inputs("not_a_declared_view", {"views": {}})


def test_deterministic_writer_is_stable_across_two_runs(tmp_path: Path) -> None:
    payload = {"b": 2.0, "a": [3, 1.5, None], "c": {"z": 1, "y": 2}}
    first = write_json(tmp_path / "one" / "out.json", payload)
    second = write_json(tmp_path / "two" / "out.json", payload)
    assert first.read_bytes() == second.read_bytes()
    assert dumps_deterministic(payload) == dumps_deterministic(dict(reversed(list(payload.items()))))


def test_export_flights_writes_schema_valid_split_files(tmp_path: Path) -> None:
    payload = _build_synthetic_raw_flight_payload()
    written = export_flights(payload, tmp_path, skip_input_check=True)
    names = {str(path.relative_to(tmp_path)) for path in written}
    assert "flights/quarters.json" in names
    assert any(name.startswith("flights/international/") for name in names)


def test_export_flights_split_recombines_to_the_same_payload(tmp_path: Path) -> None:
    payload = _build_synthetic_raw_flight_payload()
    export_flights(payload, tmp_path, skip_input_check=True)
    from src.dashboard.flights_html import integration_flight_payload

    expected = integration_flight_payload(payload)
    actual = recombine_flights(tmp_path)
    assert actual == expected


def test_export_executive_writes_schema_valid_file(tmp_path: Path) -> None:
    payload = _load_fixture("executive_sample.json")
    written = export_executive(payload, tmp_path, skip_input_check=True)
    assert written[0] == tmp_path / "executive.json"
    assert json.loads(written[0].read_text(encoding="utf-8")) == payload


def _build_synthetic_raw_flight_payload() -> dict[str, Any]:
    """A minimal build_flight_payload()-shaped dict: enough for
    integration_flight_payload() to run without a warehouse."""

    fixture = _load_fixture("flights_sample.json")
    return {
        **fixture,
        "international_networks": fixture["route_networks"],
    }


@pytest.mark.local_data
def test_real_flights_export_round_trips_exactly(tmp_path: Path, flight_payload: dict[str, Any]) -> None:
    """Splitting and recombining the real embedded payload changes nothing."""

    from src.dashboard.flights_html import integration_flight_payload

    export_flights(flight_payload, tmp_path, skip_input_check=True)
    expected = integration_flight_payload(flight_payload)
    actual = recombine_flights(tmp_path)
    assert actual == expected


@pytest.mark.local_data
def test_real_executive_export_round_trips_exactly(tmp_path: Path, executive_payload: dict[str, Any]) -> None:
    written = export_executive(executive_payload, tmp_path, skip_input_check=True)
    assert json.loads(written[0].read_text(encoding="utf-8")) == executive_payload


@pytest.mark.local_data
def test_real_warehouse_has_all_four_required_flight_inputs() -> None:
    """With the local data restore in place, require_inputs must not raise."""

    require_inputs("flights")
