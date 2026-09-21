"""Plan, probe and capture the international counterpart of the domestic seed.

Three subcommands, in the order they are meant to be used:

``plan``   prints the call plan and its cost and spends nothing.
``probe``  buys the smallest capture that can answer whether the source carries
           Aeroméxico's international network at all, under a hard unit cap,
           and prints only an aggregate summary.
``sweep``  captures a month and writes the seed to local Silver.

    uv run python -m src.ingest.aerodatabox.international_cli plan 2026M05 --days 7
    uv run python -m src.ingest.aerodatabox.international_cli probe --date 2026-09-10 \
        --airports MEX,MTY --budget 20
    uv run python -m src.ingest.aerodatabox.international_cli sweep 2026M05 \
        --days 7 --budget 1624

Nothing here fits an estimator or publishes anything.  A flight count is not a
passenger, and the margins that would turn one into the other are AFAC's, not
this provider's; the gates that have to close before a count becomes a
published passenger figure are in
``docs/estimacion-pasajeros-ruta-aerolinea.md``.

Raw responses are provider content held in transient Bronze as a resume cache
and expire with the plan's retention.  They never enter Git.
"""

from __future__ import annotations

import argparse
from datetime import date, datetime
import json
from pathlib import Path
import sys

from src.analytics.route_carrier import load_city_crosswalk
from src.config import PATHS

# The sampling plan is the domestic command's and is deliberately shared rather
# than reimplemented: a sampled week has to be weighted the same way on both
# sides or the two seeds describe different months.
from src.ingest.aerodatabox.__main__ import day_weights, month_days
from src.ingest.aerodatabox.international import (
    WINDOWS_PER_DAY,
    mexican_airports,
    plan_units,
    pull_days,
    routes_by_operator,
    summarise,
)
from src.ingest.aerodatabox.flights import UNITS_PER_CALL


DEFAULT_BRONZE = PATHS.bronze / "aerodatabox_international"


def _airports(argument: str | None) -> list[str]:
    if argument:
        return [code.strip().upper() for code in argument.split(",") if code.strip()]
    return sorted(load_city_crosswalk())


def _print_plan(airports: list[str], days: list[date]) -> int:
    cost = plan_units(len(airports), len(days))
    print(
        f"{len(airports)} aeropuertos x {len(days)} dias x {WINDOWS_PER_DAY} ventanas "
        f"x {UNITS_PER_CALL} unidades = {cost:,} unidades"
    )
    print(f"aeropuertos: {', '.join(airports)}")
    print(f"dias: {', '.join(str(day) for day in days)}")
    return cost


def _report(stats, flights) -> None:
    print(
        f"llamadas {stats.calls} (cache {stats.cached_calls})  "
        f"unidades gastadas {stats.units_spent}"
    )
    print(
        f"salidas vistas {stats.departures_seen}  llegadas vistas {stats.arrivals_seen}  "
        f"tramos nacionales descartados {stats.domestic_legs_dropped}"
    )
    if stats.unmapped_operators:
        print(
            "operadores sin mapear (conservados con su identidad publicada): "
            f"{stats.unmapped_operators.most_common(10)}"
        )
    if stats.aeromexico_unsplit:
        print(
            f"vuelos AM sin modelo de aeronave: {stats.aeromexico_unsplit} "
            "(no se reparten entre Aerovias y Connect)"
        )
    if stats.empty_windows:
        print(f"ventanas vacias: {len(stats.empty_windows)}")
    if flights.empty:
        print("La fuente no devolvio tramos internacionales.", file=sys.stderr)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m src.ingest.aerodatabox.international_cli"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    plan_parser = sub.add_parser("plan", help="print the call plan and its cost")
    plan_parser.add_argument("period_id", help="month to plan, e.g. 2026M05")
    plan_parser.add_argument("--days", type=int, default=None)
    plan_parser.add_argument("--airports", default=None)

    probe_parser = sub.add_parser(
        "probe", help="buy the smallest capture that answers the feasibility question"
    )
    probe_parser.add_argument("--date", required=True, help="local date, YYYY-MM-DD")
    probe_parser.add_argument("--airports", default="MEX")
    probe_parser.add_argument(
        "--budget", type=int, required=True,
        help="hard cap on API units; the probe stops rather than exceed it",
    )
    probe_parser.add_argument("--bronze-dir", type=Path, default=DEFAULT_BRONZE)
    probe_parser.add_argument(
        "--summary-out", type=Path, default=None,
        help="write the aggregate summary as JSON (no provider records)",
    )
    probe_parser.add_argument("--dry-run", action="store_true")

    sweep_parser = sub.add_parser("sweep", help="capture a month into local Silver")
    sweep_parser.add_argument("period_id", help="month to capture, e.g. 2026M05")
    sweep_parser.add_argument("--days", type=int, default=None)
    sweep_parser.add_argument("--airports", default=None)
    sweep_parser.add_argument("--budget", type=int, default=None)
    sweep_parser.add_argument("--bronze-dir", type=Path, default=DEFAULT_BRONZE)
    sweep_parser.add_argument("--dry-run", action="store_true")

    args = parser.parse_args(argv)
    airports = _airports(getattr(args, "airports", None))

    if args.command == "plan":
        _print_plan(airports, month_days(args.period_id, args.days))
        return 0

    if args.command == "probe":
        day = datetime.strptime(args.date, "%Y-%m-%d").date()
        cost = _print_plan(airports, [day])
        if cost > args.budget:
            print(
                f"El plan cuesta {cost:,} unidades y el tope es {args.budget:,}. "
                "Reduce aeropuertos o sube el tope deliberadamente.",
                file=sys.stderr,
            )
            return 2
        if args.dry_run:
            return 0
        args.bronze_dir.mkdir(parents=True, exist_ok=True)
        flights, stats = pull_days(
            airports, [day], period_id=f"{day:%YM%m}",
            cache_dir=args.bronze_dir, unit_budget=args.budget,
        )
        _report(stats, flights)
        summary = summarise(flights, stats)
        summary["probe_date"] = str(day)
        summary["airports"] = airports
        summary["budget_units"] = args.budget
        print()
        print(json.dumps(summary, indent=2, ensure_ascii=False, sort_keys=True))
        if args.summary_out:
            args.summary_out.parent.mkdir(parents=True, exist_ok=True)
            args.summary_out.write_text(
                json.dumps(summary, indent=2, ensure_ascii=False, sort_keys=True)
            )
        return 0 if not flights.empty else 1

    days = month_days(args.period_id, args.days)
    cost = _print_plan(airports, days)
    if args.budget is not None and cost > args.budget:
        print(
            f"Aviso: el plan completo cuesta {cost:,} unidades y el tope es "
            f"{args.budget:,}; la captura se detendra al alcanzarlo.",
            file=sys.stderr,
        )
    if args.dry_run:
        return 0

    args.bronze_dir.mkdir(parents=True, exist_ok=True)
    weights = day_weights(args.period_id, days)
    if args.days:
        print(
            "ponderacion por dia de la semana: "
            + ", ".join(f"{d:%a}x{w:.2f}" for d, w in sorted(weights.items()))
        )
    flights, stats = pull_days(
        airports, days, period_id=args.period_id,
        cache_dir=args.bronze_dir, unit_budget=args.budget, day_weights=weights,
    )
    _report(stats, flights)
    if flights.empty:
        return 1

    out = PATHS.data / "silver"
    out.mkdir(parents=True, exist_ok=True)
    detail = out / f"aerodatabox_international_flights_{args.period_id}.parquet"
    seed = out / f"aerodatabox_international_seed_{args.period_id}.parquet"
    flights.to_parquet(detail)
    routes_by_operator(flights).to_parquet(seed)
    print(f"\n{len(flights):,} filas ruta x operador x modelo -> {detail}")
    print(f"{len(routes_by_operator(flights)):,} filas ruta x operador -> {seed}")
    print(
        "\nEsto es una semilla de frecuencias, no pasajeros. No ajusta ningun "
        "estimador ni publica nada."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
