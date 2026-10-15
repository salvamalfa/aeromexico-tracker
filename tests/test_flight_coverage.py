from pathlib import Path
import json

import openpyxl
import pandas as pd
import pytest

from scripts.research.flight_coverage import audit, carrier_key, denominator, official_rows


@pytest.mark.parametrize("header_column", [0, 1, 3])
def test_official_denominator_excludes_subsidiaries_charter_and_unknown_months(tmp_path: Path, header_column):
    path = tmp_path / "official.xlsx"
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.title = "VLOSREG"
    for row in [
        [None] * header_column + ["EMPRESAS NACIONALES / DOMESTIC AIR CARRIERS"],
        [None] * header_column + ["EN SERVICIO REGULAR NACIONAL"],
        ["Aeroméxico (Aerovías de México)", 100, None, 0],
        ["Aeroméxico Connect (Aerolitoral)", 20, None, 0],
        ["Volaris (Concesionaria Vuela Cia de Aviación)", 50, None, 0],
        [None] * header_column + ["EMPRESAS NACIONALES"],
        [None] * header_column + ["EN SERVICIO REGULAR INTERNACIONAL"],
        ["Volaris (Concesionaria Vuela Cia de Aviación)", 40],
        [None] * header_column + ["EMPRESAS EXTRANJERAS"],
        [None] * header_column + ["EN SERVICIO REGULAR INTERNACIONAL"],
        ["Volaris Costa Rica", 900], ["Volaris El Salvador", 800],
    ]:
        sheet.append(row)
    workbook.save(path)
    rows = official_rows(path, 2026, 3)
    values = {(r["carrier"], r["scope"], r["month"]): r["flights"] for r in rows}
    assert denominator(values, "AEROMEXICO", "domestic", ["2026M01"]) == 120
    assert denominator(values, "VOLARIS", "international", ["2026M01"]) == 40
    assert denominator(values, "AEROMEXICO", "domestic", ["2026M02"]) is None
    assert denominator(values, "AEROMEXICO", "domestic", ["2026M03"]) == 0
    assert not any(row["month"] == "2026M04" for row in rows)
    assert carrier_key("Volaris Costa Rica") is None
    assert carrier_key("Volaris El Salvador") is None


def test_coverage_separates_charter_estimates_partial_months_and_source_conflicts(tmp_path):
    site, gold = tmp_path / "site", tmp_path / "gold"
    base = site / "data/v1/flights"
    folder = base / "entities/VOLARIS/international"
    folder.mkdir(parents=True)
    gold.mkdir()
    (base / "quarters.json").write_text(json.dumps({"quarters": [{"period_id": "2026Q2"}]}))
    network = {"observed_months": ["2026M04", "2026M05"], "routes": [
        {"market_key": "GDL<>LAX", "departures": 130, "source_label": "Estados Unidos · BTS T-100",
         "operation_status": "operated_observed", "coverage_note": "Meses: 04, 05 · BTS T-100"},
        {"market_key": "BOG<>MEX", "departures": 70, "source_label": "AFAC + AeroDataBox",
         "operation_status": "estimated_from_existing_seed", "monthly": [
             {"period_id": "2026M06", "departures": 70}]}]}
    (folder / "2026Q2.json").write_text(json.dumps(network))
    pd.DataFrame([{"carrier_key": "VOLARIS", "period_id": month, "route_key": "r", "service_class": service,
                   "source_system": "bts_t100", "departures_performed": flights}
                  for month, service, flights in [("2026M04", "F", 50), ("2026M04", "L", 20),
                                                  ("2026M04", "G", 10), ("2026M05", "F", 50)]]).to_parquet(gold / "fact_route_traffic.parquet")
    pd.DataFrame([{"route_key": "r", "market_key": "GDL<>LAX"}]).to_parquet(gold / "dim_route.parquet")
    pd.DataFrame([{"source_system": "aerocivil", "operator_icao": "AMX", "period_id": "2026M04",
                   "origin_iata": "MEX", "dest_iata": "BOG", "departures": 5}]).to_parquet(
                       gold / "fact_international_route_observations.parquet")
    official = {("VOLARIS", "international", month): 100 for month in ["2026M04", "2026M05", "2026M06"]}
    rows = audit(site, official, gold)
    observed = next(r for r in rows if r["entity"] == "VOLARIS" and r["kind"] == "observed"
                    and r["scope"] == "international")
    assert observed["map_flights"] == 130
    assert observed["comparable_observed_regular_flights"] == 110
    assert observed["observed_minimum_quarter_pct"] == pytest.approx(110 / 3)
    assert observed["observed_share_represented_months_pct"] == 55
    assert observed["pending_calendar_months"] == "2026M06"
    assert all(r["estimated_coverage_pct"] is None for r in rows)
    conflicting = audit(site, {key: 20 for key in official}, gold)
    conflict = next(r for r in conflicting if r["entity"] == "VOLARIS" and r["kind"] == "observed"
                    and r["scope"] == "international")
    assert conflict["observed_minimum_quarter_pct"] is None
    assert conflict["coverage_status"] == "source totals inconsistent"
