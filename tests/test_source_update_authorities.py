"""Retained authority source metrics and native scopes remain distinguishable."""

import csv
import io
import json

import pytest

from src.source_updates import authorities as source

ORIGINAL = {
    "source_system": "international_routes",
    "source_file": "source.json",
    "sha256": "a" * 64,
    "downloaded_at": "2026-09-08T23:45:31Z",
}


def csv_bytes(fields, rows, encoding="utf-8"):
    stream = io.StringIO()
    writer = csv.DictWriter(stream, fieldnames=fields)
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue().encode(encoding)


def caa_inputs(change=None):
    rows = []
    for direction in "AD":
        row = {field: "0" for field in source.CAA_FIELDS}
        row.update(
            reporting_period="202606",
            reporting_airport="HEATHROW",
            origin_destination_country="MEXICO",
            origin_destination="MEXICO CITY",
            airline_name="AEROMEXICO",
            scheduled_charter="S",
            arrival_departure=direction,
            number_flights_matched="30",
            run_date="17/08/2026 10:24",
        )
        rows.append(row)
    if change:
        change(rows)
    return {"csv": (csv_bytes(source.CAA_FIELDS, rows), ORIGINAL)}


def test_caa_reports_matched_unmatched_and_cancelled_separately():
    f, r = source.caa(
        caa_inputs(lambda rows: rows[0].update(actual_flights_unmatched="2", number_flights_cancelled="1")),
        "2026M06",
    )
    assert len(f) == 6 and f.loc[f.metric_key.eq("matched_flights"), "value"].sum() == 60
    assert f.loc[f.metric_key.eq("unmatched_actual_flights"), "value"].sum() == 2
    assert not f.agent_eligible.any() and f.marketing_carrier.isna().all()
    assert r["published_at"] is None and r["generation_dates_as_reported"] == ["17/08/2026 10:24"]


@pytest.mark.parametrize(
    "change",
    [
        lambda rows: rows[0].update(reporting_period="202607"),
        lambda rows: rows[0].update(arrival_departure="X"),
        lambda rows: rows[0].update(reporting_airport="GATWICK"),
        lambda rows: rows[0].update(number_flights_matched=""),
        lambda rows: rows[0].update(actual_flights_unmatched="NaN"),
        lambda rows: rows.append(rows[0]),
        lambda rows: rows.pop(),
    ],
)
def test_caa_wrong_scope_missing_counts_and_native_duplicates_block(change):
    with pytest.raises(ValueError):
        source.caa(caa_inputs(change), "2026M06")


def aena_inputs(change=None):
    result = {}
    for role in ("company_operations", "company_passengers", "market_operations", "market_passengers"):
        company = role.startswith("company_")
        first = (
            "Compañía"
            if company
            else ("Aeropuerto Escala" if role.endswith("passengers") else "Aeropuerto ORI/DES")
        )
        metric = "Operaciones Totales" if role.endswith("operations") else "Pasajeros Totales"
        fields = [first, "Aeropuerto Base", "Mes", metric]
        rows = [
            {
                first: source.AENA_COMPANY if company else source.AENA_MEXICO,
                "Aeropuerto Base": base,
                "Mes": "Enero de 2026",
                metric: "1.234",
            }
            for base in source.AENA_BASES
        ]
        if change:
            change(role, rows, metric)
        original = {**ORIGINAL, "source_system": "aena", "source_file": role + ".csv"}
        result[role] = (csv_bytes(fields, rows, "utf-16"), original)
    return result


def test_aena_keeps_carrier_airport_and_all_carrier_pair_distinct():
    f, r = source.aena(aena_inputs(), "2026M01")
    assert len(f) == 8 and f.value.eq(1234).all()
    assert f.loc[f.observation_scope.eq("carrier_airport"), "counterpart_as_reported"].isna().all()
    assert f.loc[f.observation_scope.eq("all_carrier_airport_pair"), "operator_as_reported"].isna().all()
    assert not r["company_route_join_performed"]


def test_aena_missing_pax_with_explicit_zero_operations_remains_missing():
    def edit(role, rows, metric):
        if role == "company_operations":
            rows[0][metric] = "0"
        if role == "company_passengers":
            rows.pop(0)

    f, r = source.aena(aena_inputs(edit), "2026M01")
    assert len(f) == 7 and len(r["missing_passenger_observations"]) == 1
    assert r["missing_passenger_observations"][0]["value"] is None
    assert f.value.eq(0).sum() == 1


@pytest.mark.parametrize(
    "edit",
    [
        lambda role, rows, metric: rows.pop() if role == "market_passengers" else None,
        lambda role, rows, metric: rows.pop() if role == "company_passengers" else None,
        lambda role, rows, metric: rows.append(rows[0]) if role == "company_operations" else None,
        lambda role, rows, metric: rows[0].update(Mes="Febrero de 2026"),
        lambda role, rows, metric: rows[0].__setitem__(metric, "1,234"),
        lambda role, rows, metric: rows[0].__setitem__(metric, ""),
    ],
)
def test_aena_invalid_missing_or_duplicate_scope_blocks(edit):
    with pytest.raises(ValueError):
        source.aena(aena_inputs(edit), "2026M01")


def anac_row(**changes):
    return dict(
        EMPRESA_NOME="AEROVÍAS DE MÉXICO S.A DE C.V - AEROMÉXICO",
        ANO="2026",
        MES="1",
        GRUPO_DE_VOO="REGULAR",
        NATUREZA="INTERNACIONAL",
        AEROPORTO_DE_ORIGEM_SIGLA="MMMX",
        AEROPORTO_DE_DESTINO_SIGLA="SBGR",
        AEROPORTO_DE_ORIGEM_PAIS="MÉXICO",
        AEROPORTO_DE_DESTINO_PAIS="BRASIL",
        PASSAGEIROS_PAGOS="100",
        ASSENTOS="120",
        DECOLAGENS="1",
        **changes,
    )


def test_anac_consecutive_arrays_consume_all_bytes_and_keep_source_company():
    row = anac_row()
    other = {
        **row,
        "AEROPORTO_DE_ORIGEM_SIGLA": "SBGR",
        "AEROPORTO_DE_DESTINO_SIGLA": "MMMX",
        "AEROPORTO_DE_ORIGEM_PAIS": "BRASIL",
        "AEROPORTO_DE_DESTINO_PAIS": "MÉXICO",
    }
    content = (json.dumps([row]) + "\n" + json.dumps([other])).encode()
    f, r = source.anac({"json": (content, ORIGINAL)}, "2026M01")
    assert len(f) == 6 and r["source_rows_scanned"] == 2
    assert set(f.operator_as_reported) == {row["EMPRESA_NOME"]}
    assert set(f.metric_key) == {"paid_passengers", "seats_as_reported", "departures_as_reported"}
    assert f.source_locator.str.startswith(("record:1/", "record:2/")).all()


@pytest.mark.parametrize("raw", [b"", b"[", b"[{}", b"[{},]", b"[{}]trailing", b"[{}]{}", b"[1]", b"[{} {}]"])
def test_anac_incomplete_or_unconsumed_json_blocks(raw):
    with pytest.raises(ValueError):
        list(source.json_objects(raw))


@pytest.mark.parametrize(
    "changes",
    [
        {"PASSAGEIROS_PAGOS": ""},
        {"ASSENTOS": "NaN"},
        {"DECOLAGENS": "1.5"},
        {"MES": "13"},
        {"NATUREZA": "DOMÉSTICA"},
        {"AEROPORTO_DE_ORIGEM_SIGLA": "UNKNOWN"},
        {"EMPRESA_NOME": "AEROVIAS DE MEXICO UNKNOWN"},
    ],
)
def test_anac_selected_identity_units_and_missing_values_fail_closed(changes):
    row = anac_row()
    row.update(changes)
    with pytest.raises(ValueError):
        source.anac({"json": (json.dumps([row]).encode(), ORIGINAL)}, "2026M01")


def test_anac_native_duplicates_and_wrong_requested_vintage_block():
    row = anac_row()
    with pytest.raises(ValueError):
        source.anac({"json": (json.dumps([row, row]).encode(), ORIGINAL)}, "2026M01")
    with pytest.raises(ValueError):
        source.anac({"json": (json.dumps([row]).encode(), ORIGINAL)}, "2026M02")
