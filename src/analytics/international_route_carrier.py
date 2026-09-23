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
import json
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
# Share of captured flights at airports the city crosswalk does not place.
AIRPORT_UNPLACED_REJECT = 0.01

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


def reverse_route_key(route_key: str, known: set[str]) -> str | None:
    """The opposite direction of ``route_key`` if it is among ``known`` routes.

    City labels can contain hyphens (``DALLAS-FORT WORTH``), so every hyphen
    is tried as the split point and only a reverse that exists is returned.
    """

    for index, char in enumerate(route_key):
        if char == "-":
            reverse = f"{route_key[index + 1:]}-{route_key[:index]}"
            if reverse in known:
                return reverse
    return None


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
    # Only reviewed carriers: an unresolved one has no column in the carrier
    # margin, so a route it alone serves would have no feasible fit.
    known_keys = set(
        carrier_crosswalk.loc[
            carrier_crosswalk["confidence"].isin(USABLE_CONFIDENCE), "carrier_key"
        ]
    )
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
    # Two passes may both reach one pair legitimately: a direct flight on the
    # first airport's board and a different flight through a Mexican stop
    # rebuilt on the stop's board.  Anything else seen twice is one leg twice.
    keys = ["period_id", "origin_iata", "dest_iata", "operator_key"]
    through = (
        period_capture["through_flights"]
        if "through_flights" in period_capture
        else pd.Series(0.0, index=period_capture.index)
    )
    direct_rows = period_capture[~np.isclose(through, period_capture["flights"])]
    duplicated = int(direct_rows.duplicated(subset=keys).sum())
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
    one_way = sorted(
        key for key in seed_pairs
        if (reverse := reverse_route_key(key, margin_pairs)) is not None
        and reverse not in seed_pairs
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

    # A captured airport the city crosswalk does not place.  Coverage cannot
    # see this when the city has another, mapped airport: the route keeps
    # passengers but loses part of its supply, and its proportions tilt.
    period_rejected = rejected[rejected["period_id"] == period_id]
    # Only reviewed carriers count: a private jet to Van Nuys is outside AFAC's
    # scheduled universe whether or not its airport is placed.
    placeless = period_rejected[
        (period_rejected["rejection_reason"] == "aeropuerto sin ciudad AFAC")
        & period_rejected["carrier_key"].notna()
        & (period_rejected["carrier_key"].astype(str) != "")
    ]
    placeless_flights = float(placeless["flights"].sum())
    captured_flights = float(period_seed["weight"].sum()) + placeless_flights
    if placeless_flights and captured_flights:
        share = placeless_flights / captured_flights
        unplaced = set(placeless.loc[placeless["origin_city"].isna(), "origin_iata"]) | set(
            placeless.loc[placeless["dest_city"].isna(), "dest_iata"]
        )
        airports = ", ".join(sorted(unplaced))
        findings.append(
            Finding(
                "aeropuertos_sin_ciudad",
                "reject" if share > AIRPORT_UNPLACED_REJECT else "review",
                f"{placeless_flights:,.0f} vuelos de aerolineas revisadas ({share:.2%}) "
                f"en aeropuertos sin ciudad AFAC: {airports}",
                share,
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
    # The fit keeps only the routes and carriers that carry a margin, so the
    # supply that counts is the supply between those two sets -- not the seed.
    margin_routes = set(covered_routes.loc[covered_routes["passengers"] > 0, "route_key"])
    margin_carriers = set(covered_carriers.loc[covered_carriers["passengers"] > 0, "carrier_key"])
    fitted = period_seed[
        period_seed["route_key"].isin(margin_routes)
        & period_seed["carrier_key"].isin(margin_carriers)
    ]
    supply_by_route = fitted.groupby("route_key")["weight"].sum()
    starved_routes = sorted(margin_routes - set(supply_by_route[supply_by_route > 0].index))
    if starved_routes:
        findings.append(
            Finding(
                "soporte_inviable_rutas", "reject",
                f"{len(starved_routes)} rutas con pasajeros y sin oferta de una aerolinea "
                f"con marginal: {', '.join(starved_routes[:5])}",
                float(len(starved_routes)),
            )
        )
    supply_by_carrier = fitted.groupby("carrier_key")["weight"].sum()
    starved_carriers = sorted(margin_carriers - set(supply_by_carrier[supply_by_carrier > 0].index))
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


FAMILY_FILE = "afac_international_carrier_families.csv"
UNALLOCATED = "SIN_ASIGNAR"
UNALLOCATED_SEED_SHARE = 0.01
# A cap exactly at capacity leaves the solution on its boundary, which IPF
# only approaches asymptotically; half a per cent keeps it interior.
CAPACITY_CAP_SHARE = 0.995
# The international cube has many single-carrier routes sitting at their bound,
# where IPF approaches the solution only asymptotically.  One millionth of the
# month (about five passengers in April 2026) is immaterial and reachable; the
# domestic 1e-8 (a twentieth of a passenger) is not.
INTERNATIONAL_TOLERANCE = 1e-6
PROTECTED_FROM_POOLING = frozenset({"AEROMEXICO", "AEROMEXICO_CONNECT"})


def load_carrier_families(reference_dir: Path | None = None) -> pd.DataFrame:
    """Reviewed pools of carriers the seed cannot tell apart.

    AFAC attributes passengers to the operating carrier; the provider reports
    many regional flights under the marketing brand.  Where the two cannot be
    reconciled from the seed, the carriers are fitted as one column and
    published as that family.  Aerovías and Connect are never pooled.
    """

    from src.config import PATHS

    reference = reference_dir or PATHS.data / "reference"
    families = pd.read_csv(reference / FAMILY_FILE)
    pooled = set(families["carrier_key"]) & PROTECTED_FROM_POOLING
    if pooled:
        raise ValueError(f"these carriers are never pooled: {sorted(pooled)}")
    if families["carrier_key"].duplicated().any():
        raise ValueError("a carrier belongs to two families")
    return families


def _pool(frame: pd.DataFrame, families: pd.DataFrame) -> pd.DataFrame:
    mapping = dict(zip(families["carrier_key"], families["fit_key"]))
    return frame.assign(carrier_key=frame["carrier_key"].map(lambda key: mapping.get(key, key)))


def _max_flow(
    support: np.ndarray, route_caps: np.ndarray, carrier_caps: np.ndarray
) -> tuple[np.ndarray, np.ndarray]:
    """Dinic's max flow on source -> carrier -> route -> sink.

    Returns each carrier's placed flow and a mask of the carriers still
    reachable from the source in the residual graph: the set whose demand
    the routes it can reach cannot jointly absorb.
    """

    routes, carriers = support.shape
    source, sink = 0, 1 + carriers + routes
    graph: list[list[int]] = [[] for _ in range(sink + 1)]
    head: list[int] = []
    cap: list[float] = []

    def add(u: int, v: int, c: float) -> None:
        graph[u].append(len(head)); head.append(v); cap.append(c)
        graph[v].append(len(head)); head.append(u); cap.append(0.0)

    for k in range(carriers):
        add(source, 1 + k, float(carrier_caps[k]))
    infinite = float(route_caps.sum()) + 1.0
    for i, k in zip(*np.nonzero(support > 0)):
        add(1 + k, 1 + carriers + i, infinite)
    for i in range(routes):
        add(1 + carriers + i, sink, float(route_caps[i]))

    eps = 1e-9 * max(1.0, float(route_caps.sum()))
    while True:
        level = [-1] * (sink + 1)
        level[source] = 0
        queue = [source]
        for u in queue:
            for e in graph[u]:
                if cap[e] > eps and level[head[e]] < 0:
                    level[head[e]] = level[u] + 1
                    queue.append(head[e])
        if level[sink] < 0:
            break
        pointer = [0] * (sink + 1)

        def push(u: int, pushed: float) -> float:
            if u == sink:
                return pushed
            while pointer[u] < len(graph[u]):
                e = graph[u][pointer[u]]
                v = head[e]
                if cap[e] > eps and level[v] == level[u] + 1:
                    moved = push(v, min(pushed, cap[e]))
                    if moved > eps:
                        cap[e] -= moved
                        cap[e ^ 1] += moved
                        return moved
                pointer[u] += 1
            return 0.0

        while push(source, float("inf")) > eps:
            pass

    placed = np.array([carrier_caps[k] - cap[graph[source][k]] for k in range(carriers)])
    reached = [False] * (sink + 1)
    reached[source] = True
    stack = [source]
    while stack:
        u = stack.pop()
        for e in graph[u]:
            if cap[e] > eps and not reached[head[e]]:
                reached[head[e]] = True
                stack.append(head[e])
    return placed, np.array(reached[1:1 + carriers])


def joint_feasible_targets(
    support: np.ndarray, route_targets: np.ndarray, carrier_targets: np.ndarray,
    *, max_rounds: int = 50,
) -> np.ndarray:
    """Carrier targets the routes can hold together, shrinking only who must.

    A carrier alone may fit its routes while a *group* of carriers sharing
    them does not (World2Fly, Air Europa and Evelop on Madrid-Cancún in July
    2026).  Max flow finds the group whose demand its routes cannot absorb;
    that group is scaled down proportionally, and the check repeats until
    every carrier can be placed.  The one-carrier capacity cap is the special
    case of a group of one.
    """

    targets = carrier_targets.astype(float).copy()
    for _ in range(max_rounds):
        placed, deficient = _max_flow(support, route_targets, targets)
        shortfall = targets - placed
        if shortfall.sum() <= 1e-6 * max(1.0, float(targets.sum())):
            return targets
        group = deficient & (targets > 0)
        demand = float(targets[group].sum())
        if demand <= 0:
            return np.minimum(targets, placed)
        targets[group] *= float(placed[group].sum()) / demand
    return np.minimum(targets, placed)


def fit_international(
    seed: pd.DataFrame,
    route_totals: pd.DataFrame,
    carrier_totals: pd.DataFrame,
    families: pd.DataFrame,
    *,
    tolerance: float = INTERNATIONAL_TOLERANCE,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Fit each month's international cube, keeping every compromise visible.

    Three departures from the domestic fit, each reported per month:

    - carriers the seed cannot separate are pooled into their reviewed family;
    - a carrier whose margin exceeds every passenger on the routes it is seen
      on is capped at that capacity, and the excess is reported, not spread;
    - passengers on covered routes that no covered carrier can carry go to an
      explicit ``SIN_ASIGNAR`` column instead of inflating every carrier.
    """

    from src.analytics.route_carrier import ESTIMATOR_VERSION, fit_ipf

    pooled_seed = _pool(seed, families)
    pooled_totals = _pool(carrier_totals, families)
    labels = dict(zip(families["fit_key"], families["fit_label"]))

    estimates: list[pd.DataFrame] = []
    diagnostics: list[dict[str, object]] = []
    for period_id in sorted(set(pooled_seed["period_id"])):
        period_seed = pooled_seed[pooled_seed["period_id"] == period_id]
        rows = route_totals[
            (route_totals["period_id"] == period_id)
            & route_totals["route_key"].isin(period_seed["route_key"])
            & (route_totals["passengers"] > 0)
        ]
        columns = pooled_totals[
            (pooled_totals["period_id"] == period_id)
            & pooled_totals["carrier_key"].isin(period_seed["carrier_key"])
            & (pooled_totals["passengers"] > 0)
        ]
        if rows.empty or columns.empty:
            diagnostics.append({"period_id": period_id, "reason": "no_overlap"})
            continue

        route_index = pd.Index(sorted(rows["route_key"].unique()), name="route_key")
        carrier_index = pd.Index(sorted(columns["carrier_key"].unique()), name="carrier_key")
        matrix = (
            period_seed.pivot_table(
                index="route_key", columns="carrier_key", values="weight",
                aggfunc="sum", fill_value=0.0,
            )
            .reindex(index=route_index, columns=carrier_index)
            .fillna(0.0)
            .to_numpy()
        )
        route_targets = rows.groupby("route_key")["passengers"].sum().reindex(route_index).to_numpy()
        published = (
            columns.groupby("carrier_key")["passengers"].sum().reindex(carrier_index).to_numpy()
        )
        # Carriers also carry passengers on routes the seed does not cover, so
        # their margin can exceed the covered routes' total.  That global
        # excess is removed proportionally first; only what is left after it is
        # a structural conflict between carriers and the routes they are seen on.
        rows_total = float(route_targets.sum())
        global_balance = min(1.0, rows_total / float(published.sum()))
        balanced = published * global_balance
        feasible = joint_feasible_targets(matrix, route_targets, balanced)
        is_capped = feasible < balanced * (1 - 1e-6)
        carrier_targets = np.where(is_capped, feasible * CAPACITY_CAP_SHARE, balanced)
        capped = pd.Series(balanced - carrier_targets, index=carrier_index)
        # The room a capped carrier leaves on its own routes can only be taken
        # by the unallocated column, so it is reserved there.  Any balancing
        # between the two margins falls on the uncapped carriers alone: scaling
        # a capped one would reopen the gap it was capped to close.
        reserve = float((feasible - carrier_targets)[is_capped].sum())
        unallocated = max(rows_total - float(carrier_targets.sum()), reserve)
        uncapped_total = float(carrier_targets[~is_capped].sum())
        balance = (
            (rows_total - unallocated - float(carrier_targets[is_capped].sum())) / uncapped_total
            if uncapped_total
            else 1.0
        )
        carrier_targets = np.where(is_capped, carrier_targets, carrier_targets * balance)

        full_seed = np.column_stack([matrix, matrix.sum(axis=1) * UNALLOCATED_SEED_SHARE])
        full_targets = np.append(carrier_targets, unallocated)
        result = fit_ipf(full_seed, route_targets, full_targets, tolerance=tolerance)

        keys = [*carrier_index, UNALLOCATED]
        tidy = (
            pd.DataFrame(result.matrix, index=route_index, columns=keys)
            .stack()
            .rename("passengers_estimated")
            .reset_index()
            .rename(columns={"level_1": "carrier_key"})
        )
        tidy = tidy[tidy["passengers_estimated"] > 0.5].copy()
        carriers_per_route = (matrix > 0).sum(axis=1)
        tidy["period_id"] = period_id
        tidy["is_single_operator_seed"] = tidy["route_key"].map(
            dict(zip(route_index, carriers_per_route == 1))
        )
        tidy["is_pooled_family"] = tidy["carrier_key"].isin(set(families["fit_key"]))
        tidy["carrier_label"] = tidy["carrier_key"].map(labels)
        tidy["is_exact"] = False
        tidy["estimator_version"] = f"{ESTIMATOR_VERSION}+international_families_v1"
        estimates.append(tidy)

        diagnostics.append(
            {
                "period_id": period_id,
                "routes": int(route_index.size),
                "carriers": int(carrier_index.size),
                "competitive_routes": int((carriers_per_route >= 2).sum()),
                "iterations": result.iterations,
                "converged": result.converged,
                "max_row_deviation": result.max_row_deviation,
                "max_col_deviation": result.max_col_deviation,
                "column_scale": result.column_scale,
                "global_balance": global_balance,
                "uncapped_balance": balance,
                "passengers_capped": float(capped.sum()),
                "capped_carriers": ", ".join(
                    f"{key} {value:,.0f}" for key, value in capped[capped > 0.5].sort_values(ascending=False).items()
                ),
                "passengers_unallocated": unallocated,
                "unallocated_share": unallocated / float(route_targets.sum()),
                "reason": "",
            }
        )

    columns = [
        "period_id", "route_key", "carrier_key", "carrier_label", "passengers_estimated",
        "is_exact", "is_single_operator_seed", "is_pooled_family", "estimator_version",
    ]
    estimate = pd.concat(estimates, ignore_index=True)[columns] if estimates else pd.DataFrame(columns=columns)
    return estimate, pd.DataFrame(diagnostics)


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

def capture_from_sweep(frames: list[pd.DataFrame]) -> pd.DataFrame:
    """Read the sweep's seed files into the capture contract.

    The sweep keeps an unreviewed operator under its published identity as
    ``IATA:XX`` or ``ICAO:XXX``; the code is recovered from that key so the
    crosswalk, not the adapter, decides which carrier it is.
    """

    frame = pd.concat(
        [part.assign(capture_pass=number) for number, part in enumerate(frames)],
        ignore_index=True,
    )
    if "through_flights" not in frame:
        frame["through_flights"] = 0.0
    frame["through_flights"] = frame["through_flights"].fillna(0.0)
    key = frame["operator_key"].astype(str)
    frame["operator_iata"] = key.str.extract(r"^IATA:(.+)$")[0].fillna("")
    frame["operator_icao"] = key.str.extract(r"^ICAO:(.+)$")[0].fillna("")
    return frame


def t100_substitute_capture(
    period_ids: tuple[str, ...],
    *,
    gold_dir: Path | None = None,
    measure: str = "departures_performed",
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

    if measure not in {"departures_performed", "passengers"}:
        raise ValueError(f"unsupported T-100 measure: {measure!r}")
    gold = gold_dir or PATHS.gold
    placeholders = ", ".join("?" for _ in period_ids)
    query = f"""
        SELECT f.period_id,
               r.origin_iata,
               r.dest_iata,
               f.carrier_key AS operator_key,
               SUM(f.{measure}) AS flights
        FROM read_parquet(?) f
        JOIN read_parquet(?) r USING (route_key)
        WHERE r.is_transborder_us
          AND f.period_id IN ({placeholders})
          AND f.{measure} > 0
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


def t100_backtest(estimate: pd.DataFrame, observed: pd.DataFrame) -> pd.DataFrame:
    """Compare fitted cells with the cells T-100 observes, one row per cell.

    ``observed`` carries ``period_id, route_key, carrier_key,
    passengers_observed``.  A cell T-100 observes and the fit left empty is
    kept with a zero estimate: missing supply is an error, not an exclusion.
    """

    fitted = estimate[~estimate["carrier_key"].isin({"AEROMEXICO_GROUP", UNALLOCATED})]
    keys = ["period_id", "route_key", "carrier_key"]
    joined = observed.merge(
        fitted[[*keys, "passengers_estimated"]], on=keys, how="left"
    )
    joined["passengers_estimated"] = joined["passengers_estimated"].fillna(0.0)
    joined["error"] = joined["passengers_estimated"] - joined["passengers_observed"]
    return joined


def summarise_backtest(cells: pd.DataFrame) -> dict[str, float]:
    """Weighted error measures; cells are weighted by what T-100 observed."""

    observed = float(cells["passengers_observed"].sum())
    if observed <= 0:
        return {"cells": 0, "observed": 0.0}
    absolute = cells["error"].abs()
    relative = absolute / cells["passengers_observed"]
    return {
        "cells": int(len(cells)),
        "observed": observed,
        "estimated": float(cells["passengers_estimated"].sum()),
        "sum_ratio": float(cells["passengers_estimated"].sum()) / observed,
        "weighted_abs_error": float(absolute.sum()) / observed,
        "median_abs_pct_error": float(relative.median()),
        "cells_missing_from_fit": int((cells["passengers_estimated"] == 0).sum()),
    }


def codeshare_sensitivity(
    seed: pd.DataFrame,
    route_totals: pd.DataFrame,
    carrier_totals: pd.DataFrame,
    families: pd.DataFrame,
) -> pd.DataFrame:
    """Refit without the flights whose operating status the provider guessed.

    The gap between the two fits, route by route, is how much of the answer
    rests on ``codeshareStatus = Unknown`` rather than on a declared operator.
    """

    base, _ = fit_international(seed, route_totals, carrier_totals, families)
    declared = seed.assign(weight=seed["weight"] - seed["codeshare_unknown"])
    declared = declared[declared["weight"] > 0]
    alternative, _ = fit_international(declared, route_totals, carrier_totals, families)
    keys = ["period_id", "route_key", "carrier_key"]
    compared = base.merge(
        alternative[[*keys, "passengers_estimated"]],
        on=keys, how="outer", suffixes=("", "_declared_only"),
    ).fillna({"passengers_estimated": 0.0, "passengers_estimated_declared_only": 0.0})
    return compared


def run_capture(
    capture: pd.DataFrame,
    *,
    routes: pd.DataFrame,
    carrier_margin: pd.DataFrame,
    cities: pd.DataFrame,
    carriers: pd.DataFrame,
    observed_capture: pd.DataFrame | None,
    families: pd.DataFrame,
) -> dict[str, object]:
    """Gate, fit, group and diagnose one real capture; publish nothing.

    The fit runs only for months the gate does not refuse.  T-100 enters after
    the fit, as the observation the estimate is measured against and as the
    source that will be displayed where it exists -- never as seed or margin.
    """

    seed, rejected = build_international_seed(capture, cities, carriers)
    route_totals, carrier_totals = build_international_margins(routes, carrier_margin, carriers)
    flights = afac_route_flights(routes)

    reports = {
        period_id: assess_international_seed(
            capture, seed, rejected, route_totals, carrier_totals, flights, carriers,
            period_id=period_id,
        )
        for period_id in sorted(capture["period_id"].unique())
    }
    usable = [period_id for period_id, report in reports.items() if report.usable]
    fit_seed = seed[seed["period_id"].isin(usable)]
    estimate, diagnostics = fit_international(fit_seed, route_totals, carrier_totals, families)

    observed = pd.DataFrame(
        columns=["period_id", "route_key", "carrier_key", "passengers_observed"]
    )
    if observed_capture is not None and not observed_capture.empty:
        observed_seed, _ = build_international_seed(observed_capture, cities, carriers)
        observed = observed_seed.rename(columns={"weight": "passengers_observed"})[
            ["period_id", "route_key", "carrier_key", "passengers_observed"]
        ]
        observed = observed[observed["period_id"].isin(usable)]
        # Compared at the fit's own grain: a pooled family against its pool.
        observed = (
            _pool(observed, families)
            .groupby(["period_id", "route_key", "carrier_key"], as_index=False)["passengers_observed"]
            .sum()
        )

    grouped = observed_cells_to_exclude(group_aeromexico(estimate), observed)
    backtest = t100_backtest(estimate, observed) if not observed.empty else pd.DataFrame()
    sensitivity = (
        codeshare_sensitivity(fit_seed, route_totals, carrier_totals, families)
        if not fit_seed.empty
        else pd.DataFrame()
    )
    return {
        "seed": seed,
        "rejected": rejected,
        "reports": reports,
        "estimate": grouped,
        "diagnostics": diagnostics,
        "backtest": backtest,
        "sensitivity": sensitivity,
    }


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
    parser.add_argument(
        "--capture", nargs="+", type=Path, default=None,
        help="seed parquet files written by the international sweep; one month's "
        "passes together (e.g. the nucleo and resto files)",
    )
    parser.add_argument(
        "--out", type=Path, default=None,
        help="directory for the local, unpublished outputs of --capture",
    )
    args = parser.parse_args(argv)
    periods = tuple(period.strip() for period in args.periods.split(",") if period.strip())

    reference = PATHS.data / "reference"
    routes = pd.read_csv(reference / ROUTE_MARGIN_FILE)
    carrier_margin = pd.read_csv(reference / CARRIER_MARGIN_FILE)
    cities = pd.read_csv(reference / CITY_CROSSWALK_FILE)
    carriers = pd.read_csv(reference / CARRIER_CROSSWALK_FILE).fillna("")

    if args.capture:
        return _main_capture(args, routes, carrier_margin, cities, carriers)

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


def _main_capture(args, routes, carrier_margin, cities, carriers) -> int:  # pragma: no cover
    from src.config import PATHS

    capture = capture_from_sweep([pd.read_parquet(path) for path in args.capture])
    periods = tuple(sorted(capture["period_id"].unique()))
    try:
        observed_capture = t100_substitute_capture(periods, measure="passengers")
    except Exception as error:  # T-100 Gold may be absent in a cloud clone
        print(f"T-100 no disponible para el contraste: {error}")
        observed_capture = None

    result = run_capture(
        capture, routes=routes, carrier_margin=carrier_margin, cities=cities,
        carriers=carriers, observed_capture=observed_capture,
        families=load_carrier_families(),
    )
    seed, rejected = result["seed"], result["rejected"]
    print("CAPTURA REAL de AeroDataBox. Nada se publica ni se activa.\n")
    print(
        f"capture: {len(capture):,} filas  ->  seed: {len(seed):,} filas, "
        f"{len(rejected):,} descartadas"
    )
    if not rejected.empty:
        weight = rejected.groupby("rejection_reason")["flights"].sum().round(1)
        print("  vuelos descartados por motivo: " + str(weight.to_dict()))
        unmapped = rejected[rejected["rejection_reason"] == "operador sin carrier_key revisado"]
        if not unmapped.empty:
            top = unmapped.groupby("operator_key")["flights"].sum().sort_values(ascending=False)
            print("  operadores sin revisar: " + str(top.head(15).round(1).to_dict()))
    print()
    for report in result["reports"].values():
        print(format_report(report))
        print()

    diagnostics = result["diagnostics"]
    if not diagnostics.empty:
        print("IPF:")
        print(diagnostics.to_string(index=False))
        print()

    estimate = result["estimate"]
    group = estimate[estimate["carrier_key"] == "AEROMEXICO_GROUP"]
    if not group.empty:
        print(
            f"Grupo Aeromexico: {group['passengers_estimated'].sum():,.0f} pasajeros "
            f"estimados en {group['route_key'].nunique()} rutas"
        )
        shown = estimate[estimate["carrier_key"] != "AEROMEXICO_GROUP"]
        print(
            "  celdas por fuente a mostrar: "
            + str(shown["display_source"].value_counts().to_dict())
        )
        print()

    backtest = result["backtest"]
    if not backtest.empty:
        print("Contraste con T-100 (celdas Mexico-EE. UU., fuera del ajuste):")
        for key, value in summarise_backtest(backtest).items():
            print(f"  {key:24s} {value:,.4f}" if isinstance(value, float) else f"  {key:24s} {value:,}")
        own = backtest[backtest["carrier_key"].isin({"AEROMEXICO", "AEROMEXICO_CONNECT"})]
        if not own.empty:
            print("  solo Aerovias + Connect:")
            for key, value in summarise_backtest(own).items():
                print(f"    {key:22s} {value:,.4f}" if isinstance(value, float) else f"    {key:22s} {value:,}")
        print()

    sensitivity = result["sensitivity"]
    if not sensitivity.empty:
        own = sensitivity[sensitivity["carrier_key"].isin({"AEROMEXICO", "AEROMEXICO_CONNECT"})]
        base = float(own["passengers_estimated"].sum())
        alt = float(own["passengers_estimated_declared_only"].sum())
        routes_changed = (
            own.groupby("route_key")[["passengers_estimated", "passengers_estimated_declared_only"]]
            .sum()
        )
        shift = (
            (routes_changed.iloc[:, 1] - routes_changed.iloc[:, 0]).abs()
            / routes_changed.iloc[:, 0].where(routes_changed.iloc[:, 0] > 0)
        )
        print("Sensibilidad (sin registros con codeshareStatus=Unknown):")
        print(f"  Grupo Aeromexico total   {base:,.0f} -> {alt:,.0f} ({alt / base - 1:+.2%})")
        print(f"  cambio mediano por ruta  {shift.median():.2%}")
        print(f"  rutas con cambio >10%    {int((shift > 0.10).sum())} de {int(shift.notna().sum())}")
        print()

    out = args.out or PATHS.silver / "international_route_carrier"
    out.mkdir(parents=True, exist_ok=True)
    stem = "_".join(periods)
    estimate.to_parquet(out / f"estimate_{stem}.parquet", index=False)
    diagnostics.to_parquet(out / f"diagnostics_{stem}.parquet", index=False)
    rejected.to_parquet(out / f"rejected_{stem}.parquet", index=False)
    if not backtest.empty:
        backtest.to_parquet(out / f"t100_backtest_{stem}.parquet", index=False)
    if not sensitivity.empty:
        sensitivity.to_parquet(out / f"sensitivity_{stem}.parquet", index=False)
    seed.to_parquet(out / f"seed_{stem}.parquet", index=False)
    capture.to_parquet(out / f"capture_{stem}.parquet", index=False)
    summary = {
        "acceptance": {
            period_id: {
                "verdict": report.verdict,
                "acceptance_version": report.acceptance_version,
                "route_passenger_coverage": report.route_passenger_coverage,
                "carrier_passenger_coverage": report.carrier_passenger_coverage,
                "column_scale": report.column_scale,
                "unknown_codeshare_share": report.unknown_codeshare_share,
                "status_incomplete_share": report.status_incomplete_share,
                "seed_routes": report.seed_routes,
                "seed_carriers": report.seed_carriers,
                "findings": [
                    {"code": f.code, "severity": f.severity, "detail": f.detail, "value": f.value}
                    for f in report.findings
                ],
            }
            for period_id, report in result["reports"].items()
        },
        "fit": diagnostics.to_dict(orient="records"),
        "t100_backtest": summarise_backtest(backtest) if not backtest.empty else None,
        "t100_backtest_aeromexico": (
            summarise_backtest(
                backtest[backtest["carrier_key"].isin({"AEROMEXICO", "AEROMEXICO_CONNECT"})]
            )
            if not backtest.empty
            else None
        ),
    }
    (out / f"summary_{stem}.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False, default=float)
    )
    print(f"Salidas locales, sin publicar: {out}")
    return 0


if __name__ == "__main__":  # pragma: no cover - manual entry point
    raise SystemExit(main())
