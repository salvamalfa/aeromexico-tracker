"""The international margins fail in ways the domestic ones cannot.

Two mistakes would each produce a full, plausible-looking table of wrong
numbers rather than an error: reading ``REG INT`` with the domestic column
offsets returns cargo kilograms where passengers belong, and summing the
foreign carrier block without dropping its regional subtotals counts every
foreign passenger twice.  Both are silent, so both get a test.

The fixtures build real workbooks rather than mocking openpyxl: the layout
*is* the contract here, and a mock would agree with whatever the parser
happens to do.
"""

from __future__ import annotations

from pathlib import Path

import openpyxl
import pandas as pd
import pytest

from src.ingest.afac.international_margins import (
    CARRIER_MARGIN_FILE,
    ROUTE_MARGIN_FILE,
    Reconciliation,
    WorkbookLayoutError,
    build,
    read_carrier_workbook,
    read_route_workbook,
    reconcile,
)


MONTHS = 12


def _route_workbook(
    path: Path,
    rows: list[tuple[str, str, str, str, list[int], list[int]]],
    *,
    sheet: str = "REG INT",
    keys: tuple[str, ...] = ("ORIGEN / FROM", "PAÍS ORIGEN", "DESTINO / TO", "PAÍS DESTINO"),
    total_row: bool = True,
) -> Path:
    """One ``REG INT`` sheet: 4 key columns, 12+1 flights, 12+1 passengers, 12+1 cargo."""

    workbook = openpyxl.Workbook()
    sheet_obj = workbook.active
    sheet_obj.title = sheet
    sheet_obj.append([])
    sheet_obj.append(["ESTADISTICA OPERACIONAL ORIGEN-DESTINO / AVIATION STATISTICS BY OFOD"])
    sheet_obj.append(["EN SERVICIO REGULAR INTERNACIONAL, 2026"])
    sheet_obj.append([])
    sheet_obj.append(["PAR DE CIUDADES / CITY PAIR"])
    sheet_obj.append(list(keys) + ["Ene/Jan"] * MONTHS + ["Total"] * 3)
    for origin, origin_country, destination, destination_country, flights, passengers in rows:
        cargo = [7_000 + index for index in range(MONTHS)]
        sheet_obj.append(
            [origin, origin_country, destination, destination_country]
            + flights + [sum(flights)]
            + passengers + [sum(passengers)]
            + cargo + [sum(cargo)]
        )
    if total_row:
        sheet_obj.append(["T O T A L", "", "", ""] + [0] * (MONTHS + 1) * 3)
    workbook.save(path)
    return path


def _carrier_workbook(
    path: Path,
    *,
    national_domestic: list[tuple[str, list[int]]] | None = None,
    national_international: list[tuple[str, list[int]]] | None = None,
    foreign: list[tuple[str, list[int]]] | None = None,
    include_foreign_block: bool = True,
) -> Path:
    """A ``PAXREG`` sheet with the three stacked blocks AFAC publishes."""

    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.title = "PAXREG"

    def block(entity: str, service: str, carriers: list[tuple[str, list[int]]]) -> None:
        sheet.append([])
        sheet.append([entity])
        sheet.append([service])
        sheet.append([])
        sheet.append(["E m p r e s a / Air Carrier"] + ["Ene/Jan"] * MONTHS + ["Total"])
        total = [0] * MONTHS
        for name, values in carriers:
            sheet.append([name] + values + [sum(values)])
            if not name.upper().startswith("TOTAL "):
                total = [a + b for a, b in zip(total, values)]
        sheet.append(["T     o     t     a     l"] + total + [sum(total)])

    sheet.append([])
    sheet.append(["ESTADÍSTICA POR EMPRESA"])
    block(
        "EMPRESAS NACIONALES / DOMESTIC AIR CARRIERS",
        "EN SERVICIO REGULAR NACIONAL / SCHEDULED DOMESTIC SERVICE",
        national_domestic or [("Aeroméxico (Aerovías de México)", [900] + [0] * (MONTHS - 1))],
    )
    block(
        "EMPRESAS NACIONALES / DOMESTIC AIR CARRIERS",
        "EN SERVICIO REGULAR INTERNACIONAL / SCHEDULED INTERNATIONAL SERVICE",
        national_international or [("Aeroméxico (Aerovías de México)", [60] + [0] * (MONTHS - 1))],
    )
    if include_foreign_block:
        block(
            "EMPRESAS EXTRANJERAS / FOREIGN AIR CARRIERS",
            "EN SERVICIO REGULAR INTERNACIONAL / SCHEDULED INTERNATIONAL SERVICE",
            foreign or [("Iberia", [40] + [0] * (MONTHS - 1))],
        )
    workbook.save(path)
    return path


def _month(value: int, month: int = 1) -> list[int]:
    values = [0] * MONTHS
    values[month - 1] = value
    return values


def test_passengers_are_read_from_their_own_block_not_cargo(tmp_path) -> None:
    """The domestic offsets would land on cargo and return a full wrong table."""

    path = _route_workbook(
        tmp_path / "od.xlsx",
        [("MEXICO", "Mexico", "MADRID", "España", _month(581), _month(141_526))],
    )

    frame = read_route_workbook(path, 2026)

    assert len(frame) == 1
    row = frame.iloc[0]
    assert row["pasajeros"] == 141_526 and row["vuelos"] == 581
    assert row["pais_destino"] == "España"


def test_the_two_country_columns_are_kept(tmp_path) -> None:
    path = _route_workbook(
        tmp_path / "od.xlsx",
        [("TORONTO", "Canada", "MEXICO", "Mexico", _month(313), _month(45_409))],
    )

    row = read_route_workbook(path, 2026).iloc[0]

    assert row["origen"] == "TORONTO" and row["pais_origen"] == "Canada"
    assert row["destino"] == "MEXICO" and row["pais_destino"] == "Mexico"


def test_template_months_with_no_passengers_are_dropped(tmp_path) -> None:
    """A year-to-date book carries twelve columns; the unfilled ones are zeros."""

    path = _route_workbook(
        tmp_path / "od.xlsx",
        [("MEXICO", "Mexico", "BOGOTA", "Colombia", _month(637), _month(89_400))],
    )

    frame = read_route_workbook(path, 2026)

    assert list(frame["period_id"]) == ["2026M01"]


def test_the_sheet_total_row_is_not_a_route(tmp_path) -> None:
    path = _route_workbook(
        tmp_path / "od.xlsx",
        [("MEXICO", "Mexico", "LIMA", "Peru", _month(100), _month(9_000))],
        total_row=True,
    )

    frame = read_route_workbook(path, 2026)

    assert len(frame) == 1
    assert "T O T A L" not in set(frame["origen"])


def test_a_domestic_layout_is_refused_instead_of_misread(tmp_path) -> None:
    path = _route_workbook(
        tmp_path / "od.xlsx",
        [("MEXICO", "Mexico", "MONTERREY", "Mexico", _month(2_680), _month(414_835))],
        keys=("ORIGEN / FROM", "DESTINO / TO", "", ""),
    )

    with pytest.raises(WorkbookLayoutError, match="header"):
        read_route_workbook(path, 2026)


def test_a_workbook_without_the_sheet_is_refused(tmp_path) -> None:
    path = _route_workbook(
        tmp_path / "od.xlsx",
        [("MEXICO", "Mexico", "TOKYO", "Japon", _month(181), _month(29_013))],
        sheet="REG NAC",
    )

    with pytest.raises(WorkbookLayoutError, match="REG INT"):
        read_route_workbook(path, 2026)


def test_regional_subtotals_are_excluded_so_nobody_is_counted_twice(tmp_path) -> None:
    """Summing the foreign block with its subtotals doubles every passenger."""

    path = _carrier_workbook(
        tmp_path / "summary.xlsx",
        foreign=[
            ("Total Estadounidenses / American Total", _month(300)),
            ("American Airlines", _month(200)),
            ("Delta Airlines", _month(100)),
            ("Total Europeas / European Total", _month(50)),
            ("Iberia", _month(50)),
        ],
    )

    frame = read_carrier_workbook(path, 2026)
    foreign = frame[frame["carrier_block"] == "foreign"]

    assert set(foreign["carrier_name"]) == {"American Airlines", "Delta Airlines", "Iberia"}
    assert foreign["pasajeros"].sum() == 350


def test_the_national_international_block_is_not_the_domestic_one(tmp_path) -> None:
    """Both blocks carry the same carrier names under different service lines."""

    path = _carrier_workbook(
        tmp_path / "summary.xlsx",
        national_domestic=[("Aeroméxico (Aerovías de México)", _month(1_032_307))],
        national_international=[("Aeroméxico (Aerovías de México)", _month(641_318))],
    )

    frame = read_carrier_workbook(path, 2026)
    national = frame[frame["carrier_block"] == "national"]

    assert list(national["pasajeros"]) == [641_318]


def test_footnote_marks_do_not_fork_a_carrier_identity(tmp_path) -> None:
    """AFAC flags estimated months with an asterisk on the carrier's name."""

    path = _carrier_workbook(
        tmp_path / "summary.xlsx",
        foreign=[("Spirit Airlines**", _month(1_000))],
    )

    frame = read_carrier_workbook(path, 2026)

    assert set(frame[frame["carrier_block"] == "foreign"]["carrier_name"]) == {"Spirit Airlines"}


def test_both_international_blocks_are_required(tmp_path) -> None:
    path = _carrier_workbook(tmp_path / "summary.xlsx", include_foreign_block=False)

    with pytest.raises(WorkbookLayoutError, match="foreign"):
        read_carrier_workbook(path, 2026)


def test_carriers_are_tagged_by_block_for_a_later_crosswalk(tmp_path) -> None:
    path = _carrier_workbook(
        tmp_path / "summary.xlsx",
        national_international=[("Aeroméxico Connect (Aerolitoral)", _month(45_376))],
        foreign=[("Air France (Société Air France)", _month(39_904))],
    )

    frame = read_carrier_workbook(path, 2026)

    assert dict(zip(frame["carrier_name"], frame["carrier_block"])) == {
        "Aeroméxico Connect (Aerolitoral)": "national",
        "Air France (Société Air France)": "foreign",
    }


def test_reconciliation_reports_agreement_and_disagreement() -> None:
    routes = pd.DataFrame(
        {"period_id": ["2026M01", "2026M02"], "pasajeros": [100_000, 200_000]}
    )
    carriers = pd.DataFrame(
        {"period_id": ["2026M01", "2026M02"], "pasajeros": [100_000, 180_000]}
    )

    checks = reconcile(routes, carriers)

    assert checks[0] == Reconciliation("2026M01", 100_000, 100_000)
    assert checks[0].agrees
    assert not checks[1].agrees
    assert checks[1].difference == 20_000


def test_a_matched_edition_reconciles_to_the_passenger(tmp_path) -> None:
    """The property the whole international fit depends on."""

    routes = _route_workbook(
        tmp_path / "od.xlsx",
        [
            ("MEXICO", "Mexico", "MADRID", "España", _month(581), _month(60)),
            ("MADRID", "España", "MEXICO", "Mexico", _month(580), _month(40)),
        ],
    )
    carriers = _carrier_workbook(
        tmp_path / "summary.xlsx",
        national_international=[("Aeroméxico (Aerovías de México)", _month(60))],
        foreign=[("Iberia", _month(40))],
    )

    route_frame, carrier_frame, checks = build(
        {2026: routes}, {2026: carriers}, reference_dir=tmp_path / "reference"
    )

    assert [check.difference for check in checks] == [0]
    assert (tmp_path / "reference" / ROUTE_MARGIN_FILE).exists()
    assert (tmp_path / "reference" / CARRIER_MARGIN_FILE).exists()
    assert len(route_frame) == 2 and len(carrier_frame) == 2


def test_dry_run_parses_without_writing(tmp_path) -> None:
    routes = _route_workbook(
        tmp_path / "od.xlsx",
        [("MEXICO", "Mexico", "SEUL", "Corea del Sur", _month(91), _month(60))],
    )
    carriers = _carrier_workbook(
        tmp_path / "summary.xlsx",
        national_international=[("Aeroméxico (Aerovías de México)", _month(60))],
        foreign=[("Iberia", [0] * MONTHS)],
    )
    reference = tmp_path / "reference"

    build({2026: routes}, {2026: carriers}, reference_dir=reference, write=False)

    assert not reference.exists()
