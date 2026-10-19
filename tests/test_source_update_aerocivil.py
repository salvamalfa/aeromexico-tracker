"""Aerocivil bounded query, source count, native grain and operations-only tests."""

from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
import json
import shutil
from uuid import uuid4

import httpx
import pandas as pd
import pytest

from src.common.storage import save_bronze
from src.source_updates import aerocivil
from src.source_updates.catalog import ROOT
from src.source_updates.collection import collect


def row(**changes):
    return {
        "anio": "2026",
        "mes": "07",
        "aeropuerto_operacion": "SKBO",
        "origen": "MMMX",
        "destino": "SKBO",
        "empresa": "AMX",
        "explotador": "AMX",
        "tipo_vuelo": "S",
        "trafico": "I",
        "tipo_operacion": "LLEGADA",
        "totaloperaciones": "94",
        **changes,
    }


AIRPORTS = pd.DataFrame(
    [
        {"ident": "MMMX", "iata_code": "MEX", "iso_country": "MX"},
        {"ident": "SKBO", "iata_code": "BOG", "iso_country": "CO"},
    ]
)
ORIGINAL = {
    "sha256": "a" * 64,
    "source_file": "aerocivil.json",
    "source_url": "https://www.datos.gov.co/resource/jh8x-n6h6.json",
    "downloaded_at": "2026-10-19T10:00:00Z",
}


def test_normalize_counts_operations_and_keeps_unsupported_metrics_null():
    data = [
        row(),
        row(origen="SKBO", destino="MMMX", tipo_operacion="SALIDA", totaloperaciones="93"),
        row(tipo_vuelo="N", totaloperaciones="2"),
    ]
    frame, result = aerocivil.normalize(data, "2026M07", ORIGINAL, AIRPORTS)
    assert result["accepted_rows"] == 2 and result["reported_operations_under_selected_codes"] == 187
    assert result["excluded"] == [
        {
            "source_locator": "record:3",
            "reason": "outside_selected_literal_flight_S_traffic_I_codes",
            "operations": 2,
        }
    ]
    assert frame[["passengers", "seats", "departures", "load_factor"]].isna().all().all()
    assert set(frame.metric_key) == {"operations"} and not frame.agent_eligible.any()
    assert frame.marketing_carrier.isna().all()
    assert frame.commercial_designator_as_reported.eq("AMX").all()


def test_explicit_zero_operation_is_preserved_and_unknown_operator_is_not_zero():
    frame, result = aerocivil.normalize([row(totaloperaciones="0")], "2026M07", ORIGINAL, AIRPORTS)
    assert len(frame) == 1 and frame.operations.iloc[0] == 0
    assert result["operators_present"] == ["AMX"] and result["missing_operator_is_not_zero"]


@pytest.mark.parametrize("commercial", [None, "", "missing"])
def test_optional_derived_commercial_designator_does_not_invent_a_marketer(commercial):
    raw = row(empresa=commercial)
    if commercial == "missing":
        raw.pop("empresa")
    frame, _ = aerocivil.normalize([raw], "2026M07", ORIGINAL, AIRPORTS)
    assert frame.marketing_carrier.isna().all() and frame.commercial_designator_as_reported.isna().all()
    assert (
        "literal" in frame.metric_definition.iloc[0] and "legend pending" in frame.metric_definition.iloc[0]
    )


def test_ambiguous_selected_iata_and_unrepresentable_count_block():
    ambiguous = pd.concat(
        [AIRPORTS, pd.DataFrame([{"ident": "OTHER", "iata_code": "BOG", "iso_country": "CO"}])]
    )
    with pytest.raises(ValueError, match="IATA reference is ambiguous"):
        aerocivil.normalize([row()], "2026M07", ORIGINAL, ambiguous)
    with pytest.raises(ValueError):
        aerocivil.normalize([row(totaloperaciones=str(2**53))], "2026M07", ORIGINAL, AIRPORTS)
    _, result = aerocivil.normalize(
        [row(totaloperaciones=str(2**53 - 1)), row(empresa="OTHER", totaloperaciones="2")],
        "2026M07",
        ORIGINAL,
        AIRPORTS,
    )
    assert result["reported_operations_under_selected_codes"] == 2**53 + 1


@pytest.mark.parametrize(
    "changes",
    [
        {"anio": "2025"},
        {"mes": "08"},
        {"explotador": "OTHER"},
        {"tipo_vuelo": "UNKNOWN"},
        {"trafico": "UNKNOWN"},
        {"origen": "ZZZZ"},
        {"aeropuerto_operacion": "MMMX"},
        {"tipo_operacion": "SALIDA"},
        {"totaloperaciones": ""},
        {"totaloperaciones": "NaN"},
        {"totaloperaciones": "-1"},
        {"totaloperaciones": "1.5"},
        {"totaloperaciones": "1e2"},
        {"totaloperaciones": None},
    ],
)
def test_source_query_identity_direction_and_missing_values_fail_closed(changes):
    with pytest.raises(ValueError):
        aerocivil.normalize([row(**changes)], "2026M07", ORIGINAL, AIRPORTS)


def test_native_duplicates_extra_schema_and_missing_airport_reference_block():
    with pytest.raises(ValueError, match="duplicate"):
        aerocivil.normalize([row(), row()], "2026M07", ORIGINAL, AIRPORTS)
    with pytest.raises(ValueError, match="schema changed"):
        aerocivil.normalize([row(new_column="new")], "2026M07", ORIGINAL, AIRPORTS)
    with pytest.raises(ValueError, match="absent"):
        aerocivil.normalize([row()], "2026M07", ORIGINAL, AIRPORTS.iloc[:1])
    with pytest.raises(ValueError, match="Unique OurAirports"):
        aerocivil.normalize([row()], "2026M07", ORIGINAL, pd.concat([AIRPORTS, AIRPORTS]))


def test_recipe_is_explicit_one_month_and_three_bounded_requests():
    selection = aerocivil.recipe("2026M07")
    assert selection["bounds"]["base_requests"] == 3 and selection["bounds"]["maximum_rows"] == 1000
    assert [item["entity"] for item in selection["items"]] == ["count_before", "rows", "count_after"]
    with pytest.raises(ValueError):
        aerocivil.recipe("2026Q3")


@pytest.fixture
def workspace():
    path = ROOT / "tmp/source-updates" / ("aerocivil-test-" + uuid4().hex)
    yield path
    if path.exists():
        shutil.rmtree(path)


def cutoff():
    return (datetime.now(UTC) + timedelta(minutes=1)).isoformat()


def capture(workspace, *, after_count=1, data=None):
    raw = [row()] if data is None else data
    calls = []

    class Client:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def request(self, method, url, **kwargs):
            calls.append(url)
            payload = (
                raw if len(calls) == 2 else [{"row_count": str(after_count if len(calls) == 3 else len(raw))}]
            )
            return httpx.Response(200, json=payload, request=httpx.Request(method, url))

    receipt = collect(aerocivil.recipe("2026M07"), workspace, execute=True, client_factory=Client)
    save_bronze(
        AIRPORTS.to_csv(index=False).encode(),
        "ourairports",
        "airports",
        "retained",
        "csv",
        "https://davidmegginson.github.io/ourairports-data/airports.csv",
        "manual",
        bronze_root=workspace / "data/bronze",
        relative_dir="reference",
    )
    metadata = {
        "id": "jh8x-n6h6",
        "description": "EMPRESA y EXPLOTADOR callsign matrícula trimestralmente",
        "columns": [{"fieldName": "totaloperaciones", "description": "Conteo volumétrico de movimientos"}],
    }
    save_bronze(
        json.dumps(metadata).encode(),
        "aerocivil",
        "dataset_metadata",
        "current",
        "json",
        aerocivil.METADATA_URL,
        "manual",
        bronze_root=workspace / "data/bronze",
        relative_dir="metadata",
    )
    return receipt["run_id"]


def test_default_preview_writes_nothing(workspace):
    assert aerocivil.run(workspace, "2026M07", cutoff(), "a" * 32)["network_requests"] == 0
    assert not workspace.exists()


def test_candidate_reconstructs_gold_and_reference_lineage_without_network(workspace):
    receipt = capture(workspace)
    result = aerocivil.run(workspace, "2026M07", cutoff(), receipt, execute=True)
    assert result["status"] == "checks_passed" and result["lineage"]["artifact_count"] == 4
    assert result["lineage"]["records_expected"] == 1 and result["source_counts"] == [1, 1]
    assert result["published_at"] is None and result["release_lag_days"] is None
    frame = pd.read_parquet(workspace / "data/gold" / (aerocivil.TABLE + ".parquet"))
    assert frame.operations.iloc[0] == 94 and frame.departures.isna().all()
    before = {str(p): p.read_bytes() for p in workspace.rglob("*") if p.is_file()}
    checked = aerocivil.run(workspace, "2026M07", cutoff(), receipt, check=True)
    assert checked["output_sha256"] == result["output_sha256"]
    assert before == {str(p): p.read_bytes() for p in workspace.rglob("*") if p.is_file()}
    with pytest.raises(ValueError, match="immutable"):
        aerocivil.run(workspace, "2026M07", cutoff(), receipt, execute=True)


def test_truncated_or_changing_count_never_writes_gold(workspace):
    receipt = capture(workspace, after_count=2)
    with pytest.raises(ValueError, match="changing source count"):
        aerocivil.run(workspace, "2026M07", cutoff(), receipt, execute=True)
    assert not (workspace / "data/gold").exists()


def test_relabelled_allowed_url_receipt_is_detected(workspace):
    receipt = capture(workspace)
    aerocivil.run(workspace, "2026M07", cutoff(), receipt, execute=True)
    path = workspace / "receipts" / f"collection-{receipt}.json"
    changed = json.loads(path.read_text())
    changed["items"][0]["response_url"] = "https://www.datos.gov.co/another"
    path.write_text(json.dumps(changed))
    with pytest.raises(ValueError, match="collection receipt changed"):
        aerocivil.run(workspace, "2026M07", cutoff(), receipt, check=True)


def test_modified_gold_and_reference_are_detected(workspace):
    receipt = capture(workspace)
    aerocivil.run(workspace, "2026M07", cutoff(), receipt, execute=True)
    path = workspace / "data/gold" / (aerocivil.TABLE + ".parquet")
    frame = pd.read_parquet(path)
    frame["agent_eligible"] = True
    frame.to_parquet(path, index=False)
    with pytest.raises(ValueError, match="differs from its originals"):
        aerocivil.run(workspace, "2026M07", cutoff(), receipt, check=True)
    original = next((workspace / "data/bronze/reference").glob("*.csv"))
    original.write_text("changed")
    with pytest.raises(ValueError, match="SHA-256 mismatch"):
        aerocivil.run(workspace, "2026M07", cutoff(), receipt, check=True)


def test_competing_acceptance_at_writer_entry_is_not_overwritten(workspace, monkeypatch):
    receipt = capture(workspace)
    real_writer = aerocivil.writer
    accepted = workspace / "receipts/aerocivil-2026M07.json"

    @contextmanager
    def competing(path):
        with real_writer(path):
            accepted.write_text("accepted by another writer")
            yield

    monkeypatch.setattr(aerocivil, "writer", competing)
    with pytest.raises(ValueError, match="immutable"):
        aerocivil.run(workspace, "2026M07", cutoff(), receipt, execute=True)
    assert accepted.read_text() == "accepted by another writer" and not (workspace / "data/gold").exists()
