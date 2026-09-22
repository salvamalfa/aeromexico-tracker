"""Everything a paid sweep depends on, checked without buying anything.

A capture that fails halfway is not just wasted money: a half-filled month
looks like a thin month, and the gate cannot tell the two apart. So the four
properties that decide whether a sweep is safe to start are each exercised
here against mocks, and the command that runs them is the same one an operator
runs before pressing the button.
"""

from __future__ import annotations

from datetime import date
import json
import time

import httpx
import pytest

from src.ingest.aerodatabox.flights import MAX_CACHE_AGE_SECONDS
from src.ingest.aerodatabox.international import (
    InternationalPullStats,
    _cache_path,
    fetch_window_both,
    normalise,
    pull_days,
    routes_by_operator,
)
from src.ingest.aerodatabox.international_cli import main


def _flight(other: str, *, codeshare: str = "IsOperator", status: str = "Departed") -> dict:
    return {
        "airline": {"iata": "AM", "icao": "AMX", "name": "Aeromexico"},
        "aircraft": {"model": "Boeing 787-9", "reg": "XA-ABC"},
        "codeshareStatus": codeshare,
        "status": status,
        "arrival": {"airport": {"iata": other}},
    }


MEXICAN = frozenset({"MEX", "MTY", "GDL"})


def test_preflight_passes_without_issuing_a_request(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("AERODATABOX_API_KEY", "preflight-only")
    monkeypatch.delenv("RAPIDAPI_KEY", raising=False)

    def explode(request: httpx.Request) -> httpx.Response:  # pragma: no cover
        raise AssertionError("preflight must not call the provider")

    original = httpx.Client
    transport = httpx.MockTransport(explode)
    monkeypatch.setattr(
        httpx, "Client", lambda **kwargs: original(transport=transport, **kwargs)
    )

    assert main(["preflight", "--bronze-dir", str(tmp_path)]) == 0


def test_preflight_fails_loudly_without_a_credential(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("AERODATABOX_API_KEY", raising=False)
    monkeypatch.delenv("RAPIDAPI_KEY", raising=False)

    assert main(["preflight", "--bronze-dir", str(tmp_path)]) == 1


def test_a_resumed_sweep_buys_nothing_it_already_has(tmp_path, monkeypatch) -> None:
    """The property that makes an interrupted capture safe to restart."""

    monkeypatch.setattr(
        "src.ingest.aerodatabox.international.MIN_SECONDS_BETWEEN_CALLS", 0
    )
    payload = {"departures": [_flight("MAD")], "arrivals": []}
    day = date(2026, 5, 6)
    for start in (f"{day}T00:00", f"{day}T12:00"):
        _cache_path(tmp_path, "MEX", start).write_text(json.dumps(payload))

    def explode(request: httpx.Request) -> httpx.Response:  # pragma: no cover
        raise AssertionError("a cached window must not be bought again")

    original = httpx.Client
    transport = httpx.MockTransport(explode)
    monkeypatch.setattr(
        httpx, "Client", lambda **kwargs: original(transport=transport, **kwargs)
    )

    flights, stats = pull_days(
        ["MEX"], [day], period_id="2026M05", cache_dir=tmp_path,
        api_key="test", direct=True, mexican=MEXICAN,
    )

    assert stats.units_spent == 0 and stats.cached_calls == 2
    assert float(flights["flights"].sum()) == 2.0


def test_expired_provider_content_is_deleted_and_not_reused(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(
        "src.ingest.aerodatabox.international.MIN_SECONDS_BETWEEN_CALLS", 0
    )
    day = date(2026, 5, 6)
    stale = _cache_path(tmp_path, "MEX", f"{day}T00:00")
    stale.write_text(json.dumps({"departures": [_flight("MAD")], "arrivals": []}))
    expired = time.time() - MAX_CACHE_AGE_SECONDS - 60
    import os

    os.utime(stale, (expired, expired))

    bought: list[str] = []

    def serve(request: httpx.Request) -> httpx.Response:
        bought.append(str(request.url))
        return httpx.Response(200, json={"departures": [], "arrivals": []})

    original = httpx.Client
    transport = httpx.MockTransport(serve)
    monkeypatch.setattr(
        httpx, "Client", lambda **kwargs: original(transport=transport, **kwargs)
    )

    _, stats = pull_days(
        ["MEX"], [day], period_id="2026M05", cache_dir=tmp_path,
        api_key="test", direct=True, mexican=MEXICAN,
    )

    assert stats.expired_cache_files == 1
    assert len(bought) == 2  # both windows had to be bought; nothing stale was reused


def test_the_budget_refuses_before_the_first_call_not_after(tmp_path) -> None:
    exit_code = main([
        "probe", "--date", "2026-09-10",
        "--airports", "MEX,MTY,GDL,CUN,SJD,PVR",
        "--budget", "8", "--bronze-dir", str(tmp_path),
    ])

    assert exit_code == 2
    assert not list(tmp_path.glob("*.json"))


def test_the_seed_carries_the_two_diagnostics_the_gate_needs() -> None:
    stats = InternationalPullStats()
    raw = {
        "MEX": {
            "departures": [
                _flight("MAD", codeshare="Unknown", status="Departed"),
                _flight("MAD", codeshare="IsOperator", status="Expected"),
            ],
            "arrivals": [],
        }
    }

    frame = normalise(raw, "2026M05", stats=stats, mexican=MEXICAN)
    collapsed = routes_by_operator(frame)

    assert float(collapsed["flights"].sum()) == 2.0
    assert float(collapsed["codeshare_unknown"].sum()) == 1.0
    assert float(collapsed["status_incomplete"].sum()) == 1.0


def test_the_diagnostics_are_weighted_like_the_flights_they_describe() -> None:
    """A sampled day counts for several, and so must its unknown code-shares."""

    stats = InternationalPullStats()
    sampled = date(2026, 5, 6)
    raw = {
        ("MEX", sampled): {
            "departures": [_flight("MAD", codeshare="Unknown")],
            "arrivals": [],
        }
    }

    frame = normalise(
        raw, "2026M05", stats=stats, mexican=MEXICAN, day_weights={sampled: 4.0}
    )

    assert float(frame["flights"].sum()) == 4.0
    assert float(frame["codeshare_unknown"].sum()) == 4.0


def test_two_sweeps_of_one_month_do_not_overwrite_each_other(tmp_path, monkeypatch) -> None:
    """The hybrid plan runs one month twice, with different airports."""

    from src.config import ProjectPaths

    monkeypatch.setattr(
        "src.ingest.aerodatabox.international.MIN_SECONDS_BETWEEN_CALLS", 0
    )
    # ``PATHS`` derives every directory from one root, so redirecting the root
    # sends Silver into the temporary directory without touching the project.
    monkeypatch.setattr(
        "src.ingest.aerodatabox.international_cli.PATHS", ProjectPaths(root=tmp_path)
    )
    silver = tmp_path / "data" / "silver"

    def serve(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"departures": [_flight("MAD")], "arrivals": []})

    original = httpx.Client
    transport = httpx.MockTransport(serve)
    monkeypatch.setattr(
        httpx, "Client", lambda **kwargs: original(transport=transport, **kwargs)
    )
    monkeypatch.setenv("AERODATABOX_API_KEY", "test")

    for tag, airports in (("nucleo", "MEX"), ("resto", "MTY")):
        main([
            "sweep", "2026M05", "--days", "1", "--airports", airports,
            "--tag", tag, "--bronze-dir", str(tmp_path / "bronze"),
        ])

    produced = sorted(path.name for path in silver.glob("aerodatabox_international_seed_*"))
    assert produced == [
        "aerodatabox_international_seed_2026M05_nucleo.parquet",
        "aerodatabox_international_seed_2026M05_resto.parquet",
    ]
