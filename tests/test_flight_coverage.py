from pathlib import Path

import openpyxl

from scripts.research.flight_coverage import carrier_key, denominator, official_rows


def test_official_denominator_excludes_subsidiaries_charter_and_unknown_months(tmp_path: Path):
    path = tmp_path / "official.xlsx"
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.title = "VLOSREG"
    for row in [
        ["EMPRESAS NACIONALES / DOMESTIC AIR CARRIERS"],
        ["EN SERVICIO REGULAR NACIONAL"],
        ["Aeroméxico (Aerovías de México)", 100, None, 0],
        ["Aeroméxico Connect (Aerolitoral)", 20, None, 0],
        ["Volaris (Concesionaria Vuela Cia de Aviación)", 50, None, 0],
        ["EMPRESAS NACIONALES"], ["EN SERVICIO REGULAR INTERNACIONAL"],
        ["Volaris (Concesionaria Vuela Cia de Aviación)", 40],
        ["EMPRESAS EXTRANJERAS"], ["EN SERVICIO REGULAR INTERNACIONAL"],
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
