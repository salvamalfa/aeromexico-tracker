"""Build the two AFAC margins the international estimator would fit against.

This is the international counterpart of :mod:`src.ingest.afac.margins`, and
the differences from it are the whole content of this module:

- The origin-destination workbook's ``REG INT`` sheet carries **four** key
  columns instead of two -- origin city, origin country, destination city,
  destination country -- which pushes the flight block from index 2 to 4 and
  the passenger block from 15 to 17.  Reading it with the domestic offsets
  silently returns cargo where passengers should be.

- The carrier margin cannot come from the DATATUR long table the domestic
  builder uses, because the international universe includes foreign carriers
  and the two publications are revised on different schedules.  It is read
  from the airline summary workbook instead, which means both margins come
  from the **same edition** -- and that turns out to be the condition that
  makes them reconcile at all.

- The airline summary stacks three blocks per sheet and the international
  universe is two of them: national carriers on international service, plus
  foreign carriers.  The foreign block additionally carries *regional
  subtotals* ("Total Estadounidenses", "Total Europeas", ...) interleaved with
  the carriers.  Summing the block without dropping them double-counts every
  foreign passenger, so they are excluded by shape rather than by row number.

Reconciliation is checked here rather than assumed.  Read from one edition,
``REG INT`` and the international blocks of ``PAXREG`` agree to the passenger
across the seven months of 2026; read across editions they diverge by up to
0.85%, which is revision, not a difference of universe.  The contract this
module exists to protect is that the two margins describe the same cube, and
:func:`reconcile` is what proves it on every rebuild.

Nothing here estimates anything.  The method these margins feed, and the gates
that must close before a fitted cell may be published, are in
``docs/estimacion-pasajeros-ruta-aerolinea.md``.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re

import openpyxl
import pandas as pd

from src.config import PATHS


INTERNATIONAL_ROUTE_SHEET = "REG INT"
PASSENGER_SHEET = "PAXREG"

# ``REG INT`` layout, zero-based.  Row 5 holds the column labels; data starts
# on row 6.  The four key columns shift both metric blocks two places right of
# their domestic positions.
HEADER_ROW = 5
KEY_COLUMNS = 4
FLIGHT_COLUMN_OFFSET = 4
PASSENGER_COLUMN_OFFSET = 17
MONTHS = 12

ROUTE_MARGIN_FILE = "afac_od_internacional_regular.csv"
CARRIER_MARGIN_FILE = "afac_carrier_international.csv"

# The airline summary marks a block with two stacked lines: who the carriers
# are, then which service.  Matching both is what separates the national
# carriers' international block from their domestic one.
NATIONAL_MARKER = "EMPRESAS NACIONALES"
FOREIGN_MARKER = "EMPRESAS EXTRANJERAS"
INTERNATIONAL_SERVICE_MARKER = "EN SERVICIO REGULAR INTERNACIONAL"
CARRIER_HEADER_MARKER = "EMPRESA"

RECONCILIATION_TOLERANCE_PCT = 0.01

_FOOTNOTE_MARKS = re.compile(r"[*†‡]+$")


class WorkbookLayoutError(ValueError):
    """The workbook does not have the layout this parser was written against."""


@dataclass(frozen=True, slots=True)
class Reconciliation:
    """How closely the two independently published margins agree."""

    period_id: str
    route_passengers: int
    carrier_passengers: int

    @property
    def difference(self) -> int:
        return self.route_passengers - self.carrier_passengers

    @property
    def relative_pct(self) -> float:
        if not self.carrier_passengers:
            return float("nan")
        return 100 * self.difference / self.carrier_passengers

    @property
    def agrees(self) -> bool:
        return abs(self.relative_pct) <= RECONCILIATION_TOLERANCE_PCT


def _clean(value: object) -> str:
    """Collapse the whitespace AFAC uses for visual spacing in cell labels."""

    return " ".join(str(value).split()) if value is not None else ""


def _is_block_total(name: str) -> bool:
    """``T     o     t     a     l`` ends a block; ``Total Europeas`` does not.

    The block total is the same word letter-spaced, so removing every space
    leaves exactly ``TOTAL``.  A regional subtotal keeps its region name and
    survives the same test, which is what makes this safe to use for both.
    """

    return name.replace(" ", "").upper() == "TOTAL"


def _is_regional_subtotal(name: str) -> bool:
    """A foreign-block subtotal that would double-count its own carriers."""

    return name.upper().startswith("TOTAL ")


def read_route_workbook(path: Path, year: int) -> pd.DataFrame:
    """Read ``REG INT`` into one row per month, city pair and direction.

    Months with no passengers anywhere are dropped: a year-to-date workbook
    carries twelve month columns whatever the month, and the unfilled ones are
    template zeros, not months in which nobody flew.
    """

    workbook = openpyxl.load_workbook(path, read_only=True, data_only=True)
    try:
        if INTERNATIONAL_ROUTE_SHEET not in workbook.sheetnames:
            raise WorkbookLayoutError(
                f"{path.name}: no '{INTERNATIONAL_ROUTE_SHEET}' sheet; "
                f"found {workbook.sheetnames}"
            )
        rows = list(workbook[INTERNATIONAL_ROUTE_SHEET].iter_rows(values_only=True))
    finally:
        workbook.close()

    header = [_clean(cell).upper() for cell in rows[HEADER_ROW][:KEY_COLUMNS]]
    expected = ("ORIGEN", "PAÍS ORIGEN", "DESTINO", "PAÍS DESTINO")
    if not all(actual.startswith(want) for actual, want in zip(header, expected)):
        raise WorkbookLayoutError(
            f"{path.name}: unexpected '{INTERNATIONAL_ROUTE_SHEET}' header {header}"
        )

    per_month: dict[int, float] = {month: 0.0 for month in range(1, MONTHS + 1)}
    staged: list[tuple[str, str, str, str, int, int, int]] = []
    for row in rows[HEADER_ROW + 1 :]:
        if not row or not row[0]:
            continue
        keys = [_clean(row[index]) for index in range(KEY_COLUMNS)]
        if _is_block_total(keys[0]) or not all(keys):
            continue
        for month in range(MONTHS):
            flights = row[FLIGHT_COLUMN_OFFSET + month]
            passengers = row[PASSENGER_COLUMN_OFFSET + month]
            if not isinstance(flights, (int, float)):
                continue
            if not isinstance(passengers, (int, float)):
                continue
            per_month[month + 1] += float(passengers)
            staged.append((*keys, month + 1, int(flights), int(passengers)))

    live = {month for month, total in per_month.items() if total > 0}
    return pd.DataFrame(
        [
            {
                "period_id": f"{year}M{month:02d}",
                "origen": origin,
                "pais_origen": origin_country,
                "destino": destination,
                "pais_destino": destination_country,
                "vuelos": flights,
                "pasajeros": passengers,
            }
            for origin, origin_country, destination, destination_country, month, flights, passengers in staged
            if month in live
        ]
    )


def read_carrier_workbook(path: Path, year: int) -> pd.DataFrame:
    """Read the international carrier margin from both blocks of ``PAXREG``.

    Returns one row per month and carrier, tagged with the block it came from
    so a later crosswalk can tell a Mexican carrier from a foreign one without
    re-reading the workbook.  Regional subtotals and block totals are excluded:
    they are sums of rows that are already present.
    """

    workbook = openpyxl.load_workbook(path, read_only=True, data_only=True)
    try:
        if PASSENGER_SHEET not in workbook.sheetnames:
            raise WorkbookLayoutError(
                f"{path.name}: no '{PASSENGER_SHEET}' sheet; found {workbook.sheetnames}"
            )
        rows = list(workbook[PASSENGER_SHEET].iter_rows(values_only=True))
    finally:
        workbook.close()

    labels = [_clean(row[0]) if row else "" for row in rows]
    records: list[dict[str, object]] = []
    blocks_found: list[str] = []

    for index, label in enumerate(labels):
        block = (
            "national"
            if label.upper().startswith(NATIONAL_MARKER)
            else "foreign"
            if label.upper().startswith(FOREIGN_MARKER)
            else None
        )
        if block is None:
            continue
        service = labels[index + 1].upper() if index + 1 < len(labels) else ""
        if not service.startswith(INTERNATIONAL_SERVICE_MARKER):
            continue

        start = next(
            (
                offset
                for offset in range(index + 2, min(index + 8, len(labels)))
                if labels[offset].replace(" ", "").upper().startswith(CARRIER_HEADER_MARKER)
            ),
            None,
        )
        if start is None:
            raise WorkbookLayoutError(
                f"{path.name}: no carrier header under the {block} international block"
            )

        closed = False
        for offset in range(start + 1, len(labels)):
            name = labels[offset]
            if not name:
                continue
            if _is_block_total(name):
                closed = True
                break
            if _is_regional_subtotal(name):
                continue
            carrier = _FOOTNOTE_MARKS.sub("", name).strip()
            for month in range(MONTHS):
                value = rows[offset][1 + month]
                if not isinstance(value, (int, float)):
                    continue
                records.append(
                    {
                        "period_id": f"{year}M{month + 1:02d}",
                        "carrier_name": carrier,
                        "carrier_block": block,
                        "pasajeros": int(value),
                    }
                )
        if not closed:
            raise WorkbookLayoutError(
                f"{path.name}: the {block} international block has no total row"
            )
        blocks_found.append(block)

    missing = {"national", "foreign"} - set(blocks_found)
    if missing:
        raise WorkbookLayoutError(
            f"{path.name}: international block(s) not found: {', '.join(sorted(missing))}"
        )

    frame = pd.DataFrame(records)
    if frame.empty:
        return frame
    live = frame.groupby("period_id")["pasajeros"].sum()
    return frame[frame["period_id"].isin(live[live > 0].index)].reset_index(drop=True)


def reconcile(routes: pd.DataFrame, carriers: pd.DataFrame) -> list[Reconciliation]:
    """Compare the two margins month by month, on the months both cover."""

    by_route = routes.groupby("period_id")["pasajeros"].sum()
    by_carrier = carriers.groupby("period_id")["pasajeros"].sum()
    shared = sorted(set(by_route.index) & set(by_carrier.index))
    return [
        Reconciliation(period, int(by_route[period]), int(by_carrier[period]))
        for period in shared
    ]


def build(
    route_workbooks: dict[int, Path],
    carrier_workbooks: dict[int, Path],
    *,
    reference_dir: Path | None = None,
    write: bool = True,
) -> tuple[pd.DataFrame, pd.DataFrame, list[Reconciliation]]:
    """Rebuild both international margin files and report how well they agree.

    Both mappings are keyed by year and should point at the **same edition** of
    each year's workbooks; mixing a recent origin-destination book with an older
    airline summary reintroduces the revision gap this module exists to avoid.
    """

    routes = pd.concat(
        [read_route_workbook(path, year) for year, path in sorted(route_workbooks.items())],
        ignore_index=True,
    ).sort_values(
        ["period_id", "origen", "destino"], ignore_index=True
    )
    carriers = pd.concat(
        [read_carrier_workbook(path, year) for year, path in sorted(carrier_workbooks.items())],
        ignore_index=True,
    ).sort_values(["period_id", "carrier_block", "carrier_name"], ignore_index=True)

    if write:
        reference = reference_dir or (PATHS.data / "reference")
        reference.mkdir(parents=True, exist_ok=True)
        routes.to_csv(reference / ROUTE_MARGIN_FILE, index=False)
        carriers.to_csv(reference / CARRIER_MARGIN_FILE, index=False)
    return routes, carriers, reconcile(routes, carriers)


def main(argv: list[str] | None = None) -> int:  # pragma: no cover - manual entry
    import argparse

    parser = argparse.ArgumentParser(prog="python -m src.ingest.afac.international_margins")
    parser.add_argument(
        "--year", type=int, action="append", required=True,
        help="year covered by a workbook pair; repeat for several years",
    )
    parser.add_argument(
        "--routes", type=Path, action="append", required=True,
        help="origin-destination workbook for the matching --year",
    )
    parser.add_argument(
        "--carriers", type=Path, action="append", required=True,
        help="airline summary workbook of the SAME edition as --routes",
    )
    parser.add_argument("--reference-dir", type=Path, default=None)
    parser.add_argument(
        "--dry-run", action="store_true", help="parse and reconcile without writing"
    )
    args = parser.parse_args(argv)

    if not (len(args.year) == len(args.routes) == len(args.carriers)):
        parser.error("--year, --routes and --carriers must be repeated the same number of times")

    routes, carriers, checks = build(
        dict(zip(args.year, args.routes)),
        dict(zip(args.year, args.carriers)),
        reference_dir=args.reference_dir,
        write=not args.dry_run,
    )
    pairs = routes.groupby(["origen", "destino"]).ngroups
    print(f"rutas: {len(routes):,} filas mes x par, {pairs:,} pares direccionales")
    print(
        f"aerolineas: {len(carriers):,} filas mes x empresa, "
        f"{carriers['carrier_name'].nunique():,} empresas "
        f"({carriers.groupby('carrier_block')['carrier_name'].nunique().to_dict()})"
    )
    print("\nconciliacion mes a mes:")
    for check in checks:
        flag = "ok" if check.agrees else "REVISAR"
        print(
            f"  {check.period_id}  ruta {check.route_passengers:>10,}  "
            f"empresa {check.carrier_passengers:>10,}  "
            f"dif {check.difference:>8,}  {check.relative_pct:+.6f}%  {flag}"
        )
    disagreements = [check for check in checks if not check.agrees]
    if disagreements:
        print(
            f"\n{len(disagreements)} mes(es) fuera de tolerancia. Comprueba que ambos "
            "libros sean de la misma edicion antes de usar estas marginales.",
        )
        return 1
    print("\nLas dos marginales describen el mismo universo en todos los meses.")
    return 0


if __name__ == "__main__":  # pragma: no cover - manual entry point
    raise SystemExit(main())
