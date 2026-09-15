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
