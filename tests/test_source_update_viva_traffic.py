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
    assert receipt["comparison_rows"] == 8 and receipt["reported_document_lag_days"] == 7
    assert receipt["release_lag_days"] is None and receipt["published_date"] is None
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


def current_text():
    # Synthetic contract fixture; the actual two-page PDF stays in private Bronze.
    page = """Ciudad de México, 9 de octubre de 2026 –
Viva anunció hoy sus resultados preliminares de tráfico correspondientes a septiembre de 2026
asientos por milla disponibles (ASMs)
Cifras mensuales Cifras acumuladas (Ene-Sep)
Sep 2026 Sep 2025 Var% 2026 2025 Var%
Pasajeros (itinerario & chárter, miles)
1,000 1,200 -16.7% 8,000 10,000 -20%
Nacional 800 900 -11.1% 7,000 8,000 -12.5%
Internacional 200 300 -33.3% 1,000 2,000 -50%
Factor de Ocupación (itinerario, RPM/ASM)
90% 85% 5 pp 88% 85% 3 pp
Nacional 91% 86% 5 pp 89% 87% 2 pp
Internacional 80% 75% 5 pp 78% 76% 2 pp
RPMs (itinerario & chárter, millones)
900 1,000 -10% 8,000 9,000 -11.1%
Nacional 800 900 -11.1% 7,000 8,000 -12.5%
Internacional 100 100 0% 1,000 1,000 0%
ASMs (itinerario & chárter, millones)
1,000 1,200 -16.7% 9,000 11,000 -18.2%
Nacional 850 1,000 -15% 7,500 9,000 -16.7%
Internacional 150 200 -25% 1,500 2,000 -25%
Reporte de Tráfico | Septiembre 2026
"""
    glossary = """Glosario
Pasajeros: Clientes que adquirieron su boleto para volar en el mes del reporte
indistintamente si efectúan o no su vuelo.
ASMs (por sus siglas en inglés)
capacidad de asientos de la aeronave multiplicada por el número de millas.
Factor de Ocupación: se calcula dividiendo los pasajeros pago millas (RPMs) de itinerario
por asientos disponibles por millas (ASMs) de itinerario.
RPMs: “Pasajeros pago millas”
Viva es una aerolínea mexicana de ultra bajo costo
"""
    return [page, glossary]


def test_current_monthly_segments_units_and_preliminary_are_source_faithful():
    frame, details = source.current_texts(current_text(), "2026M09", ORIGINAL)
    assert len(frame) == 24 and not frame.duplicated(source.GRAIN).any()
    assert set(frame.period_id) == {"2026M09", "2025M09"}
    assert set(frame.segment) == {"total", "domestic", "international"}
    current = frame.loc[frame.period_id.eq("2026M09") & frame.segment.eq("total")].set_index("metric_key")
    assert current.loc["passengers_booked", "value"] == 1000
    assert current.loc["passengers_booked", "unit"] == "thousand booked passengers"
    assert current.loc["asm", "unit"] == "million seat-miles"
    assert current.loc["rpm", "unit"] == "million passenger-miles"
    assert frame.is_preliminary.all() and frame.reporting_status.eq("preliminary").all()
    assert details["native_reconciliations"] == 16
    assert details["reported_document_lag_days"] == 9
    assert details["release_lag_days"] is None and details["published_date"] is None
    assert details["excluded_columns"] == [
        "year_to_date",
        "reported_changes",
    ]
    assert details["first_available_at"] is None and not details["agent_eligible"]
    assert "itinerary-only" in details["load_factor_policy"]


@pytest.mark.parametrize(
    "before,after",
    [
        ("septiembre de 2026", "agosto de 2026"),
        ("Sep 2026 Sep 2025", "Sep 2025 Sep 2026"),
        ("Cifras mensuales Cifras acumuladas", "Cifras acumuladas Cifras mensuales"),
        ("itinerario & chárter, miles", "itinerario & chárter, millones"),
        ("itinerario, RPM/ASM", "itinerario & chárter, RPM/ASM"),
        ("ASMs (itinerario & chárter, millones)", "ASKs (itinerario & chárter, millones)"),
        ("Nacional 800 900", "Nacional 8,000 900"),
        ("Internacional 200 300", "Internacional N/D 300"),
        ("1,000 1,200 -16.7%", "1.000 1,200 -16.7%"),
        ("90% 85%", "101% 85%"),
        ("90% 85%", "10% 85%"),
        ("9 de octubre de 2026", "9 de septiembre de 2026"),
        ("resultados preliminares", "resultados auditados"),
    ],
)
def test_current_wrong_month_columns_scope_missing_values_and_reconciliation_block(before, after):
    pages = current_text()
    pages[0] = pages[0].replace(before, after)
    with pytest.raises(ValueError):
        source.current_texts(pages, "2026M09", ORIGINAL)


def test_current_glossary_and_entity_identity_are_required():
    pages = current_text()
    pages[1] = pages[1].replace("indistintamente si efectúan o no su vuelo.", "solo si volaron.")
    with pytest.raises(ValueError, match="glossary"):
        source.current_texts(pages, "2026M09", ORIGINAL)
    pages = current_text()
    pages[1] = pages[1].replace("número de millas.", "número de kilómetros.")
    with pytest.raises(ValueError, match="mile units"):
        source.current_texts(pages, "2026M09", ORIGINAL)


def test_bmv_explicit_selection_requires_content_verification_and_keeps_actual_url():
    url = "https://www.bmv.com.mx/docs-pub/eventemi/eventemi_1594478_1.pdf"
    selection = source.selection_for_url(url, "2026M09")
    assert selection["items"][0]["url"] == url
    assert selection["items"][0]["period"] == "2026M09"
    assert selection["discovery"]["content_period_verification"] == "required_before_certification"
    with pytest.raises(ValueError, match="PDF URL"):
        source.selection_for_url("https://www.bmv.com.mx/es/emisoras/eventosrelevantes/GVIVA", "2026M09")
    with pytest.raises(ValueError, match="catalogue hosts"):
        source.selection_for_url("https://investorcloud.s3.amazonaws.com/viva.pdf", "2026M09")


def test_current_candidate_contract_rejects_unit_or_segment_tampering():
    frame = source.current_texts(current_text(), "2026M09", ORIGINAL)[0]
    frame.loc[frame.metric_key.eq("asm"), "unit"] = "million seat-km"
    with pytest.raises(ValueError, match="never relabel"):
        source.validate_current(frame)
    frame = source.current_texts(current_text(), "2026M09", ORIGINAL)[0]
    frame.loc[0, "segment"] = "unknown"
    with pytest.raises(ValueError, match="contract changed"):
        source.validate_current(frame)
    frame = source.current_texts(current_text(), "2026M09", ORIGINAL)[0]
    frame.loc[frame.metric_key.eq("load_factor_itinerary"), "value"] = 101
    with pytest.raises(ValueError, match="domain changed"):
        source.validate_current(frame)
