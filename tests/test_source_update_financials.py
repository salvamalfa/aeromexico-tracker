"""AM quarter columns and actual ASM-mile units cannot become YTD or ASK."""

import pytest

from src.source_updates import financials as source

ORIGINAL = {
    "source_system": "aeromexico_ir",
    "source_file": "q2.pdf",
    "sha256": "a" * 64,
    "downloaded_at": "2026-09-04T20:19:31Z",
}


def pages():
    first = "Aeroméxico reporta resultados preliminares al segundo trimestre 2026 trimestre concluido el 30 de junio de 2026 La Compañía ha utilizado dólares estadounidenses, su moneda funcional, como moneda de presentación para estos estados financieros consolidados. Todas las cifras están expresadas en millones de dólares estadounidenses, a menos que se indique lo contrario. asientos-milla disponibles (ASMs) Ciudad de México, a 13 de julio de 202 6 -"
    header = "Tres meses terminados el 30 de junio Seis meses terminados el 30 de junio 2026 2025 Var. % 2026 2025 Var. %\n"
    statement = "Estados Consolidados de Resultados y Otros Resultados Integrales (No Auditados)\n" + header
    statement += "\n".join(
        [
            "Total de ingresos 1,479 1,314 12.6% 2,821 2,498 12.9%",
            "Total gastos de operación 1,411 1,084 30.3% 2,611 2,125 22.8%",
            "Utilidad de operación 68 230 - 210 372 -",
            "Utilidad neta (58) 68 - (47) 90 -",
            "Utilidad antes de impuestos a la utilidad (68) 85 - (55) 112 -",
            "Impuesto a la utilidad (10) 17 - (8) 22 -",
            "Combustible 494 274 - 809 560 -",
            "Fuerza de trabajo 316 278 - 624 529 -",
            "Mantenimiento 78 50 - 146 104 -",
            "Depreciación y amortización 193 180 - 382 353 -",
            "Renta de equipo de vuelo 4 3 - 8 8 -",
        ]
    )
    summary = (
        "INDICADORES FINANCIEROS Y OPERATIVOS\n"
        + header
        + "Principales Indicadores Financieros 2026 2025 Var. 2026 2025 Var.\n"
    )
    summary += "\n".join(
        [
            "UAFIDAR ajustada(1) 264 410 - 600 729 -",
            "Margen UAFIDAR ajustado(1) (% de\ningresos) 17.9% 31.2% - 21.3% 29.2% -",
            "Margen de operación (% de ingresos) 4.6% 17.5% - 7.4% 14.9% -",
            "Principales Indicadores Operativos 2026 2025 Var. 2026 2025 Var.\nASMs totales (millones) 9,256 9,080 - 17,853 17,777 -",
            "RPMs totales (millones) 7,851 7,777 - 15,106 14,935 -",
            "Factor de ocupación (itinerario %) 84.9% 85.7% - 84.7% 84.0% -",
            "Pasajeros ('000) 6,014 6,180 - 11,805 12,057 -",
            "Litros de combustible (miles) 444,693 443,893 - 855,667 865,751 -",
            "Costo total excl. combustible / ASM\n(centavos de USD) 10.0 8.9 - 10.1 8.8 -",
        ]
    )
    return [first, statement, summary]


def test_current_quarter_source_units_preliminary_and_accounting_reconciliations():
    f, r = source.texts(pages(), ORIGINAL, "2026Q2")
    assert len(f) == 20 and r["statement_accounting_checks"] == 2
    metrics = f.set_index("metric_key")
    assert (
        metrics.loc["casm_ex_fuel", "value"] == 10
        and metrics.loc["casm_ex_fuel", "unit"] == "USD cents per ASM-mile"
    )
    assert metrics.loc["asm", "value"] == 9256 and metrics.loc["net_income", "value"] == -58
    assert not {"cask_ex_fuel", "ask"}.intersection(metrics.index)
    assert f.is_preliminary.all() and f.is_unaudited.all() and f.not_ytd.all()
    assert not f.normalized_unit_conversion_performed.any() and r["ytd_columns_imported"] == 0


@pytest.mark.parametrize(
    "page,old,new",
    [
        (0, "segundo trimestre 2026", "tercer trimestre 2026"),
        (0, "preliminares", "finales"),
        (0, "millones de dólares estadounidenses", "millones de pesos"),
        (1, "2026 2025 Var. %", "2025 2026 Var. %"),
        (1, "Total de ingresos 1,479", "Total de ingresos 2,821"),
        (1, "Impuesto a la utilidad (10)", "Impuesto a la utilidad 10"),
        (1, "Combustible 494", "Combustible 0,,494"),
        (2, " / ASM", " / ASK"),
        (2, "ASMs totales", "ASKs totales"),
        (2, "17.9%", "NaN"),
        (2, "Factor de ocupación (itinerario %) 84.9%", "Factor de ocupación (itinerario %) 184.9%"),
    ],
)
def test_wrong_currency_column_order_denominator_missing_or_unreconciled_cells_block(page, old, new):
    raw = pages()
    raw[page] = raw[page].replace(old, new)
    with pytest.raises(ValueError):
        source.texts(raw, ORIGINAL, "2026Q2")


def test_new_quarter_and_duplicate_statement_are_not_silently_accepted():
    with pytest.raises(ValueError):
        source.texts(pages(), ORIGINAL, "2026Q3")
    raw = pages()
    raw.append(raw[1])
    with pytest.raises(ValueError):
        source.texts(raw, ORIGINAL, "2026Q2")


@pytest.mark.parametrize("index", [1, 2])
def test_reversed_quarter_ytd_column_order_cannot_relabel_first_column(index):
    raw = pages()
    raw[index] = raw[index].replace(
        "Tres meses terminados el 30 de junio Seis meses terminados el 30 de junio",
        "Seis meses terminados el 30 de junio Tres meses terminados el 30 de junio",
    )
    with pytest.raises(ValueError, match="column order"):
        source.texts(raw, ORIGINAL, "2026Q2")


def test_duplicate_metric_row_cannot_take_the_first_value():
    raw = pages()
    raw[1] = raw[1].replace("Combustible 494", "Combustible 1 1 - 1 1 -\nCombustible 494")
    with pytest.raises(ValueError, match="duplicated"):
        source.texts(raw, ORIGINAL, "2026Q2")


@pytest.mark.parametrize(
    "index,old,new",
    [
        (1, "Combustible 494", "Combustible 494%"),
        (2, "Pasajeros ('000) 6,014", "Pasajeros ('000) -6,014"),
        (2, "Factor de ocupación (itinerario %) 84.9%", "Factor de ocupación (itinerario %) -84.9%"),
    ],
)
def test_numeric_token_units_and_physical_domains_are_enforced(index, old, new):
    raw = pages()
    raw[index] = raw[index].replace(old, new)
    with pytest.raises(ValueError):
        source.texts(raw, ORIGINAL, "2026Q2")


def test_operating_section_cannot_borrow_valid_financial_year_header():
    raw = pages()
    raw[2] = raw[2].replace(
        "Principales Indicadores Operativos 2026 2025 Var. 2026 2025 Var.",
        "Principales Indicadores Operativos 2025 2026 Var. 2025 2026 Var.",
    )
    with pytest.raises(ValueError, match="section current-prior"):
        source.texts(raw, ORIGINAL, "2026Q2")
