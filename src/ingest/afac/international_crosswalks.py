"""Join AFAC's international vocabulary to the codes AeroDataBox speaks.

AFAC publishes its international margins in words: a city label, a country
label and a commercial airline name.  AeroDataBox publishes codes: an IATA
airport and an IATA/ICAO operator.  Neither side can be fitted against the
other until something maps one vocabulary onto the other, and that mapping is
the last thing standing between the seed and the estimator.

Two properties shape how it is built.

**Direction.**  A city is not an airport.  ``NUEVA YORK`` is JFK *and* LGA
*and*, for some publications, EWR.  So the crosswalk runs **airport → city**,
many-to-one, which is always well defined; the reverse never is.  That is also
why listing an extra airport for a city is harmless: an airport that never
shows up in a seed costs nothing, while a *wrong* city on an airport silently
moves passengers between routes.

**No guessing by resemblance.**  A label is resolved only by exact match on a
normalised city name within the right country, or by an explicit reviewed
override that records *why*.  Everything else is reported as unresolved and
weighted by the AFAC passengers behind it, because an unresolved label is a
row the fit will not see, and the acceptance gate has to know how much traffic
that is.

The automatic matcher has one guard beyond exactness.  ``LAS VEGAS`` matches
four US airports, one of which is in New Mexico, 907 km away; ``NORFOLK``
matches one in Nebraska, 1,903 km from Virginia.  Airports of one city do not
sit that far apart, so a resolved city whose airports span more than
:data:`MAX_CITY_SPREAD_KM` is refused rather than accepted, and the offending
code has to be excluded by hand in the override file.

Nothing here estimates anything.  The method is in
``docs/estimacion-pasajeros-ruta-aerolinea.md``.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import unicodedata

import numpy as np
import pandas as pd

from src.config import PATHS


CITY_OVERRIDE_FILE = "afac_international_city_overrides.csv"
CARRIER_CROSSWALK_FILE = "afac_international_carrier_crosswalk.csv"
CITY_CROSSWALK_FILE = "afac_international_city_iata_crosswalk.csv"
DOMESTIC_CITY_CROSSWALK_FILE = "afac_city_iata_crosswalk.csv"
ROUTE_MARGIN_FILE = "afac_od_internacional_regular.csv"
CARRIER_MARGIN_FILE = "afac_carrier_international.csv"

# Airports serving one city are close together.  Anything wider is two cities
# that happen to share a name, and accepting it would move passengers between
# routes without leaving a trace.
MAX_CITY_SPREAD_KM = 120.0
EARTH_RADIUS_KM = 6371.0088

# A city label only resolves against airports that carry scheduled traffic.
USABLE_AIRPORT_TYPES = ("large_airport", "medium_airport")

# Three levels, because "we know this" and "we have checked this here" are not
# the same claim.  ``resolved`` is grounded in an artefact of this repository
# or in the live probe; ``probable`` is a documented airline identity that
# nothing in this repository has yet confirmed; ``unresolved`` is genuinely in
# doubt and must not be fitted.  The first real capture settles every
# ``probable`` row by whether its code shows up in the seed, so the level is a
# to-do list, not a permanent verdict.
USABLE_CONFIDENCE = ("resolved", "probable")

# AFAC writes country names in Spanish, with occasional capitalisation drift.
# The keys are reproduced exactly as the workbook publishes them.
COUNTRY_ISO2: dict[str, str] = {
    "Alemania": "DE", "Argentina": "AR", "Belgica": "BE", "Belice": "BZ",
    "Brasil": "BR", "COREA DEL SUR": "KR", "Canada": "CA", "Chile": "CL",
    "China": "CN", "Colombia": "CO", "Costa Rica": "CR", "Cuba": "CU",
    "Ecuador": "EC", "El Salvador": "SV", "Emiratos Arabes": "AE",
    "España": "ES", "Estados Unidos": "US", "Francia": "FR", "Guatemala": "GT",
    "HONG KONG": "HK", "Honduras": "HN", "Irlanda": "IE", "Italia": "IT",
    "Japon": "JP", "Luxemburgo": "LU", "Mexico": "MX", "Nicaragua": "NI",
    "Paises Bajos": "NL", "Panama": "PA", "Peru": "PE", "Portugal": "PT",
    "Qatar": "QA", "Reino Unido": "GB", "Republica Dominicana": "DO",
    "Suiza": "CH", "Turquia": "TR", "Venezuela": "VE",
}


class UnknownCountryError(ValueError):
    """A country label the crosswalk has never been told how to read."""


class AmbiguousCityError(ValueError):
    """A city label resolved to airports too far apart to be one city."""


@dataclass(frozen=True, slots=True)
class CoverageReport:
    """What share of a margin the crosswalks can actually place."""

    period_id: str
    routes_total: int
    routes_covered: int
    flights_total: int
    flights_covered: int
    passengers_total: int
    passengers_covered: int

    @property
    def route_share(self) -> float:
        return self.routes_covered / self.routes_total if self.routes_total else float("nan")

    @property
    def flight_share(self) -> float:
        return self.flights_covered / self.flights_total if self.flights_total else float("nan")

    @property
    def passenger_share(self) -> float:
        return (
            self.passengers_covered / self.passengers_total
            if self.passengers_total
            else float("nan")
        )


def normalise_city(value: object) -> str:
    """Fold accents, punctuation and spacing so two spellings can be compared."""

    text = "".join(
        char
        for char in unicodedata.normalize("NFKD", str(value))
        if not unicodedata.combining(char)
    )
    for symbol in "-./,":
        text = text.replace(symbol, " ")
    return " ".join(text.upper().split())


def _reference_dir(reference_dir: Path | None) -> Path:
    return reference_dir or (PATHS.data / "reference")


def _airport_dimension(gold_dir: Path | None = None) -> pd.DataFrame:
    frame = pd.read_parquet(
        (gold_dir or PATHS.gold) / "dim_airport.parquet",
        columns=["airport_iata", "city", "country", "type", "latitude", "longitude"],
    )
    frame = frame.dropna(subset=["airport_iata", "city", "country"])
    frame = frame[frame["type"].isin(USABLE_AIRPORT_TYPES)].copy()
    frame["city_normalised"] = frame["city"].map(normalise_city)
    return frame.drop_duplicates("airport_iata")


def _spread_km(frame: pd.DataFrame) -> float:
    """Greatest distance between any two airports assigned to one city."""

    if len(frame) < 2:
        return 0.0
    lat = np.radians(frame["latitude"].to_numpy(dtype=float))
    lon = np.radians(frame["longitude"].to_numpy(dtype=float))
    widest = 0.0
    for first in range(len(frame)):
        for second in range(first + 1, len(frame)):
            chord = (
                np.sin((lat[second] - lat[first]) / 2) ** 2
                + np.cos(lat[first]) * np.cos(lat[second])
                * np.sin((lon[second] - lon[first]) / 2) ** 2
            )
            widest = max(widest, 2 * EARTH_RADIUS_KM * np.arcsin(min(1.0, np.sqrt(chord))))
    return float(widest)


def city_labels(routes: pd.DataFrame) -> set[tuple[str, str]]:
    """Every ``(city, country)`` pair either end of a route is keyed by."""

    return set(zip(routes["origen"], routes["pais_origen"])) | set(
        zip(routes["destino"], routes["pais_destino"])
    )


def build_city_crosswalk(
    routes: pd.DataFrame,
    *,
    reference_dir: Path | None = None,
    gold_dir: Path | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Resolve each AFAC city label to its airports, and report what it could not.

    Returns ``(crosswalk, unresolved)``.  The crosswalk carries one row per
    airport; ``unresolved`` carries one row per label that no rule placed,
    which is what the acceptance gate weighs against AFAC passengers.
    """

    reference = _reference_dir(reference_dir)
    airports = _airport_dimension(gold_dir)
    domestic = pd.read_csv(reference / DOMESTIC_CITY_CROSSWALK_FILE)
    domestic_by_city = {
        normalise_city(city): code
        for city, code in zip(domestic["afac_city"], domestic["airport_iata"])
    }

    overrides = pd.read_csv(reference / CITY_OVERRIDE_FILE).fillna("")
    mapped: dict[tuple[str, str], list[tuple[str, str]]] = {}
    excluded: set[tuple[str, str, str]] = set()
    for row in overrides.itertuples(index=False):
        key = (row.afac_city, row.afac_country)
        if row.action == "exclude":
            excluded.add((*key, row.airport_iata))
        elif row.action == "map_airport":
            mapped.setdefault(key, []).append((row.airport_iata, "override_airport"))
        elif row.action == "map_city":
            iso = COUNTRY_ISO2.get(row.afac_country)
            target = normalise_city(row.dim_city)
            found = airports[
                (airports["country"] == iso) & (airports["city_normalised"] == target)
            ]
            mapped.setdefault(key, []).extend(
                (code, "override_city") for code in found["airport_iata"]
            )
        else:
            raise ValueError(f"unknown override action {row.action!r}")

    rows: list[dict[str, object]] = []
    unresolved: list[dict[str, object]] = []
    for city, country in sorted(city_labels(routes)):
        if country not in COUNTRY_ISO2:
            raise UnknownCountryError(
                f"AFAC country label {country!r} is not in COUNTRY_ISO2"
            )
        iso = COUNTRY_ISO2[country]
        key = (city, country)
        candidates: list[tuple[str, str]] = list(mapped.get(key, []))

        if not candidates and country == "Mexico":
            code = domestic_by_city.get(normalise_city(city))
            if code:
                candidates.append((code, "domestic_crosswalk"))

        if not candidates:
            matched = airports[
                (airports["country"] == iso)
                & (airports["city_normalised"] == normalise_city(city))
            ]
            candidates.extend((code, "city_exact") for code in matched["airport_iata"])

        kept = [
            (code, method)
            for code, method in dict(candidates).items()
            if (*key, code) not in excluded
        ]
        if not kept:
            unresolved.append(
                {"afac_city": city, "afac_country": country, "reason": "sin coincidencia"}
            )
            continue

        placed = airports[airports["airport_iata"].isin([code for code, _ in kept])]
        spread = _spread_km(placed)
        if spread > MAX_CITY_SPREAD_KM:
            raise AmbiguousCityError(
                f"{city!r} ({country}) resolved to airports {sorted(code for code, _ in kept)} "
                f"spanning {spread:,.0f} km; exclude the homonym in {CITY_OVERRIDE_FILE}"
            )
        for code, method in kept:
            rows.append(
                {
                    "afac_city": city,
                    "afac_country": country,
                    "airport_iata": code,
                    "match_method": method,
                    "city_spread_km": round(spread, 1),
                }
            )

    crosswalk = pd.DataFrame(rows).sort_values(
        ["afac_country", "afac_city", "airport_iata"], ignore_index=True
    )
    return crosswalk, pd.DataFrame(unresolved)


def load_carrier_crosswalk(reference_dir: Path | None = None) -> pd.DataFrame:
    """The reviewed AFAC airline to IATA/ICAO table, resolved rows and all."""

    frame = pd.read_csv(_reference_dir(reference_dir) / CARRIER_CROSSWALK_FILE).fillna("")
    duplicated = frame["afac_carrier_name"].duplicated()
    if duplicated.any():
        raise ValueError(
            "duplicate AFAC carrier name(s): "
            + ", ".join(sorted(frame.loc[duplicated, "afac_carrier_name"]))
        )
    return frame


def city_coverage(routes: pd.DataFrame, crosswalk: pd.DataFrame) -> list[CoverageReport]:
    """Coverage per month in routes, flights and AFAC passengers.

    A route counts as covered only when **both** endpoints resolve: a leg with
    one unplaceable end cannot enter the cube at all.
    """

    resolved = set(zip(crosswalk["afac_city"], crosswalk["afac_country"]))
    frame = routes.copy()
    frame["covered"] = [
        (origin, origin_country) in resolved and (destination, destination_country) in resolved
        for origin, origin_country, destination, destination_country in zip(
            frame["origen"], frame["pais_origen"], frame["destino"], frame["pais_destino"]
        )
    ]
    reports: list[CoverageReport] = []
    for period_id, group in frame.groupby("period_id"):
        covered = group[group["covered"]]
        reports.append(
            CoverageReport(
                period_id=str(period_id),
                routes_total=int(len(group)),
                routes_covered=int(len(covered)),
                flights_total=int(group["vuelos"].sum()),
                flights_covered=int(covered["vuelos"].sum()),
                passengers_total=int(group["pasajeros"].sum()),
                passengers_covered=int(covered["pasajeros"].sum()),
            )
        )
    return reports


def carrier_coverage(
    carriers: pd.DataFrame, crosswalk: pd.DataFrame
) -> list[CoverageReport]:
    """Coverage per month of the carrier margin, weighted by its passengers.

    Routes and flights are not available on this margin, so their fields
    repeat the carrier counts rather than pretending to a precision the source
    does not offer.
    """

    resolved = set(
        crosswalk.loc[crosswalk["confidence"].isin(USABLE_CONFIDENCE), "afac_carrier_name"]
    )
    frame = carriers.copy()
    frame["covered"] = frame["carrier_name"].isin(resolved)
    reports: list[CoverageReport] = []
    for period_id, group in frame.groupby("period_id"):
        covered = group[group["covered"]]
        reports.append(
            CoverageReport(
                period_id=str(period_id),
                routes_total=int(group["carrier_name"].nunique()),
                routes_covered=int(covered["carrier_name"].nunique()),
                flights_total=int(group["carrier_name"].nunique()),
                flights_covered=int(covered["carrier_name"].nunique()),
                passengers_total=int(group["pasajeros"].sum()),
                passengers_covered=int(covered["pasajeros"].sum()),
            )
        )
    return reports


def carriers_missing_from_crosswalk(
    carriers: pd.DataFrame, crosswalk: pd.DataFrame
) -> pd.DataFrame:
    """Margin airlines the crosswalk never mentions at all.

    This is a louder failure than an unresolved code and deserves its own
    report: an unresolved airline was seen and judged, while a missing one
    means the crosswalk and the margin disagree about what the universe even
    contains.  It is usually a spelling drift -- AFAC publishes
    ``United Airlines, Inc.`` and a crosswalk row saying ``United Airlines``
    silently removes nine per cent of the market.
    """

    known = set(crosswalk["afac_carrier_name"])
    frame = carriers[~carriers["carrier_name"].isin(known)]
    if frame.empty:
        return pd.DataFrame(columns=["carrier_name", "pasajeros", "share_pct"])
    total = carriers["pasajeros"].sum()
    grouped = (
        frame.groupby("carrier_name", as_index=False)["pasajeros"].sum()
        .sort_values("pasajeros", ascending=False, ignore_index=True)
    )
    grouped["share_pct"] = 100 * grouped["pasajeros"] / total
    return grouped


def unresolved_carrier_weight(
    carriers: pd.DataFrame, crosswalk: pd.DataFrame
) -> pd.DataFrame:
    """Every unresolved airline with the AFAC passengers it would take out."""

    unresolved = crosswalk[~crosswalk["confidence"].isin(USABLE_CONFIDENCE)]
    frame = carriers[carriers["carrier_name"].isin(set(unresolved["afac_carrier_name"]))]
    if frame.empty:
        return pd.DataFrame(columns=["carrier_name", "pasajeros", "share_pct"])
    total = carriers["pasajeros"].sum()
    grouped = (
        frame.groupby("carrier_name", as_index=False)["pasajeros"].sum()
        .sort_values("pasajeros", ascending=False, ignore_index=True)
    )
    grouped["share_pct"] = 100 * grouped["pasajeros"] / total
    return grouped


def build(
    *, reference_dir: Path | None = None, gold_dir: Path | None = None, write: bool = True
) -> dict[str, object]:
    """Build both crosswalks from the margins already on disk and report coverage."""

    reference = _reference_dir(reference_dir)
    routes = pd.read_csv(reference / ROUTE_MARGIN_FILE)
    carriers = pd.read_csv(reference / CARRIER_MARGIN_FILE)

    cities, unresolved_cities = build_city_crosswalk(
        routes, reference_dir=reference_dir, gold_dir=gold_dir
    )
    carrier_map = load_carrier_crosswalk(reference_dir)
    if write:
        cities.to_csv(reference / CITY_CROSSWALK_FILE, index=False)

    return {
        "cities": cities,
        "unresolved_cities": unresolved_cities,
        "carriers": carrier_map,
        "city_coverage": city_coverage(routes, cities),
        "carrier_coverage": carrier_coverage(carriers, carrier_map),
        "unresolved_carriers": unresolved_carrier_weight(carriers, carrier_map),
        "missing_carriers": carriers_missing_from_crosswalk(carriers, carrier_map),
        "routes": routes,
        "carrier_margin": carriers,
    }


def main(argv: list[str] | None = None) -> int:  # pragma: no cover - manual entry
    import argparse

    parser = argparse.ArgumentParser(prog="python -m src.ingest.afac.international_crosswalks")
    parser.add_argument("--dry-run", action="store_true", help="report without writing")
    args = parser.parse_args(argv)

    result = build(write=not args.dry_run)
    cities: pd.DataFrame = result["cities"]
    print(
        f"ciudades: {cities.groupby(['afac_city', 'afac_country']).ngroups:,} etiquetas "
        f"-> {len(cities):,} aeropuertos "
        f"({cities['match_method'].value_counts().to_dict()})"
    )
    unresolved_cities: pd.DataFrame = result["unresolved_cities"]
    print(f"etiquetas de ciudad sin resolver: {len(unresolved_cities)}")
    for row in unresolved_cities.itertuples(index=False):
        print(f"   {row.afac_city!r} ({row.afac_country}): {row.reason}")

    carriers: pd.DataFrame = result["carriers"]
    counts = carriers["confidence"].value_counts().to_dict()
    print(f"\naerolineas: {len(carriers)} etiquetas ({counts})")

    print("\ncobertura de rutas por mes (rutas / vuelos / pasajeros):")
    for report in result["city_coverage"]:
        print(
            f"  {report.period_id}  "
            f"{report.route_share:7.2%}  {report.flight_share:7.2%}  {report.passenger_share:7.2%}"
        )
    probable = carriers[carriers["confidence"] == "probable"]
    if not probable.empty:
        print(
            f"   de ellas {len(probable)} son 'probable': identidad documentada, "
            "sin confirmar todavia contra una captura"
        )
    print("\ncobertura de la marginal por aerolinea (empresas / pasajeros):")
    for report in result["carrier_coverage"]:
        print(
            f"  {report.period_id}  {report.routes_covered:>2}/{report.routes_total:<2}  "
            f"{report.passenger_share:7.2%}"
        )
    missing: pd.DataFrame = result["missing_carriers"]
    if not missing.empty:
        print("\nAEROLINEAS DEL MARGEN AUSENTES DEL CROSSWALK (revisar la escritura):")
        for row in missing.itertuples(index=False):
            print(f"  {row.pasajeros:>10,}  {row.share_pct:5.2f}%  {row.carrier_name!r}")
    unresolved_carriers: pd.DataFrame = result["unresolved_carriers"]
    if not unresolved_carriers.empty:
        print("\naerolineas sin resolver, por pasajeros AFAC del periodo completo:")
        for row in unresolved_carriers.itertuples(index=False):
            print(f"  {row.pasajeros:>10,}  {row.share_pct:5.2f}%  {row.carrier_name}")
    return 0


if __name__ == "__main__":  # pragma: no cover - manual entry point
    raise SystemExit(main())
