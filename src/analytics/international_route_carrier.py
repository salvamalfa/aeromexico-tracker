"""Turn an international capture into the three frames the estimator fits, or refuse.

:mod:`src.analytics.route_carrier` already knows how to fit a cube to two
margins.  What it cannot do is decide whether a *particular* international
capture is fit to be fitted, and that decision is where this module lives.

The domestic gate could be simple because its universe is small and closed:
nine Mexican scheduled carriers, 58 airports, one publication.  The
international cube is none of those things, and every extra degree of freedom
is a way to produce a confident wrong number:

- both directions of a market are captured from *different* sides -- one as a
  departure from Mexico, one as an arrival into it -- so a market can arrive
  half-observed without anything looking broken;
- an operator arrives as a code, not as a name, and a code the crosswalk has
  not reviewed must not be quietly folded into a neighbour;
- roughly one record in five arrives with ``codeshareStatus`` unknown, which
  means the provider guessed whether it was the operating carrier, and the
  guess lands squarely on the within-route proportions that are the seed's
  entire content;
- AFAC publishes flights performed, while a schedule feed can carry flights
  that never flew, so the two flight counts are related but not the same
  measurement.

Each of those is measured and reported as a finding rather than folded into a
single pass/fail, because an operator has to be able to see *which* property
failed before deciding whether a partial fit is still worth having.

Nothing here fits anything or publishes anything.  The method, the thresholds
and the gates that follow are in
``docs/estimacion-pasajeros-ruta-aerolinea.md``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

from src.analytics.route_carrier import SEED_COLUMNS
from src.ingest.afac.international_crosswalks import USABLE_CONFIDENCE


ACCEPTANCE_VERSION = "international_seed_acceptance_v1"

# Mirrors the domestic gate so the two verdicts mean the same thing.
ROUTE_COVERAGE_PASS = 0.95
CARRIER_COVERAGE_PASS = 0.95
COLUMN_SCALE_TOLERANCE = 0.05
# Measured at 17.6% in the probe of 2026-09-10.  Above this share the seed's
# within-route proportions rest more on the provider's heuristic than on a
# declared operating status, and the fit should not be read as evidence.
UNKNOWN_CODESHARE_REJECT = 0.25
UNKNOWN_CODESHARE_REVIEW = 0.05
# A sampled week cannot reproduce a month's flights, so the ratio of seed
# flights to AFAC flights is only informative about its *spread* across routes.
# A route seen far more often than AFAC reports is the diagnostic that matters:
# it means schedule, not operation.
FLIGHT_RATIO_REVIEW = 1.20

VERDICT_ACCEPT = "accept"
VERDICT_REVIEW = "review"
VERDICT_REJECT = "reject"

# What a capture must carry for this module to read it.
CAPTURE_COLUMNS = (
    "period_id",
    "origin_iata",
    "dest_iata",
    "operator_key",
    "operator_iata",
    "operator_icao",
    "flights",
    "codeshare_unknown",
    "status_incomplete",
)

# Aeroméxico flights the capture could not split between Aerovías and Connect.
UNSPLIT_AEROMEXICO = "AEROMEXICO_UNSPLIT"


class CityLabelCollisionError(ValueError):
    """Two countries publish the same city label, so a route key is ambiguous."""


@dataclass(frozen=True, slots=True)
class Finding:
    """One measured property of a capture, and whether it blocks the fit."""

    code: str
    severity: str  # "reject", "review" or "note"
    detail: str
    value: float | None = None

    def __str__(self) -> str:  # pragma: no cover - presentation only
        measured = "" if self.value is None else f" [{self.value:,.4f}]"
        return f"{self.severity.upper():6s} {self.code}: {self.detail}{measured}"


@dataclass(frozen=True, slots=True)
class AcceptanceReport:
    """Everything needed to accept, review or refuse one month's capture."""

    period_id: str
    acceptance_version: str
    route_passenger_coverage: float
    carrier_passenger_coverage: float
    column_scale: float
    unknown_codeshare_share: float
    status_incomplete_share: float
    seed_routes: int
    seed_carriers: int
    findings: tuple[Finding, ...] = field(default_factory=tuple)

    @property
    def verdict(self) -> str:
        severities = {finding.severity for finding in self.findings}
        if "reject" in severities:
            return VERDICT_REJECT
        if "review" in severities:
            return VERDICT_REVIEW
        return VERDICT_ACCEPT

    @property
    def usable(self) -> bool:
        return self.verdict in {VERDICT_ACCEPT, VERDICT_REVIEW}


def _require(frame: pd.DataFrame, columns: tuple[str, ...], name: str) -> None:
    missing = [column for column in columns if column not in frame.columns]
    if missing:
        raise ValueError(f"{name} is missing required column(s): {', '.join(missing)}")


def city_lookup(city_crosswalk: pd.DataFrame) -> dict[str, str]:
    """Airport code to AFAC city label, refusing a label two countries share.

    The margins key a route by city alone, so if two countries published the
    same label the route key would silently merge them.  AFAC disambiguates in
    the label itself (``SAN JOSE, COSTA RICA`` against
    ``SAN JOSE, CALIFORNIA``); this checks that it always has.
    """

    labels = city_crosswalk.groupby("afac_city")["afac_country"].nunique()
    collisions = sorted(labels[labels > 1].index)
    if collisions:
        raise CityLabelCollisionError(
            "city label(s) used by more than one country: " + ", ".join(collisions)
        )
    return dict(zip(city_crosswalk["airport_iata"], city_crosswalk["afac_city"]))


def carrier_lookup(carrier_crosswalk: pd.DataFrame) -> dict[str, str]:
    """Operator code to ``carrier_key``, for the codes review has cleared.

    Both IATA and ICAO are indexed because the provider populates whichever it
    has, and has been observed putting an ICAO code in the IATA field.  A code
    claimed by two different carriers is left out rather than resolved by
    preference: the gate reports it as ambiguous.
    """

    usable = carrier_crosswalk[carrier_crosswalk["confidence"].isin(USABLE_CONFIDENCE)]
    claims: dict[str, set[str]] = {}
    for row in usable.itertuples(index=False):
        for code in (row.iata, row.icao):
            code = str(code or "").strip().upper()
            if code:
                claims.setdefault(code, set()).add(row.carrier_key)
    return {code: next(iter(keys)) for code, keys in claims.items() if len(keys) == 1}


def ambiguous_operator_codes(carrier_crosswalk: pd.DataFrame) -> dict[str, set[str]]:
    """Codes two reviewed carriers both claim; never resolved by preference."""

    usable = carrier_crosswalk[carrier_crosswalk["confidence"].isin(USABLE_CONFIDENCE)]
    claims: dict[str, set[str]] = {}
    for row in usable.itertuples(index=False):
        for code in (row.iata, row.icao):
            code = str(code or "").strip().upper()
            if code:
                claims.setdefault(code, set()).add(row.carrier_key)
    return {code: keys for code, keys in claims.items() if len(keys) > 1}


def build_international_seed(
    capture: pd.DataFrame,
    city_crosswalk: pd.DataFrame,
    carrier_crosswalk: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Map a capture onto the estimator's seed contract, keeping what it dropped.

    Returns ``(seed, rejected)``.  ``seed`` carries
    :data:`~src.analytics.route_carrier.SEED_COLUMNS` plus the two diagnostics
    the gate needs; ``rejected`` carries every capture row that could not be
    placed, with the reason, so nothing disappears without a count.
    """

    _require(capture, CAPTURE_COLUMNS, "capture")
    cities = city_lookup(city_crosswalk)
    carriers = carrier_lookup(carrier_crosswalk)

    frame = capture.copy()
    frame["origin_city"] = frame["origin_iata"].map(cities)
    frame["dest_city"] = frame["dest_iata"].map(cities)
    codes = frame["operator_iata"].fillna("").str.upper().where(
        lambda column: column != "", frame["operator_icao"].fillna("").str.upper()
    )
    # A project carrier_key already assigned by the adapter wins: it encodes the
    # fleet split between Aerovías and Connect that no code can express.
    known_keys = set(carrier_crosswalk["carrier_key"])
    frame["carrier_key"] = np.where(
        frame["operator_key"].isin(known_keys),
        frame["operator_key"],
        codes.map(carriers),
    )

    reasons = []
    for row in frame.itertuples(index=False):
        if not isinstance(row.origin_city, str) or not isinstance(row.dest_city, str):
            reasons.append("aeropuerto sin ciudad AFAC")
        elif row.operator_key == UNSPLIT_AEROMEXICO:
            reasons.append("Aeromexico sin separar Aerovias/Connect")
        elif not isinstance(row.carrier_key, str) or not row.carrier_key:
            reasons.append("operador sin carrier_key revisado")
        else:
            reasons.append("")
    frame["rejection_reason"] = reasons

    rejected = frame[frame["rejection_reason"] != ""].copy()
    kept = frame[frame["rejection_reason"] == ""].copy()
    if kept.empty:
        empty = pd.DataFrame(
            columns=[*SEED_COLUMNS, "codeshare_unknown", "status_incomplete"]
        )
        return empty, rejected

    kept["route_key"] = kept["origin_city"] + "-" + kept["dest_city"]
    kept = kept.rename(columns={"flights": "weight"})
    seed = (
        kept.groupby(["period_id", "route_key", "carrier_key"], as_index=False)[
            ["weight", "codeshare_unknown", "status_incomplete"]
        ]
        .sum()
        .loc[:, [*SEED_COLUMNS, "codeshare_unknown", "status_incomplete"]]
    )
    return seed[seed["weight"] > 0].reset_index(drop=True), rejected


def build_international_margins(
    routes: pd.DataFrame, carrier_margin: pd.DataFrame, carrier_crosswalk: pd.DataFrame
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Shape both AFAC margins into the estimator's contract, at the same grain."""

    route_totals = (
        routes.assign(route_key=routes["origen"] + "-" + routes["destino"])
        .rename(columns={"pasajeros": "passengers"})
        .groupby(["period_id", "route_key"], as_index=False)["passengers"]
        .sum()
    )
    usable = carrier_crosswalk[carrier_crosswalk["confidence"].isin(USABLE_CONFIDENCE)]
    by_name = dict(zip(usable["afac_carrier_name"], usable["carrier_key"]))
    carriers = carrier_margin.copy()
    carriers["carrier_key"] = carriers["carrier_name"].map(by_name)
    carrier_totals = (
        carriers.dropna(subset=["carrier_key"])
        .rename(columns={"pasajeros": "passengers"})
        .groupby(["period_id", "carrier_key"], as_index=False)["passengers"]
        .sum()
    )
    return route_totals, carrier_totals


def afac_route_flights(routes: pd.DataFrame) -> pd.DataFrame:
    """Flights per directional route and month, the free contrast for coverage."""

    return (
        routes.assign(route_key=routes["origen"] + "-" + routes["destino"])
        .rename(columns={"vuelos": "flights"})
        .groupby(["period_id", "route_key"], as_index=False)["flights"]
        .sum()
    )


def assess_international_seed(
    capture: pd.DataFrame,
    seed: pd.DataFrame,
    rejected: pd.DataFrame,
    route_totals: pd.DataFrame,
    carrier_totals: pd.DataFrame,
    afac_flights: pd.DataFrame,
    carrier_crosswalk: pd.DataFrame,
    *,
    period_id: str,
) -> AcceptanceReport:
    """Measure one month's capture against everything that can silently spoil it."""

    findings: list[Finding] = []
    period_seed = seed[seed["period_id"] == period_id]
    period_routes = route_totals[route_totals["period_id"] == period_id]
    period_carriers = carrier_totals[carrier_totals["period_id"] == period_id]
    period_capture = capture[capture["period_id"] == period_id]
    period_flights = afac_flights[afac_flights["period_id"] == period_id]

    if period_seed.empty:
        findings.append(Finding("sin_semilla", "reject", f"No hay semilla para {period_id}"))
        return AcceptanceReport(
            period_id, ACCEPTANCE_VERSION, 0.0, 0.0, float("nan"), float("nan"),
            float("nan"), 0, 0, tuple(findings),
        )

    # 1. Duplicates.  Two rows for one leg double its weight inside its route.
    keys = ["period_id", "origin_iata", "dest_iata", "operator_key"]
    duplicated = int(period_capture.duplicated(subset=keys).sum())
    if duplicated:
        findings.append(
            Finding(
                "duplicados", "reject",
                f"{duplicated} filas repiten periodo, ruta y operador",
                float(duplicated),
            )
        )

    # 2. Lost directions.  Both legs of a market are captured from opposite
    # ends, so one can go missing without anything else looking wrong.
    seed_pairs = set(period_seed["route_key"])
    margin_pairs = set(period_routes["route_key"])
    def _reverse(key: str) -> str:
        origin, _, destination = key.partition("-")
        return f"{destination}-{origin}"
    one_way = sorted(
        key for key in seed_pairs
        if _reverse(key) in margin_pairs and _reverse(key) not in seed_pairs
    )
    if one_way:
        findings.append(
            Finding(
                "direcciones_perdidas", "review",
                f"{len(one_way)} rutas con un solo sentido en la semilla; "
                f"AFAC publica ambos (p. ej. {one_way[0]})",
                float(len(one_way)),
            )
        )

    # 3. Ambiguous operators, both in the crosswalk and in the capture.
    ambiguous = ambiguous_operator_codes(carrier_crosswalk)
    if ambiguous:
        findings.append(
            Finding(
                "operadores_ambiguos", "reject",
                "codigos reclamados por dos aerolineas: "
                + ", ".join(f"{code}->{sorted(keys)}" for code, keys in sorted(ambiguous.items())),
                float(len(ambiguous)),
            )
        )
    unsplit = float(
        rejected.loc[
            rejected["rejection_reason"] == "Aeromexico sin separar Aerovias/Connect",
            "flights",
        ].sum()
    )
    if unsplit:
        findings.append(
            Finding(
                "aeromexico_sin_separar", "review",
                f"{unsplit:,.0f} vuelos de Aeromexico sin modelo de aeronave quedaron fuera",
                unsplit,
            )
        )
    unmapped = float(
        rejected.loc[
            rejected["rejection_reason"] == "operador sin carrier_key revisado", "flights"
        ].sum()
    )
    if unmapped:
        findings.append(
            Finding(
                "operadores_sin_revisar", "review",
                f"{unmapped:,.0f} vuelos de operadores sin entrada revisada en el crosswalk",
                unmapped,
            )
        )

    # 4. Unresolved code-shares: how much of the seed rests on a heuristic.
    total_weight = float(period_seed["weight"].sum())
    unknown_share = (
        float(period_seed["codeshare_unknown"].sum()) / total_weight if total_weight else float("nan")
    )
    if np.isfinite(unknown_share):
        if unknown_share > UNKNOWN_CODESHARE_REJECT:
            findings.append(
                Finding(
                    "codeshare_sin_resolver", "reject",
                    f"{unknown_share:.1%} de la semilla llega con codeshareStatus desconocido",
                    unknown_share,
                )
            )
        elif unknown_share > UNKNOWN_CODESHARE_REVIEW:
            findings.append(
                Finding(
                    "codeshare_sin_resolver", "review",
                    f"{unknown_share:.1%} de la semilla llega con codeshareStatus desconocido",
                    unknown_share,
                )
            )

    # 5. Schedule against operation.
    incomplete_share = (
        float(period_seed["status_incomplete"].sum()) / total_weight if total_weight else float("nan")
    )
    if np.isfinite(incomplete_share) and incomplete_share > 0:
        findings.append(
            Finding(
                "estado_no_operado", "note",
                f"{incomplete_share:.1%} de la semilla no declara un estado de vuelo "
                "completado; AFAC cuenta vuelos realizados",
                incomplete_share,
            )
        )

    # 6. Coverage, weighted by the passengers each margin publishes.
    covered_routes = period_routes[period_routes["route_key"].isin(seed_pairs)]
    route_coverage = (
        float(covered_routes["passengers"].sum()) / float(period_routes["passengers"].sum())
        if period_routes["passengers"].sum()
        else float("nan")
    )
    seed_carriers = set(period_seed["carrier_key"])
    covered_carriers = period_carriers[period_carriers["carrier_key"].isin(seed_carriers)]
    carrier_coverage = (
        float(covered_carriers["passengers"].sum()) / float(period_carriers["passengers"].sum())
        if period_carriers["passengers"].sum()
        else float("nan")
    )
    for label, value, threshold in (
        ("cobertura_rutas", route_coverage, ROUTE_COVERAGE_PASS),
        ("cobertura_aerolineas", carrier_coverage, CARRIER_COVERAGE_PASS),
    ):
        if not np.isfinite(value) or value < threshold:
            findings.append(
                Finding(
                    label, "reject",
                    f"{value:.2%} de los pasajeros AFAC quedan dentro de la semilla, "
                    f"umbral {threshold:.0%}",
                    value,
                )
            )
        elif value < 1.0:
            findings.append(
                Finding(
                    label, "review",
                    f"cobertura parcial: {value:.2%} de los pasajeros AFAC",
                    value,
                )
            )

    # 7. Compatible margins.
    row_total = float(covered_routes["passengers"].sum())
    column_total = float(covered_carriers["passengers"].sum())
    column_scale = row_total / column_total if column_total else float("nan")
    if not np.isfinite(column_scale) or abs(column_scale - 1.0) > COLUMN_SCALE_TOLERANCE:
        findings.append(
            Finding(
                "margenes_incompatibles", "reject",
                f"column_scale {column_scale:.4f} fuera de ±{COLUMN_SCALE_TOLERANCE:.0%}",
                column_scale,
            )
        )

    # 8. Structural support, checked before the fit rather than by its failure.
    supply_by_route = period_seed.groupby("route_key")["weight"].sum()
    starved_routes = sorted(
        set(covered_routes.loc[covered_routes["passengers"] > 0, "route_key"])
        - set(supply_by_route[supply_by_route > 0].index)
    )
    if starved_routes:
        findings.append(
            Finding(
                "soporte_inviable_rutas", "reject",
                f"{len(starved_routes)} rutas con pasajeros y sin oferta en la semilla",
                float(len(starved_routes)),
            )
        )
    supply_by_carrier = period_seed.groupby("carrier_key")["weight"].sum()
    starved_carriers = sorted(
        set(covered_carriers.loc[covered_carriers["passengers"] > 0, "carrier_key"])
        - set(supply_by_carrier[supply_by_carrier > 0].index)
    )
    if starved_carriers:
        findings.append(
            Finding(
                "soporte_inviable_aerolineas", "reject",
                "aerolineas con pasajeros y sin ruta en la semilla: "
                + ", ".join(starved_carriers[:5]),
                float(len(starved_carriers)),
            )
        )

    # 9. Seed flights against the flights AFAC publishes for the same route.
    merged = supply_by_route.rename("seed_flights").reset_index().merge(
        period_flights, on="route_key", how="inner"
    )
    merged = merged[merged["flights"] > 0]
    if not merged.empty:
        ratio = float(merged["seed_flights"].sum() / merged["flights"].sum())
        overshooting = merged[merged["seed_flights"] > FLIGHT_RATIO_REVIEW * merged["flights"]]
        if len(overshooting):
            findings.append(
                Finding(
                    "vuelos_por_encima_de_afac", "review",
                    f"{len(overshooting)} rutas con mas vuelos en la semilla que en AFAC; "
                    "programacion y operacion pueden diferir",
                    float(len(overshooting)),
                )
            )
        findings.append(
            Finding(
                "razon_vuelos_semilla_afac", "note",
                f"la semilla contiene {ratio:.2f} veces los vuelos que AFAC publica "
                "en las rutas comparables",
                ratio,
            )
        )

    return AcceptanceReport(
        period_id=period_id,
        acceptance_version=ACCEPTANCE_VERSION,
        route_passenger_coverage=route_coverage,
        carrier_passenger_coverage=carrier_coverage,
        column_scale=column_scale,
        unknown_codeshare_share=unknown_share,
        status_incomplete_share=incomplete_share,
        seed_routes=int(period_seed["route_key"].nunique()),
        seed_carriers=int(period_seed["carrier_key"].nunique()),
        findings=tuple(findings),
    )


def group_aeromexico(estimate: pd.DataFrame) -> pd.DataFrame:
    """Sum Aerovías and Connect into Grupo Aeroméxico **after** the fit.

    The order is the whole point.  Each airline is fitted against its own
    published total, because AFAC publishes them separately; only then are the
    two cells added for display.  Fitting the pair against a route total that
    belongs to every airline would hand them Volaris' and Iberia's passengers.

    The subsidiary rows are kept, not replaced, so the internal lineage
    survives the aggregation.
    """

    parts = {"AEROMEXICO", "AEROMEXICO_CONNECT"}
    own = estimate[estimate["carrier_key"].isin(parts)]
    if own.empty:
        return estimate
    value_columns = [
        column
        for column in ("passengers_estimated", "passengers_estimated_low", "passengers_estimated_high")
        if column in own.columns
    ]
    grouped = (
        own.groupby(["period_id", "route_key"], as_index=False)[value_columns].sum()
        .assign(carrier_key="AEROMEXICO_GROUP", carrier_label="Grupo Aeroméxico")
    )
    return pd.concat([estimate, grouped], ignore_index=True)


def observed_cells_to_exclude(
    estimate: pd.DataFrame, observed: pd.DataFrame
) -> pd.DataFrame:
    """Mark fitted cells that T-100 already observes, so nothing is counted twice.

    T-100 never enters the fit.  It arrives here, afterwards, to say which
    cells must be *published* from observation instead of from the estimate.
    The fitted value is kept beside it as a diagnostic — their difference is
    the estimator's measured error — but the two are never summed into one
    total.
    """

    if observed.empty:
        return estimate.assign(display_source="estimated")
    keys = set(zip(observed["period_id"], observed["route_key"], observed["carrier_key"]))
    marked = estimate.copy()
    marked["display_source"] = [
        "observed_t100" if (period, route, carrier) in keys else "estimated"
        for period, route, carrier in zip(
            marked["period_id"], marked["route_key"], marked["carrier_key"]
        )
    ]
    return marked


def format_report(report: AcceptanceReport) -> str:
    """A human-readable verdict, findings first."""

    lines = [
        f"{report.period_id}  veredicto: {report.verdict.upper()}  "
        f"({report.acceptance_version})",
        f"  cobertura rutas      {report.route_passenger_coverage:7.2%}",
        f"  cobertura aerolineas {report.carrier_passenger_coverage:7.2%}",
        f"  column_scale         {report.column_scale:7.4f}",
        f"  codeshare desconocido{report.unknown_codeshare_share:7.2%}",
        f"  semilla              {report.seed_routes:,} rutas x {report.seed_carriers} operadores",
    ]
    lines.extend(f"  {finding}" for finding in report.findings)
    return "\n".join(lines)


# --------------------------------------------------------------------------
# A rehearsal on real data, with no capture and no API units
# --------------------------------------------------------------------------

def t100_substitute_capture(
    period_ids: tuple[str, ...], *, gold_dir: Path | None = None
) -> pd.DataFrame:
    """Shape T-100 into the capture contract, as a stand-in for a real seed.

    There is no international capture yet, and inventing one would prove
    nothing.  T-100 is a real observation of flights by route and operator for
    the Mexico-United States part of the same cube, so it can stand in for the
    seed's *shape* while the margins stay exactly as AFAC published them.

    What this rehearses is the plumbing -- crosswalks, grain, contracts, the
    gate's findings -- on real rows.  What it deliberately does **not** do is
    pretend to be the capture: it covers only the United States, so the gate
    should refuse it on coverage, and that refusal is the point.
    """

    import duckdb

    from src.config import PATHS

    gold = gold_dir or PATHS.gold
    placeholders = ", ".join("?" for _ in period_ids)
    query = f"""
        SELECT f.period_id,
               r.origin_iata,
               r.dest_iata,
               f.carrier_key AS operator_key,
               SUM(f.departures_performed) AS flights
        FROM read_parquet(?) f
        JOIN read_parquet(?) r USING (route_key)
        WHERE r.is_transborder_us
          AND f.period_id IN ({placeholders})
          AND f.departures_performed > 0
        GROUP BY 1, 2, 3, 4
    """
    connection = duckdb.connect()
    try:
        frame = connection.execute(
            query,
            [
                str(gold / "fact_route_traffic.parquet"),
                str(gold / "dim_route.parquet"),
                *period_ids,
            ],
        ).df()
    finally:
        connection.close()

    bts = pd.read_csv(PATHS.root / "config" / "carrier_crosswalk.csv")
    iata_by_key = (
        bts.dropna(subset=["unique_carrier"])
        .drop_duplicates("carrier_key")
        .set_index("carrier_key")["unique_carrier"]
        .to_dict()
    )
    frame["operator_iata"] = frame["operator_key"].map(iata_by_key).fillna("")
    frame["operator_icao"] = ""
    # T-100 publishes performed departures and nothing about code-shares, so
    # both diagnostics are zero by construction, not by measurement.
    frame["codeshare_unknown"] = 0.0
    frame["status_incomplete"] = 0.0
    return frame


def main(argv: list[str] | None = None) -> int:  # pragma: no cover - manual entry
    import argparse

    from src.config import PATHS
    from src.ingest.afac.international_crosswalks import (
        CARRIER_CROSSWALK_FILE,
        CARRIER_MARGIN_FILE,
        CITY_CROSSWALK_FILE,
        ROUTE_MARGIN_FILE,
    )

    parser = argparse.ArgumentParser(prog="python -m src.analytics.international_route_carrier")
    parser.add_argument(
        "--periods", default="2026M01,2026M02,2026M03,2026M04,2026M05",
        help="months to rehearse; only months T-100 already covers",
    )
    args = parser.parse_args(argv)
    periods = tuple(period.strip() for period in args.periods.split(",") if period.strip())

    reference = PATHS.data / "reference"
    routes = pd.read_csv(reference / ROUTE_MARGIN_FILE)
    carrier_margin = pd.read_csv(reference / CARRIER_MARGIN_FILE)
    cities = pd.read_csv(reference / CITY_CROSSWALK_FILE)
    carriers = pd.read_csv(reference / CARRIER_CROSSWALK_FILE).fillna("")

    capture = t100_substitute_capture(periods)
    seed, rejected = build_international_seed(capture, cities, carriers)
    route_totals, carrier_totals = build_international_margins(routes, carrier_margin, carriers)
    flights = afac_route_flights(routes)

    print(
        "ENSAYO con semilla sustituta de T-100 (solo Mexico-EE. UU.). "
        "No es una captura: la puerta debe rechazarla por cobertura.\n"
    )
    print(
        f"capture: {len(capture):,} filas  ->  seed: {len(seed):,} filas, "
        f"{len(rejected):,} descartadas"
    )
    if not rejected.empty:
        print("  motivos: " + str(rejected["rejection_reason"].value_counts().to_dict()))
    print()
    for period_id in periods:
        report = assess_international_seed(
            capture, seed, rejected, route_totals, carrier_totals, flights, carriers,
            period_id=period_id,
        )
        print(format_report(report))
        print()
    return 0


if __name__ == "__main__":  # pragma: no cover - manual entry point
    raise SystemExit(main())
