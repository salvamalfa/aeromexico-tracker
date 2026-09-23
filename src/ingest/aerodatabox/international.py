"""Observe the international legs the domestic sweep was already throwing away.

The domestic adapter asks AeroDataBox for departures at every Mexican airport
and then discards every flight whose arrival airport is not Mexican, counting
them only as ``foreign_destinations``.  Those discarded rows are the whole
international network: the same call that produced the domestic seed also saw
Madrid, Tokyo, Toronto and Bogotá and threw them out.  This module keeps them.

Three things differ from :mod:`src.ingest.aerodatabox.flights`, each forced by
the data rather than chosen:

- **Direction.**  A domestic leg departs a Mexican airport, so sweeping every
  Mexican airport for departures sees each leg exactly once.  An international
  market has one leg that departs Mexico and one that arrives, and only the
  first departs an airport in the sweep.  ``direction=Both`` costs the same two
  units as ``direction=Departure`` and is the only way to observe the inbound
  leg without paying for a second sweep at foreign airports.  Domestic legs are
  then seen twice, at both ends, and are dropped here rather than deduplicated:
  this module does not produce a domestic seed.

- **Carrier universe.**  The domestic margin contains Mexican scheduled
  carriers only, so the domestic adapter drops an operator it cannot place in
  the crosswalk.  The international margin contains foreign carriers too --
  Iberia and Air France are as real on MEX–MAD and MEX–CDG as Aeroméxico is --
  so dropping an unmapped operator here would delete a competitor from the
  route and corrupt exactly the within-route proportions the seed exists to
  carry.  Operators are therefore kept under their published identity, and
  mapping one to a project ``carrier_key`` is an annotation, not a filter.

- **What counts as Mexican.**  The domestic adapter reads its airport universe
  from the AFAC city crosswalk, which is a list of the 58 airports AFAC's
  domestic margin is keyed by.  An arrival from a Mexican airport outside that
  list would be misread here as an international leg, so nationality is decided
  by ``dim_airport.country`` and the crosswalk is only a fallback.

The module produces flight counts, never passengers: AeroDataBox publishes no
passenger figure of any kind.  A count becomes a passenger figure only through
the AFAC margins and the fit documented in
``docs/estimacion-pasajeros-ruta-aerolinea.md``, which is the canonical method
and states the conditions this seed has to meet before it is fitted at all.

Raw responses go to transient Bronze under a distinct ``_both`` file name so a
two-direction payload can never be read back as the one-direction list the
domestic adapter caches.  They are provider content, expire with the plan's
retention and never enter Git.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
import json
from pathlib import Path
import time
import unicodedata

import httpx
import pandas as pd

from src.analytics.route_carrier import load_city_crosswalk
from src.config import PATHS
from src.ingest.aerodatabox.flights import (
    CARRIER_BY_IATA,
    CARRIER_BY_ICAO,
    CARRIER_BY_NAME,
    CONNECT_FLEET,
    MAX_WINDOW_HOURS,
    MIN_SECONDS_BETWEEN_CALLS,
    NON_SCHEDULED_ICAO,
    PullStats,
    UNITS_PER_CALL,
    _cache_is_fresh,
    api_credentials,
    purge_expired_cache,
)


WINDOWS_PER_DAY = 24 // MAX_WINDOW_HOURS
# An Aeroméxico flight whose aircraft model is missing cannot be split between
# Aerovías de México and Aeroméxico Connect by fleet.  The domestic adapter
# drops it, because leaving it in would silently credit Aerovías with a Connect
# leg.  Dropping it here would instead delete a real international flight from
# a route, so it is kept under a key that says exactly what is unknown.
UNSPLIT_AEROMEXICO = "AEROMEXICO_UNSPLIT"

FLIGHT_COLUMNS = (
    "period_id",
    "origin_iata",
    "dest_iata",
    "operator_key",
    "operator_iata",
    "operator_icao",
    "operator_name",
    "aircraft_model",
    # The Mexican airport a through flight stops at, or empty for a direct
    # leg.  AFAC counts a flight MEX-MTY-NRT on MEXICO-TOKYO as well as on
    # MONTERREY-TOKYO, so the seed has to carry both.
    "via_iata",
    "flights",
    # Two diagnostics the acceptance gate needs and that cannot be recovered
    # later: once the provider's raw responses expire, nothing else records how
    # much of the seed rests on a guess.
    "codeshare_unknown",
    "status_incomplete",
)

# The provider filters code-shares when asked, but for airports with no
# code-share information it applies a heuristic and warns that "false results
# are possible".  A record that arrives ``Unknown`` therefore survived a guess,
# not a declaration, and its weight belongs in the seed so the gate can price
# it.  The probe of 2026-09-10 measured 17.6% of records in this state.
UNKNOWN_CODESHARE = "Unknown"
# A status that does not say the flight actually operated.  Scheduled is not
# flown, and AFAC counts flights performed.
COMPLETED_STATUSES = frozenset({"departed", "arrived", "landed", "enroute"})


class NoAirportUniverseError(RuntimeError):
    """Neither the airport dimension nor the AFAC crosswalk could be read."""


@dataclass
class InternationalPullStats(PullStats):
    """Everything the international sweep saw and everything it refused.

    The domestic counters are inherited; these record the decisions that only
    exist once both directions are requested and foreign operators are kept.
    """

    domestic_legs_dropped: int = 0
    foreign_to_foreign_dropped: int = 0
    unknown_endpoint_country: Counter = field(default_factory=Counter)
    unmapped_operators: Counter = field(default_factory=Counter)
    aeromexico_unsplit: int = 0
    arrivals_seen: int = 0
    departures_seen: int = 0
    through_legs: int = 0
    through_already_direct: int = 0


def _strip_accents(text: str) -> str:
    return "".join(
        char
        for char in unicodedata.normalize("NFKD", text)
        if not unicodedata.combining(char)
    )


def mexican_airports(reference_dir: Path | None = None) -> frozenset[str]:
    """Every Mexican airport code, so a foreign endpoint is decided, not guessed.

    ``dim_airport`` is the authority because it covers airports outside AFAC's
    58-airport domestic margin; a leg arriving from one of those would read as
    international against the crosswalk alone.  The crosswalk remains the
    fallback for an environment without Gold, where it is still correct for
    every airport it does list.
    """

    airports: set[str] = set()
    dimension = PATHS.gold / "dim_airport.parquet"
    if dimension.exists():
        frame = pd.read_parquet(dimension, columns=["airport_iata", "country"])
        airports.update(
            frame.loc[frame["country"] == "MX", "airport_iata"].dropna().astype(str)
        )
    try:
        airports.update(load_city_crosswalk(reference_dir))
    except (FileNotFoundError, OSError):
        if not airports:
            raise NoAirportUniverseError(
                "Neither data/gold/dim_airport.parquet nor the AFAC city "
                "crosswalk is available; the Mexican airport universe is unknown"
            ) from None
    return frozenset(airports)


def _cache_path(cache_dir: Path, iata: str, start: str) -> Path:
    """Both-direction payloads are named apart from the domestic list cache."""

    return cache_dir / f"{iata}_{start.replace(':', '')}_both.json"


def fetch_window_both(
    iata: str,
    start: str,
    end: str,
    *,
    api_key: str | None = None,
    direct: bool | None = None,
    cache_dir: Path,
    stats: PullStats,
    client: httpx.Client | None = None,
) -> dict[str, list[dict]]:
    """One airport, one window of at most 12 hours, arrivals and departures.

    The request duplicates the domestic adapter's rather than sharing it,
    because the two cache different shapes: this one has to keep both arrays,
    and a dict written under the domestic file name would be read back as a
    list of departures on the next resume.
    """

    path = _cache_path(cache_dir, iata, start)
    if _cache_is_fresh(path):
        stats.cached_calls += 1
        return json.loads(path.read_text())
    if path.exists():
        path.unlink()
        stats.expired_cache_files += 1

    base_url, headers = api_credentials(api_key, direct=direct)
    params = {
        # The only parameter that differs from the domestic pull, and the whole
        # reason this module exists: an inbound leg from Madrid arrives at MEX
        # and departs nowhere in the sweep.
        "direction": "Both",
        "withLeg": "true",
        "withCancelled": "false",
        "withCodeshared": "false",
        "withCargo": "false",
        "withPrivate": "false",
        "withLocation": "false",
    }
    owns_client = client is None
    client = client or httpx.Client(timeout=90.0)
    try:
        response = client.get(
            f"{base_url}/{iata}/{start}/{end}", params=params, headers=headers
        )
    finally:
        if owns_client:
            client.close()

    stats.calls += 1
    stats.units_spent += UNITS_PER_CALL
    if response.status_code == 204:
        payload: dict[str, list[dict]] = {"departures": [], "arrivals": []}
    else:
        response.raise_for_status()
        body = response.json() or {}
        payload = {
            "departures": body.get("departures") or [],
            "arrivals": body.get("arrivals") or [],
        }

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload))
    if not payload["departures"] and not payload["arrivals"]:
        stats.empty_windows.append(f"{iata} {start}")
    return payload


def _operator(flight: dict, stats: InternationalPullStats) -> tuple[str, str, str, str] | None:
    """Resolve the operating carrier's key and its published identity.

    Unlike the domestic adapter this never returns ``None`` for an operator it
    cannot place in the project's crosswalk: a foreign carrier is a real
    competitor on the route and deleting it would move every other carrier's
    share on that route.  It returns ``None`` only when the record carries no
    usable operator identity at all, or when the operator is a known
    non-scheduled one.
    """

    airline = flight.get("airline") or {}
    iata = (airline.get("iata") or "").strip().upper()
    icao = (airline.get("icao") or "").strip().upper()
    name = (airline.get("name") or "").strip()
    if icao in NON_SCHEDULED_ICAO or iata in NON_SCHEDULED_ICAO:
        stats.non_scheduled_dropped += 1
        return None

    key = (
        CARRIER_BY_IATA.get(iata)
        or CARRIER_BY_ICAO.get(icao)
        # The live feed has been observed putting an ICAO code in the IATA
        # field; resolve only codes already in the reviewed crosswalk.
        or CARRIER_BY_ICAO.get(iata)
        or CARRIER_BY_IATA.get(icao)
        or CARRIER_BY_NAME.get(_strip_accents(name).lower())
    )
    if key == "AEROMEXICO":
        model = (flight.get("aircraft") or {}).get("model")
        if not model:
            stats.aeromexico_unsplit += 1
            key = UNSPLIT_AEROMEXICO
        elif CONNECT_FLEET.search(model):
            key = "AEROMEXICO_CONNECT"
    if key is None:
        # Kept, not dropped: the identity is recorded as published so a human
        # crosswalk can map it to the AFAC carrier margin later.
        if iata:
            key = f"IATA:{iata}"
        elif icao:
            key = f"ICAO:{icao}"
        elif name:
            key = f"NAME:{_strip_accents(name).upper()}"
        else:
            stats.unmapped_operators["?"] += 1
            return None
        stats.unmapped_operators[key] += 1
    return key, iata, icao, name


def _endpoint(movement: dict | None) -> str | None:
    airport = (movement or {}).get("airport") or {}
    code = airport.get("iata")
    return str(code).strip().upper() if code else None


def _keep(flight: dict, stats: InternationalPullStats) -> bool:
    """Apply the filters the request already asked for, defensively."""

    if str(flight.get("status") or "").strip().lower() in {"canceled", "cancelled"}:
        stats.cancelled_dropped += 1
        return False
    if flight.get("isCargo"):
        stats.cargo_dropped += 1
        return False
    if flight.get("codeshareStatus") == "IsCodeshared":
        stats.codeshares_dropped += 1
        return False
    return True


# A domestic leg and an international leg with one flight number form one
# through flight only if the aircraft turns around within this window.
THROUGH_CONNECTION_HOURS = 8


def _utc(movement: dict | None) -> datetime | None:
    stamp = (((movement or {}).get("scheduledTime")) or {}).get("utc")
    if not stamp:
        return None
    try:
        return datetime.strptime(stamp, "%Y-%m-%d %H:%MZ")
    except ValueError:
        return None


def _number(flight: dict) -> str:
    return str(flight.get("number") or "").replace(" ", "").upper()


def board_index(cache_dir: Path, period_id: str) -> dict[str, dict[str, dict[str, set[str]]]]:
    """What every cached board of the month says each flight number connects to.

    ``index[airport]["out"][number]`` is the set of destinations the airport's
    departure board lists for that number, ``["in"]`` the origins its arrival
    board lists.  The provider sometimes lists a through flight's final
    endpoint rather than its next stop, and when it does the flight is already
    counted directly and must not be rebuilt a second time.
    """

    year, month = int(period_id[:4]), int(period_id[5:])
    prefix = f"{year:04d}-{month:02d}-"
    index: dict[str, dict[str, dict[str, set[str]]]] = {}
    for path in sorted(cache_dir.glob("*_both.json")):
        airport, start, _ = path.stem.split("_", 2)
        if not start.startswith(prefix):
            continue
        payload = json.loads(path.read_text())
        entry = index.setdefault(airport, {"out": {}, "in": {}})
        for flight in payload.get("departures") or []:
            other = _endpoint(flight.get("arrival"))
            if other and _number(flight):
                entry["out"].setdefault(_number(flight), set()).add(other)
        for flight in payload.get("arrivals") or []:
            other = _endpoint(flight.get("departure"))
            if other and _number(flight):
                entry["in"].setdefault(_number(flight), set()).add(other)
    return index


def _through_rows(
    raw: dict,
    period_id: str,
    *,
    stats: InternationalPullStats,
    mexican: frozenset[str],
    day_weights: dict[date, float] | None,
    boards: dict[str, dict[str, dict[str, set[str]]]] | None = None,
) -> list[tuple]:
    """International origin-destination pairs flown through a Mexican stop.

    Aeroméxico's Tokyo flight leaves Mexico City as a domestic leg to
    Monterrey and continues to Narita under the same number.  Mexico City's
    board shows only MEX-MTY, which is dropped as domestic, yet AFAC counts
    the flight on MEXICO-TOKYO.  Both legs are visible at the stop itself --
    the domestic arrival and the international departure, or the reverse --
    so the pair is rebuilt there, from the stop's own records, and weighted
    like the international leg it continues.
    """

    by_airport: dict[str, list[tuple[str, dict, float]]] = {}
    for key, payload in raw.items():
        swept, day = key if isinstance(key, tuple) else (key, None)
        weight = 1.0 if day_weights is None else float(day_weights.get(day, 1.0))
        bucket = by_airport.setdefault(str(swept).strip().upper(), [])
        bucket.extend(("departure", f, weight) for f in payload.get("departures") or [])
        bucket.extend(("arrival", f, weight) for f in payload.get("arrivals") or [])

    window = timedelta(hours=THROUGH_CONNECTION_HOURS)
    rows: list[tuple] = []
    for stop, records in by_airport.items():
        if stop not in mexican:
            continue
        domestic_in: dict[str, list[tuple[datetime, str]]] = {}
        domestic_out: dict[str, list[tuple[datetime, str]]] = {}
        for arrow, flight, _ in records:
            if arrow == "arrival":
                other, when = _endpoint(flight.get("departure")), _utc(flight.get("arrival"))
                bucket = domestic_in
            else:
                other, when = _endpoint(flight.get("arrival")), _utc(flight.get("departure"))
                bucket = domestic_out
            if other in mexican and other != stop and when is not None and _number(flight):
                bucket.setdefault(_number(flight), []).append((when, other))

        for arrow, flight, weight in records:
            if arrow == "departure":
                foreign, when = _endpoint(flight.get("arrival")), _utc(flight.get("departure"))
                candidates = domestic_in.get(_number(flight), [])
                matches = [a for t, a in candidates if when and timedelta(0) < when - t <= window]
            else:
                foreign, when = _endpoint(flight.get("departure")), _utc(flight.get("arrival"))
                candidates = domestic_out.get(_number(flight), [])
                matches = [a for t, a in candidates if when and timedelta(0) < t - when <= window]
            if foreign is None or foreign in mexican or not matches:
                continue
            if not _keep(flight, stats):
                continue
            operator = _operator(flight, stats)
            if operator is None:
                continue
            operator_key, iata, icao, name = operator
            mexican_end = matches[0]
            side = "out" if arrow == "departure" else "in"
            listed = ((boards or {}).get(mexican_end, {}).get(side, {})).get(_number(flight), set())
            if foreign in listed:
                # The first airport's own board already shows this flight to
                # its final endpoint, so it was counted there directly.
                stats.through_already_direct += 1
                continue
            origin, dest = (mexican_end, foreign) if arrow == "departure" else (foreign, mexican_end)
            status = str(flight.get("status") or "").strip().lower()
            stats.through_legs += 1
            rows.append(
                (
                    period_id,
                    origin,
                    dest,
                    operator_key,
                    iata,
                    icao,
                    name,
                    str((flight.get("aircraft") or {}).get("model") or ""),
                    stop,
                    weight,
                    weight if flight.get("codeshareStatus") == UNKNOWN_CODESHARE else 0.0,
                    weight if status not in COMPLETED_STATUSES else 0.0,
                )
            )
    return rows


def normalise(
    raw: dict,
    period_id: str,
    *,
    stats: InternationalPullStats,
    mexican: frozenset[str],
    day_weights: dict[date, float] | None = None,
    boards: dict[str, dict[str, dict[str, set[str]]]] | None = None,
) -> pd.DataFrame:
    """Turn cached both-direction payloads into international route counts.

    ``raw`` maps an airport, or an ``(airport, day)`` pair, to the payload of
    :func:`fetch_window_both`.  Each leg is recorded once, in its published
    direction: a departure from a swept Mexican airport to a foreign one, or an
    arrival at a swept Mexican airport from a foreign one.  A leg between two
    Mexican airports is seen at both ends and belongs to the domestic seed, so
    it is dropped here rather than deduplicated.

    ``day_weights`` works exactly as in the domestic adapter: a sampled day
    counts as its weekday's frequency within the month, so a sampled week
    scales to the month instead of merely resembling it.  International
    frequency is lumpier than domestic -- a route flown three times a week is
    common -- so a weighted sample is a coarser instrument here and a whole
    month is worth its units where the window still allows one.
    """

    rows: list[tuple] = []
    for key, payload in raw.items():
        swept, day = key if isinstance(key, tuple) else (key, None)
        swept = str(swept).strip().upper()
        weight = 1.0 if day_weights is None else float(day_weights.get(day, 1.0))
        for arrow, flights in (
            ("departure", payload.get("departures") or []),
            ("arrival", payload.get("arrivals") or []),
        ):
            for flight in flights:
                if arrow == "departure":
                    stats.departures_seen += 1
                    other = _endpoint(flight.get("arrival"))
                    origin, dest = swept, other
                else:
                    stats.arrivals_seen += 1
                    other = _endpoint(flight.get("departure"))
                    origin, dest = other, swept
                if other is None:
                    stats.missing_arrival += 1
                    continue
                if other in mexican:
                    stats.domestic_legs_dropped += 1
                    continue
                if swept not in mexican:
                    # Only reachable if the caller sweeps a non-Mexican airport.
                    stats.foreign_to_foreign_dropped += 1
                    continue
                if not _keep(flight, stats):
                    continue
                operator = _operator(flight, stats)
                if operator is None:
                    continue
                operator_key, iata, icao, name = operator
                model = (flight.get("aircraft") or {}).get("model") or ""
                unknown_codeshare = (
                    weight if flight.get("codeshareStatus") == UNKNOWN_CODESHARE else 0.0
                )
                status = str(flight.get("status") or "").strip().lower()
                incomplete = weight if status not in COMPLETED_STATUSES else 0.0
                rows.append(
                    (
                        period_id,
                        origin,
                        dest,
                        operator_key,
                        iata,
                        icao,
                        name,
                        str(model),
                        "",
                        weight,
                        unknown_codeshare,
                        incomplete,
                    )
                )

    rows.extend(
        _through_rows(
            raw, period_id, stats=stats, mexican=mexican, day_weights=day_weights,
            boards=boards,
        )
    )
    frame = pd.DataFrame(rows, columns=list(FLIGHT_COLUMNS))
    if frame.empty:
        return frame
    measures = ["flights", "codeshare_unknown", "status_incomplete"]
    group = [column for column in FLIGHT_COLUMNS if column not in measures]
    return frame.groupby(group, as_index=False)[measures].sum()


def plan_units(airports: int, days: int) -> int:
    """API units a sweep will cost, so the operator sees it before spending."""

    return airports * days * WINDOWS_PER_DAY * UNITS_PER_CALL


def pull_days(
    airports: list[str],
    days: list[date],
    *,
    period_id: str,
    cache_dir: Path,
    api_key: str | None = None,
    direct: bool | None = None,
    unit_budget: int | None = None,
    reference_dir: Path | None = None,
    day_weights: dict[date, float] | None = None,
    mexican: frozenset[str] | None = None,
    offline: bool = False,
) -> tuple[pd.DataFrame, InternationalPullStats]:
    """Sweep every airport across whole days, in half-day windows, both ways.

    ``offline`` rebuilds from the cache and refuses to buy a single window.

    ``unit_budget`` is a hard stop: the sweep returns what it already has
    rather than spending past it.  A cached window is free, so the budget is
    only consulted before a window that would actually be bought.
    """

    base_url, _ = api_credentials(api_key, direct=direct)  # falla temprano si no hay llave
    del base_url

    universe = mexican if mexican is not None else mexican_airports(reference_dir)
    stats = InternationalPullStats()
    stats.expired_cache_files = purge_expired_cache(cache_dir)
    raw: dict[tuple[str, date], dict] = {}
    last_call = 0.0
    with httpx.Client(timeout=90.0) as client:
        for day in days:
            halves = [
                (f"{day}T00:00", f"{day}T12:00"),
                (f"{day}T12:00", f"{day + timedelta(days=1)}T00:00"),
            ]
            for start, end in halves:
                for iata in airports:
                    cached = _cache_path(cache_dir, iata, start).exists()
                    if offline and not cached:
                        raise RuntimeError(
                            f"--offline: la ventana {iata} {start} no esta en cache; "
                            "no se compra nada"
                        )
                    if (
                        unit_budget is not None
                        and stats.units_spent + UNITS_PER_CALL > unit_budget
                        and not cached
                    ):
                        return normalise(
                            raw, period_id, stats=stats, mexican=universe,
                            day_weights=day_weights,
                        ), stats
                    wait = MIN_SECONDS_BETWEEN_CALLS - (time.monotonic() - last_call)
                    if wait > 0 and not cached:
                        time.sleep(wait)
                    payload = fetch_window_both(
                        iata, start, end, api_key=api_key, direct=direct,
                        cache_dir=cache_dir, stats=stats, client=client,
                    )
                    last_call = time.monotonic()
                    merged = raw.setdefault((iata, day), {"departures": [], "arrivals": []})
                    merged["departures"].extend(payload.get("departures") or [])
                    merged["arrivals"].extend(payload.get("arrivals") or [])

    return normalise(
        raw, period_id, stats=stats, mexican=universe, day_weights=day_weights,
        boards=board_index(cache_dir, period_id),
    ), stats


def routes_by_operator(flights: pd.DataFrame) -> pd.DataFrame:
    """Collapse the aircraft-model grain away, keeping route by operator."""

    if flights.empty:
        return flights
    group = ["period_id", "origin_iata", "dest_iata", "operator_key"]
    measures = ["flights", "codeshare_unknown", "status_incomplete", "through_flights"]
    through = flights["via_iata"].fillna("").ne("") if "via_iata" in flights else False
    flights = flights.assign(through_flights=flights["flights"].where(through, 0.0))
    return flights.groupby(group, as_index=False)[measures].sum()


def market_key(origin: str, destination: str) -> str:
    """The bidirectional market the dashboard shows, from a directional leg."""

    return "<>".join(sorted((origin, destination)))


def summarise(flights: pd.DataFrame, stats: InternationalPullStats) -> dict:
    """An aggregate the probe can print without republishing provider content.

    Counts of routes, operators and flights are a derived summary; the flight
    records behind them are the provider's and stay in transient Bronze.
    """

    summary: dict[str, object] = {
        "calls": stats.calls,
        "units_spent": stats.units_spent,
        "cached_calls": stats.cached_calls,
        "departures_seen": stats.departures_seen,
        "arrivals_seen": stats.arrivals_seen,
        "domestic_legs_dropped": stats.domestic_legs_dropped,
        "codeshares_dropped": stats.codeshares_dropped,
        "cancelled_dropped": stats.cancelled_dropped,
        "cargo_dropped": stats.cargo_dropped,
        "missing_endpoint": stats.missing_arrival,
        "aeromexico_unsplit": stats.aeromexico_unsplit,
        "empty_windows": list(stats.empty_windows),
        "international_legs": 0,
        "markets": 0,
        "operators": 0,
        "aeromexico_markets": [],
        "top_operators": [],
    }
    if flights.empty:
        return summary

    summary["international_legs"] = float(flights["flights"].sum())
    markets = flights.apply(
        lambda row: market_key(row["origin_iata"], row["dest_iata"]), axis=1
    )
    summary["markets"] = int(markets.nunique())
    summary["operators"] = int(flights["operator_key"].nunique())
    summary["top_operators"] = [
        {"operator_key": key, "flights": float(value)}
        for key, value in flights.groupby("operator_key")["flights"]
        .sum()
        .sort_values(ascending=False)
        .head(15)
        .items()
    ]
    group_keys = {"AEROMEXICO", "AEROMEXICO_CONNECT", UNSPLIT_AEROMEXICO}
    own = flights[flights["operator_key"].isin(group_keys)].copy()
    if not own.empty:
        own["market_key"] = own.apply(
            lambda row: market_key(row["origin_iata"], row["dest_iata"]), axis=1
        )
        summary["aeromexico_markets"] = [
            {"market_key": key, "flights": float(value)}
            for key, value in own.groupby("market_key")["flights"]
            .sum()
            .sort_values(ascending=False)
            .items()
        ]
    return summary
