"""The adapter's job is to drop the right flights, silently to no one.

Every filter here corresponds to a way the seed can be corrupted: a codeshare
double-counts one flight under two carriers and moves the within-route
proportions that are the seed's entire content; a cargo run inflates a route
that carries no passengers; and a record with no arrival airport belongs to no
route at all.
"""

from __future__ import annotations

from datetime import date
import json
import os
import time

import httpx
import pandas as pd
import pytest

from src.ingest.aerodatabox.flights import (
    MAX_CACHE_AGE_SECONDS,
    PullStats,
    fetch_window,
    normalise,
    purge_expired_cache,
)


def _flight(
    dest: str | None = "GDL",
    *,
    iata: str | None = "AM",
    icao: str | None = "AMX",
    name: str = "Aeromexico",
    model: str | None = "Boeing 737-800",
    cargo: bool = False,
    codeshare: str = "IsOperator",
) -> dict:
    arrival = {"airport": {"iata": dest}} if dest else None
    return {
        "airline": {"iata": iata, "icao": icao, "name": name},
        "arrival": arrival,
        "aircraft": {"model": model} if model else {},
        "isCargo": cargo,
        "codeshareStatus": codeshare,
    }


def _run(flights: list[dict], origin: str = "MEX") -> tuple[pd.DataFrame, PullStats]:
    stats = PullStats()
    return normalise({origin: flights}, "2026M02", stats=stats), stats


def test_counts_one_flight_per_record() -> None:
    frame, _ = _run([_flight(), _flight()])
    assert frame.loc[0, "flights"] == 2
    assert frame.loc[0, "carrier_key"] == "AEROMEXICO"
    assert (frame.loc[0, "origin_iata"], frame.loc[0, "dest_iata"]) == ("MEX", "GDL")


def test_connect_is_split_from_mainline_by_fleet() -> None:
    """Both file under AM; AFAC counts them separately, so the fleet decides."""

    frame, _ = _run([_flight(model="Embraer 190"), _flight(model="Boeing 737 MAX 8")])
    assert set(frame["carrier_key"]) == {"AEROMEXICO_CONNECT", "AEROMEXICO"}


def test_aeromexico_without_a_model_is_not_guessed_as_mainline() -> None:
    frame, stats = _run([_flight(model=None)])
    assert frame.empty
    assert stats.aircraft_model_missing == 1
    assert stats.unmapped_carriers["AM:aircraft_model_missing"] == 1


def test_connect_resolves_from_its_own_operator_codes() -> None:
    frame, _ = _run([
        _flight(iata="5D", icao="SLI", name="Aeromexico Connect", model=None),
    ])
    assert frame.loc[0, "carrier_key"] == "AEROMEXICO_CONNECT"


def test_cancelled_flights_are_dropped_defensively() -> None:
    flight = _flight()
    flight["status"] = "Canceled"
    frame, stats = _run([flight])
    assert frame.empty
    assert stats.cancelled_dropped == 1


def test_codeshares_are_dropped() -> None:
    frame, stats = _run([_flight(codeshare="IsCodeshared")])
    assert frame.empty
    assert stats.codeshares_dropped == 1


def test_cargo_is_dropped() -> None:
    frame, stats = _run([_flight(cargo=True)])
    assert frame.empty
    assert stats.cargo_dropped == 1


def test_a_record_without_an_arrival_airport_is_reported_not_silently_lost() -> None:
    """This is the withLeg trap: no leg, no arrival, no route."""

    frame, stats = _run([_flight(dest=None)])
    assert frame.empty
    assert stats.missing_arrival == 1


def test_foreign_destinations_are_dropped() -> None:
    frame, stats = _run([_flight(dest="LAX")])
    assert frame.empty
    assert stats.foreign_destinations == 1


def test_aerus_resolves_by_name_despite_having_no_iata_code() -> None:
    frame, stats = _run([_flight(iata=None, icao=None, name="Aerus", model=None)])
    assert frame.loc[0, "carrier_key"] == "AERUS"
    assert not stats.unmapped_carriers


def test_reviewed_icao_code_resolves_when_feed_places_it_in_iata_field() -> None:
    frame, stats = _run([
        _flight(iata="MXA", icao=None, name="Mexicana", model=None),
    ])
    assert frame.loc[0, "carrier_key"] == "MEXICANA_NUEVA"
    assert not stats.unmapped_carriers


def test_magnicharter_singular_live_name_resolves() -> None:
    frame, stats = _run([
        _flight(iata=None, icao=None, name="Magnicharter", model=None),
    ])
    assert frame.loc[0, "carrier_key"] == "MAGNICHARTERS"
    assert not stats.unmapped_carriers


def test_estafeta_is_dropped_as_freight_not_mistaken_for_aerus() -> None:
    """E7 is Estafeta, a cargo carrier -- an easy and costly mis-mapping."""

    frame, stats = _run([_flight(iata="E7", icao="ESF", name="Estafeta")])
    assert frame.empty
    assert stats.non_scheduled_dropped == 1
    assert not stats.unmapped_carriers


def test_an_unknown_carrier_is_surfaced_rather_than_dropped_quietly() -> None:
    frame, stats = _run([_flight(iata="ZZ", icao="ZZZ", name="Nueva")])
    assert frame.empty
    assert stats.unmapped_carriers["ZZ"] == 1


def test_flights_are_aggregated_per_route_and_carrier() -> None:
    frame, _ = _run(
        [_flight(dest="GDL"), _flight(dest="GDL"), _flight(dest="CUN")]
    )
    counts = dict(zip(frame["dest_iata"], frame["flights"], strict=True))
    assert counts == {"GDL": 2, "CUN": 1}


def test_day_weights_scale_a_sampled_day_into_the_month() -> None:
    """A Wednesday that stands for five Wednesdays counts five times."""

    stats = PullStats()
    raw = {("MEX", date(2026, 7, 1)): [_flight(), _flight()]}
    frame = normalise(raw, "2026M02", stats=stats, day_weights={date(2026, 7, 1): 5.0})
    assert frame.loc[0, "flights"] == pytest.approx(10.0)


def test_without_weights_every_flight_counts_once() -> None:
    stats = PullStats()
    raw = {("MEX", date(2026, 7, 1)): [_flight()]}
    assert normalise(raw, "2026M02", stats=stats).loc[0, "flights"] == pytest.approx(1.0)


def test_a_plain_airport_key_still_works_unweighted() -> None:
    """The older shape, an airport with no day, must keep parsing."""

    stats = PullStats()
    assert normalise({"MEX": [_flight()]}, "2026M02", stats=stats).loc[0, "flights"] == 1.0


def test_fetch_excludes_cancelled_flights_at_the_api(tmp_path) -> None:
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(dict(request.url.params))
        return httpx.Response(200, json={"departures": []})

    stats = PullStats()
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        fetch_window(
            "MEX", "2026-07-01T00:00", "2026-07-01T12:00",
            api_key="test", direct=True, cache_dir=tmp_path, stats=stats, client=client,
        )

    assert seen["withCancelled"] == "false"


def test_expired_raw_cache_is_removed(tmp_path) -> None:
    path = tmp_path / "MEX_2026-07-01T0000.json"
    path.write_text(json.dumps([{"flight": "old"}]))
    old = time.time() - MAX_CACHE_AGE_SECONDS - 1
    os.utime(path, (old, old))

    assert purge_expired_cache(tmp_path) == 1
    assert not path.exists()
