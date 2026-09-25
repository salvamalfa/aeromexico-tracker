"""Build the two AFAC margins the route-carrier estimator fits against.

AFAC publishes the same domestic universe twice, cut two different ways, and
never crossed:

- the origin-destination workbook (``sase-*.xlsx``, sheet ``REG NAC``) gives
  flights and passengers per city pair and month;
- the airline series gives passengers per carrier and month.

Each ``sase`` workbook is cumulative within its year: the December edition
carries all twelve months, so one file per year is enough.  The carrier series
is easier -- DATATUR republishes it as a single long table covering every year
since 2016, which avoids the anti-automation challenge that blocks the
``.xlsx`` downloads on gob.mx.  That the two agree to the passenger is checked
here rather than assumed, because it is the evidence that a joint table exists
upstream at all.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

import openpyxl
import pandas as pd

from src.config import PATHS


DOMESTIC_SCHEDULED_SHEET = "REG NAC"
# Row 6 of the sheet holds the header; flights occupy twelve columns from index
# 2 and passengers twelve more from index 15.
HEADER_ROW = 5
FLIGHT_COLUMN_OFFSET = 2
PASSENGER_COLUMN_OFFSET = 15
MONTHS = 12

ROUTE_MARGIN_FILE = "afac_od_nacional_regular.csv"
CARRIER_MARGIN_FILE = "afac_carrier_domestic.csv"
CARRIER_FLIGHTS_FILE = "afac_carrier_flights_domestic.csv"

# The airline summary workbook stacks three blocks in every sheet: national
# carriers on domestic service, the same carriers on international service, and
# foreign carriers.  Only the first is the domestic universe, and reading past
# its end silently triples the totals.
DOMESTIC_BLOCK_MARKER = "REGULAR NACIONAL"
BLOCK_BOUNDARIES = ("EMPRESAS", "EN SERVICIO")

# Carriers DATATUR lists under scheduled domestic service that carry freight
# only, or that ceased operating.  They are excluded by the crosswalk rather
# than by name, so this is only documentation of why the totals still match.
RECONCILIATION_TOLERANCE_PCT = 0.01


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


def read_route_workbook(path: Path, year: int) -> pd.DataFrame:
    """Read one cumulative ``sase`` workbook into route rows.

    Months with no passengers at all are dropped: a year-to-date file carries
    twelve columns whatever the month, and the unfilled ones are zeros, not
    routes that carried nobody.
    """

    workbook = openpyxl.load_workbook(path, read_only=True, data_only=True)
    try:
        sheet = workbook[DOMESTIC_SCHEDULED_SHEET]
        rows = list(sheet.iter_rows(values_only=True))
    finally:
        workbook.close()

    header = rows[HEADER_ROW]
    if not (
        str(header[0]).startswith("ORIGEN") and str(header[1]).startswith("DESTINO")
    ):
        raise ValueError(f"{path.name}: unexpected header layout {header[:2]}")

    per_month_passengers: dict[int, float] = defaultdict(float)
    staged: list[tuple[str, str, int, int, int]] = []
    for row in rows[HEADER_ROW + 1 :]:
        if not row or not row[0] or not row[1]:
            continue
        origin, destination = str(row[0]).strip(), str(row[1]).strip()
        if origin.upper().startswith("TOTAL") or destination.upper().startswith("TOTAL"):
            continue
        for month in range(MONTHS):
            flights = row[FLIGHT_COLUMN_OFFSET + month]
            passengers = row[PASSENGER_COLUMN_OFFSET + month]
            if not isinstance(flights, (int, float)):
                continue
            if not isinstance(passengers, (int, float)):
                continue
            per_month_passengers[month + 1] += passengers
            staged.append((origin, destination, month + 1, int(flights), int(passengers)))

    live = {month for month, total in per_month_passengers.items() if total > 0}
    return pd.DataFrame(
        [
            {
                "period_id": f"{year}M{month:02d}",
                "origen": origin,
                "destino": destination,
                "vuelos": flights,
                "pasajeros": passengers,
            }
            for origin, destination, month, flights, passengers in staged
            if month in live
        ]
    )


def read_carrier_base(path: Path) -> pd.DataFrame:
    """Read the DATATUR long table, keeping scheduled domestic service only."""

    base = pd.read_excel(path, sheet_name="AFAC")
    domestic = base[
        (base["Tipo"] == "Nacional")
        & (base["Servicio"].astype(str).str.strip().str.casefold() == "regular")
        & (base["Pasajeros"] > 0)
    ].copy()
    domestic["period_id"] = (
        domestic["Año"].astype(int).astype(str)
        + "M"
        + domestic["Id_mes"].astype(int).astype(str).str.zfill(2)
    )
    return (
        domestic.rename(columns={"Aerolinea": "carrier_name", "Pasajeros": "pasajeros"})
        .groupby(["period_id", "carrier_name"], as_index=False)["pasajeros"]
        .sum()
        .astype({"pasajeros": int})
    )


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
    carrier_base: Path,
    *,
    reference_dir: Path | None = None,
    known_carriers: set[str] | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame, list[Reconciliation]]:
    """Rebuild both margin files and report how well they agree."""

    routes = pd.concat(
        [read_route_workbook(path, year) for year, path in sorted(route_workbooks.items())],
        ignore_index=True,
    ).sort_values(["period_id", "origen", "destino"], ignore_index=True)

    carriers = read_carrier_base(carrier_base)
    if known_carriers is not None:
        carriers = carriers[carriers["carrier_name"].isin(known_carriers)]
    # The carrier base runs back to 2016; keep it aligned to the months the
    # route margin actually covers, so the pair is always fittable.
    carriers = carriers[carriers["period_id"].isin(set(routes["period_id"]))]
    carriers = carriers.sort_values(["period_id", "carrier_name"], ignore_index=True)

    reference = reference_dir or (PATHS.data / "reference")
    routes.to_csv(reference / ROUTE_MARGIN_FILE, index=False)
    carriers.to_csv(reference / CARRIER_MARGIN_FILE, index=False)
    return routes, carriers, reconcile(routes, carriers)


def read_summary_domestic_block(path: Path, sheet: str, year: int) -> pd.DataFrame:
    """Read one sheet of the airline summary, domestic block only.

    ``VLOSREG`` and ``PAXREG`` share a layout: carrier in the first column,
    twelve month columns, then a total.  The sheet holds three stacked blocks
    and only the first covers scheduled domestic service, so the read stops at
    the next block header rather than running to the end of the sheet.
    """

    workbook = openpyxl.load_workbook(path, read_only=True, data_only=True)
    try:
        rows = list(workbook[sheet].iter_rows(values_only=True))
    finally:
        workbook.close()

    start = next(
        (
            index + 1
            for index, row in enumerate(rows)
            if row and row[0] and DOMESTIC_BLOCK_MARKER in str(row[0]).upper()
        ),
        None,
    )
    if start is None:
        raise ValueError(f"{path.name}:{sheet} has no domestic block header")

    records: list[dict[str, object]] = []
    for row in rows[start:]:
        if not row or row[0] is None:
            continue
        name = str(row[0]).strip()
        upper = name.upper()
        if upper.startswith(BLOCK_BOUNDARIES):
            break
        # Total rows are sometimes letter-spaced ("T  o  t  a  l"), so collapse
        # whitespace before comparing rather than matching the literal.
        if "".join(upper.split()).startswith(("TOTAL", "EMPRESA")):
            continue
        for month in range(1, MONTHS + 1):
            value = row[month]
            if isinstance(value, (int, float)):
                records.append(
                    {
                        "period_id": f"{year}M{month:02d}",
                        "carrier_name": name,
                        "value": int(value),
                    }
                )
    return pd.DataFrame(records)


def build_carrier_flights(
    summary_workbooks: dict[int, Path],
    *,
    reference_dir: Path | None = None,
    known_carriers: set[str] | None = None,
) -> pd.DataFrame:
    """Flights per carrier and month, which no other AFAC product publishes.

    This is what turns the seed acceptance test from an inference into a
    division: a candidate source's flight count per carrier can be compared
    directly against the published one, so coverage that favours one carrier
    over another shows up without having to be modelled.
    """

    frames = [
        read_summary_domestic_block(path, "VLOSREG", year)
        for year, path in sorted(summary_workbooks.items())
    ]
    flights = pd.concat(frames, ignore_index=True)
    flights = flights[flights["value"] > 0]
    if known_carriers is not None:
        flights = flights[flights["carrier_name"].isin(known_carriers)]
    flights = (
        flights.rename(columns={"value": "vuelos"})
        .groupby(["period_id", "carrier_name"], as_index=False)["vuelos"]
        .sum()
        .sort_values(["period_id", "carrier_name"], ignore_index=True)
    )
    reference = reference_dir or (PATHS.data / "reference")
    flights.to_csv(reference / CARRIER_FLIGHTS_FILE, index=False)
    return flights


def refresh_year(
    year: int,
    route_workbook: Path,
    summary_workbook: Path,
    *,
    reference_dir: Path | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame, list[Reconciliation]]:
    """Replace one year of the three domestic margin files from one AFAC edition.

    A new monthly edition (``sase-agosto-2026-*.xlsx`` with its companion
    ``resumen-agosto-2026-*.xlsx``) restates every month of its year, so the
    whole year is swapped at once and never mixed with an older edition.  The
    carrier side is read from the summary's ``PAXREG`` domestic block instead
    of the DATATUR long table, which lags the monthly release; its names are
    the ones the files already use, and a carrier absent from them is kept
    out of the fit and listed.
    """

    reference = reference_dir or (PATHS.data / "reference")
    prefix = f"{year}M"
    routes = read_route_workbook(route_workbook, year)
    carriers = read_summary_domestic_block(summary_workbook, "PAXREG", year)
    flights = read_summary_domestic_block(summary_workbook, "VLOSREG", year)
    carriers = carriers[carriers["value"] > 0].rename(columns={"value": "pasajeros"})
    # The summary marks some carriers with a footnote asterisk that the
    # DATATUR names in the passenger file never carry.  The flight file was
    # built from the summary itself, so its names are left as published.
    carriers["carrier_name"] = carriers["carrier_name"].str.rstrip("* ").str.strip()
    flights = flights[flights["value"] > 0].rename(columns={"value": "vuelos"})
    months = set(routes["period_id"])
    carriers = carriers[carriers["period_id"].isin(months)]
    flights = flights[flights["period_id"].isin(months)]

    existing_carriers = pd.read_csv(reference / CARRIER_MARGIN_FILE)
    known = set(existing_carriers["carrier_name"])
    excluded = carriers[~carriers["carrier_name"].isin(known)]
    if not excluded.empty:
        # Same exclusion ``build`` applies through ``known_carriers``: charter
        # and freight operators the crosswalk leaves out.  A genuinely new
        # carrier also lands here, so it is printed, and the reconciliation
        # below shows whether the route side carries its passengers.
        totals = excluded.groupby("carrier_name")["pasajeros"].sum()
        print("aerolineas fuera de la marginal: " + ", ".join(
            f"{name} ({int(value):,})" for name, value in totals.items()
        ))
    carriers = carriers[carriers["carrier_name"].isin(known)]
    flights = flights[flights["carrier_name"].isin(known)]

    def swap(existing: pd.DataFrame, fresh: pd.DataFrame, keys: list[str]) -> pd.DataFrame:
        kept = existing[~existing["period_id"].astype(str).str.startswith(prefix)]
        merged = pd.concat([kept, fresh.loc[:, list(existing.columns)]], ignore_index=True)
        return merged.sort_values(keys, ignore_index=True)

    routes_out = swap(
        pd.read_csv(reference / ROUTE_MARGIN_FILE), routes, ["period_id", "origen", "destino"]
    )
    carriers_out = swap(existing_carriers, carriers, ["period_id", "carrier_name"])
    flights_out = swap(
        pd.read_csv(reference / CARRIER_FLIGHTS_FILE), flights, ["period_id", "carrier_name"]
    )
    routes_out.to_csv(reference / ROUTE_MARGIN_FILE, index=False)
    carriers_out.to_csv(reference / CARRIER_MARGIN_FILE, index=False)
    flights_out.to_csv(reference / CARRIER_FLIGHTS_FILE, index=False)
    return routes_out, carriers_out, reconcile(routes_out, carriers_out)


def main(argv: list[str] | None = None) -> int:  # pragma: no cover - manual entry
    import argparse

    parser = argparse.ArgumentParser(prog="python -m src.ingest.afac.margins")
    parser.add_argument("--year", type=int, required=True)
    parser.add_argument("--routes", type=Path, required=True, help="sase-<mes>-<año>-*.xlsx")
    parser.add_argument("--carriers", type=Path, required=True, help="resumen-<mes>-<año>-*.xlsx")
    parser.add_argument("--reference-dir", type=Path, default=None)
    args = parser.parse_args(argv)
    _, _, checks = refresh_year(
        args.year, args.routes, args.carriers, reference_dir=args.reference_dir
    )
    for check in checks:
        if check.period_id.startswith(f"{args.year}M"):
            print(
                f"{check.period_id}: rutas {check.route_passengers:,} "
                f"aerolineas {check.carrier_passengers:,} diferencia {check.difference:,}"
            )
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
