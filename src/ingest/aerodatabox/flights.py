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

Every response is cached on disk keyed by airport and window.  API units are
spent once; re-running the pull is free.
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


API_HOST = "aerodatabox.p.rapidapi.com"
BASE_URL = f"https://{API_HOST}/flights/airports/iata"
# The Basic plan answers a window longer than this with an empty list.
MAX_WINDOW_HOURS = 12
UNITS_PER_CALL = 2
# Basic allows one request per second; stay under it.
MIN_SECONDS_BETWEEN_CALLS = 1.1

# IATA code to the project's carrier_key.  Mexico's scheduled domestic carriers
# only; anything else is foreign or charter and is dropped with a count.
CARRIER_BY_IATA: dict[str, str] = {
    "AM": "AEROMEXICO",          # split from Connect below, by fleet
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
    "VOI": "VOLARIS",
    "VIV": "VIVA_AEROBUS",
    "TQR": "TAR",
    "GMT": "MAGNICHARTERS",
    "CFV": "AEREO_CALAFIA",
    "MXA": "MEXICANA_NUEVA",
}
CARRIER_BY_NAME: dict[str, str] = {
    "aerus": "AERUS",
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


def _cache_path(cache_dir: Path, iata: str, start: str) -> Path:
    return cache_dir / f"{iata}_{start.replace(':', '')}.json"


def fetch_window(
    iata: str,
    start: str,
    end: str,
    *,
    api_key: str,
    cache_dir: Path,
    stats: PullStats,
    client: httpx.Client | None = None,
) -> list[dict]:
    """One airport, one window of at most 12 hours, cached on disk."""

    path = _cache_path(cache_dir, iata, start)
    if path.exists():
        stats.cached_calls += 1
        return json.loads(path.read_text())

    url = f"{BASE_URL}/{iata}/{start}/{end}"
    params = {
        "direction": "Departure",
        # Required: without it a departure record carries no arrival airport
        # at all, so the route is unknowable and the pull is wasted.
        "withLeg": "true",
        "withCancelled": "true",
        "withCodeshared": "false",
        "withCargo": "false",
        "withPrivate": "false",
        "withLocation": "false",
    }
    headers = {"x-rapidapi-key": api_key, "x-rapidapi-host": API_HOST}
    owns_client = client is None
    client = client or httpx.Client(timeout=90.0)
    try:
        response = client.get(url, params=params, headers=headers)
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
    icao = (airline.get("icao") or "").upper()
    if icao in NON_SCHEDULED_ICAO:
        stats.non_scheduled_dropped += 1
        return None

    key = (
        CARRIER_BY_IATA.get(airline.get("iata") or "")
        or CARRIER_BY_ICAO.get(icao)
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
        return key
    return "AEROMEXICO_CONNECT" if CONNECT_FLEET.search(model) else key


def normalise(
    raw: dict[str, list[dict]], period_id: str, *, stats: PullStats,
    reference_dir: Path | None = None,
) -> pd.DataFrame:
    """Turn cached responses into the ``FLIGHT_COLUMNS`` contract."""

    domestic = set(load_city_crosswalk(reference_dir))
    rows: list[tuple[str, str, str, str, int]] = []
    for origin, flights in raw.items():
        for flight in flights:
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
            rows.append((period_id, origin, dest, carrier, 1))

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
    unit_budget: int | None = None,
    reference_dir: Path | None = None,
) -> tuple[pd.DataFrame, PullStats]:
    """Sweep every airport across whole days, in half-day windows.

    ``unit_budget`` is a hard stop: the pull returns what it has rather than
    spending past it, because the free tier is small enough that overrunning
    costs the next attempt.
    """

    api_key = api_key or os.environ.get("RAPIDAPI_KEY")
    if not api_key:
        raise RuntimeError("RAPIDAPI_KEY is not set")

    stats = PullStats()
    raw: dict[str, list[dict]] = {}
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
                            raw, period_id, stats=stats, reference_dir=reference_dir
                        ), stats
                    wait = MIN_SECONDS_BETWEEN_CALLS - (time.monotonic() - last_call)
                    if wait > 0 and not _cache_path(cache_dir, iata, start).exists():
                        time.sleep(wait)
                    flights = fetch_window(
                        iata, start, end, api_key=api_key, cache_dir=cache_dir,
                        stats=stats, client=client,
                    )
                    last_call = time.monotonic()
                    raw.setdefault(iata, []).extend(flights)

    return normalise(raw, period_id, stats=stats, reference_dir=reference_dir), stats
