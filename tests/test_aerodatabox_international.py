"""What the international adapter must keep is the mirror of what the domestic one drops.

The domestic seed is safe because an unmappable operator is discarded: AFAC's
domestic margin contains only Mexican scheduled carriers, so a flight that
cannot be placed in the crosswalk does not belong in the cube at all.  The
international margin contains foreign carriers, so the same discard would
delete Iberia from MEX–MAD and hand its flights' share to Aeroméxico.  Most of
these tests exist to hold that difference in place.
"""

from __future__ import annotations

from datetime import date
import json

import httpx
import pandas as pd
import pytest

from src.ingest.aerodatabox.international import (
    UNSPLIT_AEROMEXICO,
    InternationalPullStats,
    _cache_path,
    fetch_window_both,
    market_key,
    normalise,
    plan_units,
    pull_days,
    routes_by_operator,
    summarise,
)


MEXICAN = frozenset({"MEX", "GDL", "MTY", "CUN", "NLU"})


def _flight(
    *,
    other: str | None,
    iata: str | None = "AM",
    icao: str | None = "AMX",
    name: str = "Aeromexico",
    model: str | None = "Boeing 787-9",
    side: str = "arrival",
    cargo: bool = False,
    codeshare: str = "IsOperator",
    status: str = "Departed",
) -> dict:
    """One FIDS record, with the opposite endpoint on ``side``."""

    movement = {"airport": {"iata": other}} if other else None
    flight = {
        "airline": {"iata": iata, "icao": icao, "name": name},
        "isCargo": cargo,
        "codeshareStatus": codeshare,
        "status": status,
    }
    if model is not None:
        flight["aircraft"] = {"model": model, "reg": "XA-ABC"}
    flight[side] = movement
    return flight


def _payload(departures=(), arrivals=()) -> dict:
    return {"departures": list(departures), "arrivals": list(arrivals)}


def test_both_directions_of_a_market_are_counted_once_each() -> None:
    stats = InternationalPullStats()
    raw = {
        "MEX": _payload(
            departures=[_flight(other="MAD", side="arrival")],
            arrivals=[_flight(other="MAD", side="departure")],
        )
    }
    frame = normalise(raw, "2026M05", stats=stats, mexican=MEXICAN)

    legs = {(row.origin_iata, row.dest_iata): row.flights for row in frame.itertuples()}
    assert legs == {("MEX", "MAD"): 1.0, ("MAD", "MEX"): 1.0}
    assert stats.departures_seen == 1 and stats.arrivals_seen == 1


def test_a_domestic_leg_is_dropped_at_both_ends_not_deduplicated() -> None:
    """MEX–GDL is seen as a departure at MEX and an arrival at GDL."""

    stats = InternationalPullStats()
    raw = {
        "MEX": _payload(departures=[_flight(other="GDL", side="arrival")]),
        "GDL": _payload(arrivals=[_flight(other="MEX", side="departure")]),
    }
    frame = normalise(raw, "2026M05", stats=stats, mexican=MEXICAN)

    assert frame.empty
    assert stats.domestic_legs_dropped == 2


def test_a_foreign_operator_is_kept_under_its_published_identity() -> None:
    """Dropping Iberia would hand its share of MEX–MAD to Aeroméxico."""

    stats = InternationalPullStats()
    raw = {
        "MEX": _payload(
            departures=[
                _flight(other="MAD", side="arrival"),
                _flight(
                    other="MAD", side="arrival", iata="IB", icao="IBE",
                    name="Iberia", model="Airbus A350-900",
                ),
            ]
        )
    }
    frame = normalise(raw, "2026M05", stats=stats, mexican=MEXICAN)

    assert set(frame["operator_key"]) == {"AEROMEXICO", "IATA:IB"}
    assert frame["flights"].sum() == 2.0
    assert stats.unmapped_operators["IATA:IB"] == 1
    kept = frame[frame["operator_key"] == "IATA:IB"].iloc[0]
    assert kept["operator_icao"] == "IBE" and kept["operator_name"] == "Iberia"


def test_an_operator_with_no_identity_at_all_is_the_only_one_dropped() -> None:
    stats = InternationalPullStats()
    raw = {
        "MEX": _payload(
            departures=[
                _flight(other="MAD", side="arrival", iata=None, icao=None, name="")
            ]
        )
    }
    assert normalise(raw, "2026M05", stats=stats, mexican=MEXICAN).empty
    assert stats.unmapped_operators["?"] == 1


def test_aeromexico_splits_by_fleet_and_never_guesses_without_a_model() -> None:
    stats = InternationalPullStats()
    raw = {
        "MEX": _payload(
            departures=[
                _flight(other="SAL", side="arrival", model="Embraer 190"),
                _flight(other="MAD", side="arrival", model=None),
            ]
        )
    }
    frame = normalise(raw, "2026M05", stats=stats, mexican=MEXICAN)

    keys = dict(zip(frame["dest_iata"], frame["operator_key"]))
    assert keys["SAL"] == "AEROMEXICO_CONNECT"
    # Kept, not dropped: the flight is real even though the operator is unsplit.
    assert keys["MAD"] == UNSPLIT_AEROMEXICO
    assert stats.aeromexico_unsplit == 1


@pytest.mark.parametrize(
    "kwargs,counter",
    [
        ({"codeshare": "IsCodeshared"}, "codeshares_dropped"),
        ({"cargo": True}, "cargo_dropped"),
        ({"status": "Canceled"}, "cancelled_dropped"),
    ],
)
def test_the_filters_the_request_asked_for_are_enforced_again(kwargs, counter) -> None:
    stats = InternationalPullStats()
    raw = {"MEX": _payload(departures=[_flight(other="MAD", side="arrival", **kwargs)])}

    assert normalise(raw, "2026M05", stats=stats, mexican=MEXICAN).empty
    assert getattr(stats, counter) == 1


def test_a_record_without_the_opposite_endpoint_belongs_to_no_route() -> None:
    stats = InternationalPullStats()
    raw = {"MEX": _payload(departures=[_flight(other=None, side="arrival")])}

    assert normalise(raw, "2026M05", stats=stats, mexican=MEXICAN).empty
    assert stats.missing_arrival == 1


def test_a_sampled_day_counts_as_its_weekdays_share_of_the_month() -> None:
    stats = InternationalPullStats()
    sampled = date(2026, 5, 6)
    raw = {("MEX", sampled): _payload(departures=[_flight(other="MAD", side="arrival")])}

    frame = normalise(
        raw, "2026M05", stats=stats, mexican=MEXICAN, day_weights={sampled: 4.0}
    )

    assert frame["flights"].sum() == 4.0


def test_the_both_direction_cache_cannot_collide_with_the_domestic_one(tmp_path) -> None:
    from src.ingest.aerodatabox.flights import _cache_path as domestic_path

    assert _cache_path(tmp_path, "MEX", "2026-05-06T00:00") != domestic_path(
        tmp_path, "MEX", "2026-05-06T00:00"
    )


def test_a_cached_window_round_trips_and_costs_nothing(tmp_path) -> None:
    stats = InternationalPullStats()
    payload = _payload(departures=[_flight(other="MAD", side="arrival")])
    _cache_path(tmp_path, "MEX", "2026-05-06T00:00").write_text(json.dumps(payload))

    def explode(request: httpx.Request) -> httpx.Response:  # pragma: no cover
        raise AssertionError("a fresh cache entry must not be bought again")

    with httpx.Client(transport=httpx.MockTransport(explode)) as client:
        result = fetch_window_both(
            "MEX", "2026-05-06T00:00", "2026-05-06T12:00",
            api_key="test", direct=True, cache_dir=tmp_path, stats=stats, client=client,
        )

    assert result == payload
    assert stats.units_spent == 0 and stats.cached_calls == 1


def test_an_empty_window_is_reported_rather_than_swallowed(tmp_path) -> None:
    stats = InternationalPullStats()

    def empty(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"departures": [], "arrivals": []})

    with httpx.Client(transport=httpx.MockTransport(empty)) as client:
        fetch_window_both(
            "MEX", "2026-05-06T00:00", "2026-05-06T12:00",
            api_key="test", direct=True, cache_dir=tmp_path, stats=stats, client=client,
        )

    assert stats.empty_windows == ["MEX 2026-05-06T00:00"]


def test_the_sweep_stops_before_spending_past_its_budget(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(
        "src.ingest.aerodatabox.international.MIN_SECONDS_BETWEEN_CALLS", 0
    )
    calls: list[str] = []

    def one_leg(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        return httpx.Response(
            200,
            json=_payload(departures=[_flight(other="MAD", side="arrival")]),
        )

    transport = httpx.MockTransport(one_leg)
    original = httpx.Client
    monkeypatch.setattr(
        httpx, "Client", lambda **kwargs: original(transport=transport, **kwargs)
    )

    flights, stats = pull_days(
        ["MEX", "MTY"], [date(2026, 5, 6)], period_id="2026M05",
        cache_dir=tmp_path, api_key="test", direct=True, unit_budget=4,
        mexican=MEXICAN,
    )

    assert stats.units_spent == 4 and len(calls) == 2
    assert not flights.empty


def test_the_plan_prices_a_sweep_before_it_is_bought() -> None:
    # 58 airports, a seven-day sample, two windows a day, two units a window.
    assert plan_units(58, 7) == 1_624


def test_the_seed_grain_collapses_to_route_by_operator() -> None:
    stats = InternationalPullStats()
    raw = {
        "MEX": _payload(
            departures=[
                _flight(other="MAD", side="arrival", model="Boeing 787-9"),
                _flight(other="MAD", side="arrival", model="Boeing 787-8"),
            ]
        )
    }
    frame = normalise(raw, "2026M05", stats=stats, mexican=MEXICAN)

    assert len(frame) == 2  # two aircraft models
    collapsed = routes_by_operator(frame)
    assert len(collapsed) == 1 and collapsed.iloc[0]["flights"] == 2.0


def test_a_market_key_is_direction_free() -> None:
    assert market_key("MEX", "MAD") == market_key("MAD", "MEX") == "MAD<>MEX"


def test_the_summary_carries_counts_and_no_provider_records() -> None:
    stats = InternationalPullStats()
    stats.calls, stats.units_spent = 2, 4
    raw = {
        "MEX": _payload(
            departures=[
                _flight(other="MAD", side="arrival"),
                _flight(
                    other="MAD", side="arrival", iata="IB", icao="IBE", name="Iberia"
                ),
            ]
        )
    }
    frame = normalise(raw, "2026M05", stats=stats, mexican=MEXICAN)

    summary = summarise(frame, stats)

    assert summary["units_spent"] == 4
    assert summary["markets"] == 1 and summary["operators"] == 2
    assert summary["aeromexico_markets"] == [{"market_key": "MAD<>MEX", "flights": 1.0}]
    # An aggregate only: no flight record, tail number or timestamp survives.
    serialised = json.dumps(summary)
    assert "XA-ABC" not in serialised and "codeshareStatus" not in serialised


def test_an_empty_capture_summarises_without_pretending_to_have_data() -> None:
    summary = summarise(pd.DataFrame(), InternationalPullStats())

    assert summary["markets"] == 0 and summary["international_legs"] == 0
    assert summary["aeromexico_markets"] == []
