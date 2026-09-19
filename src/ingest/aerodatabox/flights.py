"""Pull departures from AeroDataBox and shape them into an estimator seed.

The seed only needs the *relative* structure of supply within a route, so this
module stays deliberately small: count departures per route and carrier, and let
iterative proportional fitting handle the rest.

Two traps are encoded here rather than left to the caller:

- The free tier caps a query at **12 hours** and answers a longer window with an
  empty list instead of an error, so a naive one-call-per-day pull silently
  returns nothing.  Windows are therefore built as half-days and a full-day slot
  that comes back empty is reported, not swallowed.
- Codeshares would double-count a flight under two carriers and wreck exactly
  the within-route proportions the seed exists to carry, so only the operating
  carrier is kept.

Every response is cached on disk keyed by airport and window.  Provider terms
limit raw-response retention, so cache files expire after seven days.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import date, timedelta
import json
import os
from pathlib import Path
import re
import time

import httpx
import pandas as pd

from src.analytics.route_carrier import load_city_crosswalk


# Two ways in, priced differently: RapidAPI resells the same API, and the
# direct plans are cheaper per unit.  They differ only in host and auth header,
# so the caller picks one and nothing else changes.
RAPIDAPI_HOST = "aerodatabox.p.rapidapi.com"
RAPIDAPI_URL = f"https://{RAPIDAPI_HOST}/flights/airports/iata"
# Host and header taken from the official direct specification
# (doc.aerodatabox.com/docs/openapi-direct-v1.yaml): server
# `https://api.aerodatabox.com/`, security scheme `X-Api-Key` in the header.
DIRECT_URL = "https://api.aerodatabox.com/flights/airports/iata"
# The Basic plan answers a window longer than this with an empty list.
MAX_WINDOW_HOURS = 12
# The specification marks this endpoint TIER 2, and the pricing table puts a
# tier-2 request at two units on every plan.  Measured against the live API at
# two units as well, so the direct plans cost the same per call as RapidAPI.
UNITS_PER_CALL = 2
# Basic allows one request per second; stay under it.
MIN_SECONDS_BETWEEN_CALLS = 1.1
# AeroDataBox permits raw API contents to be cached for at most seven days.
MAX_CACHE_AGE_SECONDS = 7 * 24 * 60 * 60

# IATA code to the project's carrier_key.  Mexico's scheduled domestic carriers
# only; anything else is foreign or charter and is dropped with a count.
CARRIER_BY_IATA: dict[str, str] = {
    "AM": "AEROMEXICO",          # split from Connect below, by fleet
    "5D": "AEROMEXICO_CONNECT",
    "Y4": "VOLARIS",
    "VB": "VIVA_AEROBUS",
    "YQ": "TAR",
    "UJ": "MAGNICHARTERS",
    "A7": "AEREO_CALAFIA",
}
# Aerus files without an IATA code, so it has to be matched on identity fields
# the feed does carry.  Mexicana likewise publishes under codes that vary.
CARRIER_BY_ICAO: dict[str, str] = {
    "AMX": "AEROMEXICO",
    "SLI": "AEROMEXICO_CONNECT",
    "VOI": "VOLARIS",
    "VIV": "VIVA_AEROBUS",
    "TQR": "TAR",
    "GMT": "MAGNICHARTERS",
    "CFV": "AEREO_CALAFIA",
    "MXA": "MEXICANA_NUEVA",
}
CARRIER_BY_NAME: dict[str, str] = {
    "aerus": "AERUS",
    "aeromexico connect": "AEROMEXICO_CONNECT",
    "aerolitoral": "AEROMEXICO_CONNECT",
    "magnicharter": "MAGNICHARTERS",
    "magnicharters": "MAGNICHARTERS",
    "mexicana": "MEXICANA_NUEVA",
}
# Cargo and charter operators that fly domestic legs but are outside AFAC's
# scheduled-passenger universe.  Named explicitly so they are dropped knowingly
# rather than surfacing as "unmapped" noise on every run.  E7 is Estafeta, a
# freight carrier -- not Aerus, which files with no IATA code at all.
NON_SCHEDULED_ICAO: frozenset[str] = frozenset(
    {"ESF", "XAR", "VTM", "MNU", "AJT"}
)

# Aeroméxico and Aerolitoral file under one IATA code but are separate carriers
# in the AFAC margin.  Aerolitoral is the Embraer operator.
CONNECT_FLEET = re.compile(r"embraer", re.IGNORECASE)


class WindowTooLongError(ValueError):
    """A window longer than the plan allows would return an empty list."""


@dataclass
class PullStats:
    """What the pull cost and what it had to throw away."""

    calls: int = 0
    units_spent: int = 0
    cached_calls: int = 0
    empty_windows: list[str] = field(default_factory=list)
    unmapped_carriers: Counter = field(default_factory=Counter)
    foreign_destinations: int = 0
    codeshares_dropped: int = 0
    cargo_dropped: int = 0
    missing_arrival: int = 0
    non_scheduled_dropped: int = 0
    aircraft_model_missing: int = 0
    cancelled_dropped: int = 0
    expired_cache_files: int = 0


def _cache_path(cache_dir: Path, iata: str, start: str) -> Path:
    return cache_dir / f"{iata}_{start.replace(':', '')}.json"


def _cache_is_fresh(path: Path, *, now: float | None = None) -> bool:
    if not path.exists():
        return False
    current = time.time() if now is None else now
    return current - path.stat().st_mtime <= MAX_CACHE_AGE_SECONDS


def purge_expired_cache(cache_dir: Path, *, now: float | None = None) -> int:
    """Delete raw responses older than the provider's seven-day limit."""

    if not cache_dir.exists():
        return 0
    removed = 0
    for path in cache_dir.glob("*.json"):
        if not _cache_is_fresh(path, now=now):
            path.unlink()
            removed += 1
    return removed


def api_credentials(
    api_key: str | None = None, *, direct: bool | None = None
) -> tuple[str, dict[str, str]]:
    """Resolve the base URL and auth headers for whichever plan is configured.

    ``AERODATABOX_API_KEY`` selects the direct plans, ``RAPIDAPI_KEY`` the
    resold ones.  Passing ``api_key`` overrides both, and ``direct`` says which
    of the two it is.
    """

    if api_key is not None:
        if direct is None:
            raise ValueError("pass direct=True or direct=False with an explicit api_key")
    elif os.environ.get("AERODATABOX_API_KEY"):
        api_key, direct = os.environ["AERODATABOX_API_KEY"], True
    elif os.environ.get("RAPIDAPI_KEY"):
        api_key, direct = os.environ["RAPIDAPI_KEY"], False
    else:
        raise RuntimeError(
            "Set AERODATABOX_API_KEY (direct plans) or RAPIDAPI_KEY (RapidAPI)"
        )

    if direct:
        return DIRECT_URL, {"X-Api-Key": api_key}
    return RAPIDAPI_URL, {"x-rapidapi-key": api_key, "x-rapidapi-host": RAPIDAPI_HOST}


def fetch_window(
    iata: str,
    start: str,
    end: str,
    *,
    api_key: str | None = None,
    direct: bool | None = None,
    cache_dir: Path,
    stats: PullStats,
    client: httpx.Client | None = None,
) -> list[dict]:
    """One airport, one window of at most 12 hours, cached on disk."""

    path = _cache_path(cache_dir, iata, start)
    if _cache_is_fresh(path):
        stats.cached_calls += 1
        return json.loads(path.read_text())
    if path.exists():
        path.unlink()
        stats.expired_cache_files += 1

    base_url, headers = api_credentials(api_key, direct=direct)
    params = {
        "direction": "Departure",
        # Required: without it a departure record carries no arrival airport
        # at all, so the route is unknowable and the pull is wasted.
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
        response = client.get(f"{base_url}/{iata}/{start}/{end}", params=params, headers=headers)
    finally:
        if owns_client:
            client.close()

    stats.calls += 1
    stats.units_spent += UNITS_PER_CALL
    if response.status_code == 204:
        departures: list[dict] = []
    else:
        response.raise_for_status()
        departures = response.json().get("departures", []) or []

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(departures))
    if not departures:
        stats.empty_windows.append(f"{iata} {start}")
    return departures


def _carrier_key(flight: dict, stats: PullStats) -> str | None:
    """Resolve the operating carrier, or None if it is outside AFAC's universe."""

    airline = flight.get("airline") or {}
    iata = (airline.get("iata") or "").upper()
    icao = (airline.get("icao") or "").upper()
    if icao in NON_SCHEDULED_ICAO or iata in NON_SCHEDULED_ICAO:
        stats.non_scheduled_dropped += 1
        return None

    key = (
        CARRIER_BY_IATA.get(iata)
        or CARRIER_BY_ICAO.get(icao)
        # The live feed occasionally places a three-letter ICAO code in the
        # IATA field (MXA was observed this way). Resolve only codes already in
        # the reviewed crosswalk; never infer an unknown carrier.
        or CARRIER_BY_ICAO.get(iata)
        or CARRIER_BY_IATA.get(icao)
        or CARRIER_BY_NAME.get((airline.get("name") or "").strip().lower())
    )
    if key is None:
        stats.unmapped_carriers[
            airline.get("iata") or icao or airline.get("name") or "?"
        ] += 1
        return None
    if key != "AEROMEXICO":
        return key

    model = (flight.get("aircraft") or {}).get("model")
    if not model:
        stats.aircraft_model_missing += 1
        stats.unmapped_carriers["AM:aircraft_model_missing"] += 1
        return None
    return "AEROMEXICO_CONNECT" if CONNECT_FLEET.search(model) else key


def normalise(
    raw: dict[str, list[dict]], period_id: str, *, stats: PullStats,
    reference_dir: Path | None = None,
    day_weights: dict[date, float] | None = None,
) -> pd.DataFrame:
    """Turn cached responses into the ``FLIGHT_COLUMNS`` contract.

    ``raw`` maps an airport, or an ``(airport, day)`` pair, to its departures.
    With ``day_weights`` each flight counts as its day's weight instead of one,
    which is what lets a sampled week stand in for a whole month: a month with
    five Wednesdays and four Sundays needs the sampled Wednesday counted five
    times and the Sunday four, or every carrier's mix is read through whichever
    weekdays happened to be sampled.
    """

    domestic = set(load_city_crosswalk(reference_dir))
    rows: list[tuple[str, str, str, str, float]] = []
    for key, flights in raw.items():
        origin, day = key if isinstance(key, tuple) else (key, None)
        weight = 1.0 if day_weights is None else float(day_weights.get(day, 1.0))
        for flight in flights:
            if str(flight.get("status") or "").strip().lower() in {"canceled", "cancelled"}:
                stats.cancelled_dropped += 1
                continue
            if flight.get("isCargo"):
                stats.cargo_dropped += 1
                continue
            if flight.get("codeshareStatus") == "IsCodeshared":
                stats.codeshares_dropped += 1
                continue
            dest = ((flight.get("arrival") or {}).get("airport") or {}).get("iata")
            if not dest:
                stats.missing_arrival += 1
                continue
            if dest not in domestic:
                stats.foreign_destinations += 1
                continue
            carrier = _carrier_key(flight, stats)
            if carrier is None:
                continue
            rows.append((period_id, origin, dest, carrier, weight))

    frame = pd.DataFrame(
        rows, columns=["period_id", "origin_iata", "dest_iata", "carrier_key", "flights"]
    )
    if frame.empty:
        return frame
    return frame.groupby(
        ["period_id", "origin_iata", "dest_iata", "carrier_key"], as_index=False
    )["flights"].sum()


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
) -> tuple[pd.DataFrame, PullStats]:
    """Sweep every airport across whole days, in half-day windows.

    ``unit_budget`` is a hard stop: the pull returns what it has rather than
    spending past it, because the free tier is small enough that overrunning
    costs the next attempt.
    """

    base_url, _ = api_credentials(api_key, direct=direct)   # falla temprano si no hay llave
    del base_url

    stats = PullStats()
    stats.expired_cache_files = purge_expired_cache(cache_dir)
    raw: dict[tuple[str, date], list[dict]] = {}
    last_call = 0.0
    with httpx.Client(timeout=90.0) as client:
        for day in days:
            halves = [
                (f"{day}T00:00", f"{day}T12:00"),
                (f"{day}T12:00", f"{day + timedelta(days=1)}T00:00"),
            ]
            for start, end in halves:
                for iata in airports:
                    if (
                        unit_budget is not None
                        and stats.units_spent + UNITS_PER_CALL > unit_budget
                        and not _cache_path(cache_dir, iata, start).exists()
                    ):
                        return normalise(
                            raw, period_id, stats=stats,
                            reference_dir=reference_dir, day_weights=day_weights,
                        ), stats
                    wait = MIN_SECONDS_BETWEEN_CALLS - (time.monotonic() - last_call)
                    if wait > 0 and not _cache_path(cache_dir, iata, start).exists():
                        time.sleep(wait)
                    flights = fetch_window(
                        iata, start, end, api_key=api_key, direct=direct,
                        cache_dir=cache_dir, stats=stats, client=client,
                    )
                    last_call = time.monotonic()
                    raw.setdefault((iata, day), []).extend(flights)

    return normalise(
        raw, period_id, stats=stats,
        reference_dir=reference_dir, day_weights=day_weights,
    ), stats
