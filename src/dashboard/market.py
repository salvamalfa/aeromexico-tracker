"""Market card payload: AFAC passenger share of the Mexican carriers.

Denominator: the passengers AFAC reports for every Mexican carrier (regular
and charter service), summed per month and segment. It is the universe the
dashboard calls *Industria*'s market; foreign carriers on international
routes are outside it because AFAC only publishes them as an aggregate, and
the fase-0 report documents that difference
(docs/etapas/dashboard-v2-fase0-datos-20260928.md).

A carrier row AFAC does not publish for a month is missing, not zero: that
carrier's share and the industry total are ``None`` for that month.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

import duckdb

from src.config import PATHS
from src.dashboard.entities import CARRIER_ENTITIES, INDUSTRY


SCHEMA_VERSION = "market_payload_v1"
# Enough history for the pre-pandemic baseline and every year-over-year
# comparison the card shows, without shipping 2015–2018 to the browser.
FIRST_MONTH = "2019M01"
SEGMENTS = ("total", "domestic", "international")
MONTHS_ES = ("ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic")

MONTHLY_QUERY = """
SELECT carrier_key, period_id, segment, value
FROM v_carrier_default
WHERE metric_key = 'passengers_afac'
  AND period_type = 'month'
  AND segment IN ('total', 'domestic', 'international')
  AND carrier_key <> 'MARKET_TOTAL_MX'
  AND value IS NOT NULL
  AND period_id >= ?
ORDER BY period_id, segment, carrier_key
"""


def _month_label(period_id: str) -> str:
    return f"{MONTHS_ES[int(period_id[5:7]) - 1]} {period_id[2:4]}"


def _quarter_of(period_id: str) -> str:
    return f"{period_id[:4]}Q{(int(period_id[5:7]) - 1) // 3 + 1}"


def _quarter_label(period_id: str) -> str:
    return f"{period_id[-1]}T{period_id[2:4]}"


def _previous_quarter(period_id: str) -> str:
    year, quarter = int(period_id[:4]), int(period_id[-1])
    return f"{year - 1}Q4" if quarter == 1 else f"{year}Q{quarter - 1}"


def _previous_year(period_id: str) -> str:
    return f"{int(period_id[:4]) - 1}{period_id[4:]}"


def _segment_block(values: dict[str, float], denominator: float) -> dict[str, Any]:
    carriers: dict[str, Any] = {}
    for entity in CARRIER_ENTITIES:
        passengers = values.get(entity.key)
        carriers[entity.key] = {
            "passengers": passengers,
            "share": None if passengers is None or denominator <= 0 else passengers / denominator,
        }
    members = [values.get(key) for key in INDUSTRY.carriers]
    industry = None if any(value is None for value in members) else float(sum(members))
    return {
        "mexican_carriers_passengers": denominator,
        "carriers": carriers,
        "industry": {
            "passengers": industry,
            "share": None if industry is None or denominator <= 0 else industry / denominator,
        },
    }


def _change_pp(current: float | None, previous: float | None) -> float | None:
    if current is None or previous is None:
        return None
    return (current - previous) * 100


def build_market_payload(database_path: str | None = None) -> dict[str, Any]:
    path = str(PATHS.warehouse if database_path is None else database_path)
    with duckdb.connect(path, read_only=True) as connection:
        frame = connection.execute(MONTHLY_QUERY, [FIRST_MONTH]).df()
        as_of = connection.execute(
            "SELECT MAX(CAST(downloaded_at AS DATE)) FROM dim_source_artifact WHERE source_system = 'afac'"
        ).fetchone()[0]
    if frame.empty:
        raise ValueError("AFAC carrier passengers are missing from v_carrier_default")
    if (frame["value"] < 0).any():
        raise ValueError("AFAC carrier passengers contain a negative value")

    # (period, segment) -> carrier -> passengers
    cells: dict[tuple[str, str], dict[str, float]] = defaultdict(dict)
    for row in frame.itertuples(index=False):
        cells[(str(row.period_id), str(row.segment))][str(row.carrier_key)] = float(row.value)

    months = sorted({period for period, _ in cells})
    month_rows = []
    for period_id in months:
        segments = {}
        for segment in SEGMENTS:
            values = cells.get((period_id, segment), {})
            segments[segment] = _segment_block(values, float(sum(values.values())))
        month_rows.append({"period_id": period_id, "period_label": _month_label(period_id), "segments": segments})

    # Quarters only from complete three-month windows; a carrier missing in
    # any month of the quarter stays missing for that quarter.
    by_quarter: dict[str, list[str]] = defaultdict(list)
    for period_id in months:
        by_quarter[_quarter_of(period_id)].append(period_id)
    quarter_blocks: dict[str, dict[str, Any]] = {}
    for quarter_id, quarter_months in sorted(by_quarter.items()):
        if len(quarter_months) != 3:
            continue
        segments = {}
        for segment in SEGMENTS:
            totals: dict[str, float] = {}
            carriers_present = set.intersection(
                *(set(cells.get((month, segment), {})) for month in quarter_months)
            )
            all_carriers = set().union(*(set(cells.get((month, segment), {})) for month in quarter_months))
            for carrier in all_carriers:
                if carrier in carriers_present:
                    totals[carrier] = sum(cells[(month, segment)][carrier] for month in quarter_months)
            denominator = float(
                sum(sum(cells.get((month, segment), {}).values()) for month in quarter_months)
            )
            segments[segment] = _segment_block(totals, denominator)
        quarter_blocks[quarter_id] = {
            "period_id": quarter_id,
            "period_label": _quarter_label(quarter_id),
            "segments": segments,
        }
    for quarter_id, block in quarter_blocks.items():
        prior = quarter_blocks.get(_previous_quarter(quarter_id))
        prior_year = quarter_blocks.get(_previous_year(quarter_id))
        for segment, current in block["segments"].items():
            for key, item in [*current["carriers"].items(), (INDUSTRY.key, current["industry"])]:
                def previous_share(reference: dict[str, Any] | None) -> float | None:
                    if reference is None:
                        return None
                    seg = reference["segments"][segment]
                    return (seg["industry"] if key == INDUSTRY.key else seg["carriers"][key])["share"]

                item["share_change_qoq_pp"] = _change_pp(item["share"], previous_share(prior))
                item["share_change_yoy_pp"] = _change_pp(item["share"], previous_share(prior_year))

    quarters = list(quarter_blocks.values())
    latest = quarters[-1]
    industry_share = latest["segments"]["total"]["industry"]["share"]
    note = (
        f"Industria = Aeroméxico, Volaris y Viva · {industry_share:.0%} de los pasajeros "
        f"de aerolíneas mexicanas en {latest['period_label']} (AFAC)."
        if industry_share is not None
        else "Industria = Aeroméxico, Volaris y Viva."
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "metadata": {
            "source": "AFAC · pasajeros por aerolínea (servicio regular y de fletamento)",
            "denominator": "Pasajeros de todas las aerolíneas mexicanas que publica AFAC",
            "first_period": months[0],
            "last_period": months[-1],
            "default_quarter": latest["period_id"],
            "data_as_of": None if as_of is None else str(as_of),
            "industry_note": note,
            "industry_share_latest": industry_share,
            "method_note": (
                "La participación divide los pasajeros de cada aerolínea entre los de todas "
                "las aerolíneas mexicanas del mismo mes y segmento. Aeroméxico incluye a "
                "Aeroméxico Connect. Las aerolíneas extranjeras quedan fuera porque AFAC "
                "no las publica por aerolínea."
            ),
        },
        "carriers": [entity.key for entity in CARRIER_ENTITIES],
        "months": month_rows,
        "quarters": quarters,
    }
