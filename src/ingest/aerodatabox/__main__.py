"""One command to turn a paid month of API quota into published estimates.

    uv run python -m src.ingest.aerodatabox 2026M07

Pulls every Mexican airport across the whole month, shapes the result into a
seed, runs the acceptance test, and only then fits the estimate.  The order
matters: the acceptance test is what stands between a cheap data source and a
published number that is quietly wrong, so it is not optional and its verdict
is not advisory -- a seed it rejects does not get fitted unless the operator
says so explicitly and knowingly.

Responses are cached on disk, so an interrupted run resumes without spending
API units again.
"""

from __future__ import annotations

import argparse
import calendar
from datetime import date
from pathlib import Path
import sys

from src.analytics.route_carrier import (
    build_seed_from_flights,
    estimate_route_carrier,
    load_afac_domestic_margins,
    load_city_crosswalk,
)
from src.analytics.seed_acceptance import assess_seed, format_report
from src.config import PATHS
from src.ingest.aerodatabox.flights import UNITS_PER_CALL, pull_days


WINDOWS_PER_DAY = 2


def month_days(period_id: str, sample: int | None = None) -> list[date]:
    """Every day of the month, or a sample of whole days that is weekday-balanced.

    Carrier mix moves with the weekly schedule, so a sample that over-represents
    a weekday biases the seed.  Even spacing does not fix this on its own: seven
    days spread over thirty-one lands on a step of four, but a step that is a
    multiple of seven would hit the same weekday every time.  Stepping by a
    number coprime with seven walks every weekday in turn.
    """

    year, month = int(period_id[:4]), int(period_id[5:])
    total = calendar.monthrange(year, month)[1]
    days = [date(year, month, day) for day in range(1, total + 1)]
    if sample is None or sample >= total:
        return days

    step = max(1, total // sample)
    if step % 7 == 0:
        step += 1
    picked = [days[(index * step) % total] for index in range(sample)]
    # A step that wraps can repeat a day; fall back to the nearest unused one.
    seen: set[date] = set()
    result: list[date] = []
    for day in picked:
        while day in seen:
            day = days[(days.index(day) + 1) % total]
        seen.add(day)
        result.append(day)
    return sorted(result)


def plan(airports: int, days: int) -> int:
    """API units a sweep will cost, so the operator sees it before spending."""

    return airports * days * WINDOWS_PER_DAY * UNITS_PER_CALL


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m src.ingest.aerodatabox")
    parser.add_argument("period_id", help="month to estimate, e.g. 2026M07")
    parser.add_argument(
        "--days", type=int, default=None,
        help="sample this many whole days instead of the entire month",
    )
    parser.add_argument(
        "--budget", type=int, default=None,
        help="stop before spending more than this many API units",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="print the call plan and its cost without spending anything",
    )
    parser.add_argument(
        "--fit-rejected-seed", action="store_true",
        help="fit even if the acceptance test rejects the seed (not for publication)",
    )
    parser.add_argument("--cache-dir", type=Path, default=PATHS.data / "cache" / "aerodatabox")
    args = parser.parse_args(argv)

    airports = sorted(load_city_crosswalk())
    days = month_days(args.period_id, args.days)
    cost = plan(len(airports), len(days))
    print(
        f"{len(airports)} aeropuertos x {len(days)} dias x {WINDOWS_PER_DAY} ventanas "
        f"= {cost:,} unidades"
    )
    if args.dry_run:
        return 0

    args.cache_dir.mkdir(parents=True, exist_ok=True)
    flights, stats = pull_days(
        airports, days, period_id=args.period_id,
        cache_dir=args.cache_dir, unit_budget=args.budget,
    )
    print(
        f"llamadas {stats.calls} (cache {stats.cached_calls})  "
        f"unidades gastadas {stats.units_spent}"
    )
    if stats.unmapped_carriers:
        print(f"aerolineas sin mapear: {stats.unmapped_carriers.most_common(8)}")
    if flights.empty:
        print("La fuente no devolvio vuelos nacionales; nada que ajustar.", file=sys.stderr)
        return 1

    out = PATHS.data / "silver"
    out.mkdir(parents=True, exist_ok=True)
    flights.to_parquet(out / f"aerodatabox_flights_{args.period_id}.parquet")

    report = assess_seed(flights, args.period_id)
    print()
    print(format_report(report))

    if not report.accepted and not args.fit_rejected_seed:
        print(
            "\nLa semilla no pasa la prueba de aceptacion, asi que no se ajusta.\n"
            "Repite con --fit-rejected-seed solo para diagnostico, nunca para publicar.",
            file=sys.stderr,
        )
        return 2

    seed = build_seed_from_flights(flights)
    route_totals, carrier_totals = load_afac_domestic_margins()
    estimate, diagnostics = estimate_route_carrier(
        seed,
        route_totals[route_totals["period_id"] == args.period_id],
        carrier_totals[carrier_totals["period_id"] == args.period_id],
    )
    estimate["is_estimated"] = True
    estimate.to_parquet(out / f"route_carrier_estimate_{args.period_id}.parquet")
    print(f"\nestimacion: {len(estimate):,} celdas ruta x aerolinea")
    print(diagnostics.to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
