"""Contract fixtures for historical Viva traffic; real extraction receipt is private."""

import pandas as pd
import pytest

from src.source_updates import retained
from src.source_updates import viva_traffic as source

ORIGINAL = {
    "source_system": "viva_ir",
    "source_file": "synthetic-contract.pdf",
    "sha256": "a" * 64,
    "downloaded_at": "2026-10-21T00:30:00Z",
}


def text():
    return """Cifras Mensuales de Pasajeros: noviembre 2021
VIVA AEROBUS REPORTA RESULTADOS MENSUALES DE TRÁFICO
Ciudad de México, 07 de diciembre 2021
INFORMACIÓN MENSUAL
Concepto Mensual Year to Date (enero – noviembre)
Noviembre 2021 Noviembre 2020 VAR Noviembre 2019 VAR Octubre 2021 VAR 2021 2020 VAR 2019 VAR
Pasajeros 1,000 800 25% 600 66.7% 900 11.1% 8,000 6,000 33.3% 5,000 60%
Factor de Ocupación (RPK/ASK) 88% 80% 8 pp 70% 18 pp 85% 3 pp 83% 81% 2 pp 80% 3 pp
RPK's (millones) 900 800 12.5% 700 28.6% 850 5.9% 8,000 7,000 14.3% 6,000 33.3%
ASK's (millones) 1,000 900 11.1% 800 25% 950 5.3% 9,000 8,000 12.5% 7,000 28.6%
*NOTA: Synthetic values to test contract; not a source capture.
Glosario
Pasajeros: Personas que adquirieron su boleto para volar en el mes del reporte
indistintamente si efectúan o no su vuelo
Factor de ocupación: Porcentaje de asientos reservados en una aeronave o flota
en un determinado periodo de tiempo
ASK (Available Seat Kilometers / Asientos disponibles por kilómetro)
RPK (Revenue Passenger Kilometers / Ingresos Pasajero Kilómetro)
"""


def test_historical_native_units_and_booked_scope_do_not_become_flown_or_asm():
    frame, receipt = source.texts([text()], "2021M11", ORIGINAL)
    assert len(frame) == 12 and receipt["monthly_rows"] == 4
    assert receipt["comparison_rows"] == 8 and receipt["release_lag_days"] == 7
    assert set(frame.period_id) == {"2021M11", "2020M11", "2019M11"}
    current = frame[frame.period_id.eq("2021M11")].set_index("metric_key")
    assert current.loc["passengers_booked", "value"] == 1000
    assert current.loc["passengers_booked", "definition"].endswith("not_necessarily_flown")
    assert current.loc["ask", "unit"] == "million seat-km"
    assert current.loc["rpk", "unit"] == "million passenger-km"
    assert current.loc["load_factor_reserved", "value"] == 88
    assert not receipt["agent_eligible"] and receipt["activation"] == "none"
    assert receipt["current_source_availability"] == "not_certified_by_historical_layout"
    assert retained.spec("viva_traffic")["grain"] == source.GRAIN


@pytest.mark.parametrize(
    "before,after",
    [
        ("noviembre 2021", "septiembre 2026"),
        ("Noviembre 2021 Noviembre 2020", "Noviembre 2020 Noviembre 2021"),
        ("Year to Date", "Monthly"),
        ("kilómetro", "milla"),
        ("indistintamente si efectúan o no su vuelo", "solo si efectuaron el vuelo"),
        ("Pasajeros 1,000", "Pasajeros N/D"),
        ("Pasajeros 1,000", "Pasajeros 1.000"),
        ("Pasajeros 1,000", "Pasajeros 1,,000"),
        ("Pasajeros 1,000", "Pasajeros -1,000"),
        ("(RPK/ASK) 88%", "(RPK/ASK) 101%"),
        ("RPK's (millones) 900", "RPK's (millones) 9,000"),
        ("07 de diciembre 2021", "07 de noviembre 2021"),
    ],
)
def test_schema_units_missing_values_and_semantic_changes_block(before, after):
    with pytest.raises(ValueError):
        source.texts([text().replace(before, after)], "2021M11", ORIGINAL)


def test_same_row_twice_blocks_and_current_layout_is_never_certified_from_history():
    duplicate = text().replace(
        "Factor de Ocupación (RPK/ASK) 88%",
        "Pasajeros 1,000 800 25% 600 66.7% 900 11.1% 8,000 6,000 33.3% 5,000 60%\n"
        "Factor de Ocupación (RPK/ASK) 88%",
    )
    with pytest.raises(ValueError, match="Duplicate"):
        source.texts([duplicate], "2021M11", ORIGINAL)
    with pytest.raises(ValueError, match="current edition requires"):
        source.texts([text()], "2026M09", ORIGINAL)
    with pytest.raises(ValueError, match="one-page"):
        source.texts([text(), "extra"], "2021M11", ORIGINAL)


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -1])
def test_nonfinite_or_negative_candidate_values_block(value):
    frame = source.texts([text()], "2021M11", ORIGINAL)[0]
    frame.loc[0, "value"] = value
    with pytest.raises(ValueError):
        source.validate(frame)


def test_selector_never_constructs_future_url_or_changes_source_policy(tmp_path):
    catalog = tmp_path / "catalog.html"
    url = "https://cdn.investorcloud.net/VivaAerobus/InformacionFinanciera/SalaPrensa/2021-12-07-Trafico-noviembre-2021.pdf"
    catalog.write_text(f'<a href="{url}">November report</a>')
    selected = source.select(catalog, "2021M11", catalog_url="https://ri.vivaaerobus.com/reportes")
    assert selected["items"][0]["url"] == url
    assert selected["items"][0]["source_system"] == "viva_ir"
    with pytest.raises(ValueError, match="absent or ambiguous"):
        source.select(catalog, "2026M09", catalog_url="https://ri.vivaaerobus.com/reportes")
    denied = "https://investorcloud.s3.amazonaws.com/VivaAerobus/InformacionFinanciera/SalaPrensa/2026-10-09-Trafico-septiembre-2026.pdf"
    catalog.write_text(f'<a href="{denied}">September report</a>')
    with pytest.raises(ValueError, match="catalogue hosts"):
        source.select(catalog, "2026M09", catalog_url="https://ri.vivaaerobus.com/reportes")


def test_deterministic_reparse_of_contract_fixture():
    first = source.texts([text()], "2021M11", ORIGINAL)
    second = source.texts([text()], "2021M11", ORIGINAL)
    pd.testing.assert_frame_equal(first[0], second[0], check_exact=True)
    assert first[1] == second[1]
