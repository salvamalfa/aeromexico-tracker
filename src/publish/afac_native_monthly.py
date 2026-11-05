"""Project only the AFAC monthly passenger subtree from reconciled native cells."""

import math
from calendar import monthrange
from copy import deepcopy
from datetime import datetime

NOTE = (
    "Serie AFAC por empresa: suma calculada de Aerovías de México y Aeroméxico Connect, "
    "servicio regular y de fletamento. La corrección de lectura de 2019–2025 usa los originales "
    "y sus totales mexicanos reconciliados; no representa un cambio del método de AFAC. "
    "Se conserva por separado la serie de la empresa y la inelegibilidad histórica al corte. "
    "No crea indicadores financieros ni un trimestre incompleto."
)


def project_monthly_series(before, cells, sources):
    """Return a full quarters document; only monthly_passengers may differ.

    cells is exactly market_cells' dictionary: AM already includes Connect.
    Keep each unchanged existing record byte for byte, including provenance.
    Years before 2019 are retained, without newly certifying their contents.
    """
    if not sources or min(sources) != 2019 or set(sources) != set(range(2019, max(sources) + 1)):
        raise ValueError("AFAC monthly projection requires the complete native annual series from 2019")
    last_year = max(sources)
    if any(source["through"] != 12 for year, source in sources.items() if year < last_year):
        raise ValueError("Historical AFAC monthly projection requires complete annual coverage")
    result = deepcopy(before)
    series = result["monthly_passengers"]
    records = series["records"]
    if not records or len({row["period_id"] for row in records}) != len(records):
        raise ValueError("AFAC baseline monthly series is empty or duplicated")
    existing = {row["period_id"]: row for row in records}
    periods = [
        f"{year}M{month:02d}"
        for year, source in sorted(sources.items())
        for month in range(1, source["through"] + 1)
    ]
    if periods[-1] < records[-1]["period_id"]:
        raise ValueError("An older AFAC annual edition cannot remove later monthly passengers")
    retained = [row for row in records if row["period_id"] < "2019M01"]
    updated = []
    for period in periods:
        source = sources[int(period[:4])]
        values = {
            segment: cells.get(("AEROMEXICO", period, segment))
            for segment in ("domestic", "international", "total")
        }
        if any(value is None or not math.isfinite(value) or value < 0 for value in values.values()):
            raise ValueError("AFAC monthly native group observation is missing or invalid")
        if values["total"] != values["domestic"] + values["international"]:
            raise ValueError("AFAC monthly native group segments do not reconcile")
        prior = existing.get(period)
        if prior and all(
            prior[key] == value
            for key, value in {
                "domestic": values["domestic"],
                "international": values["international"],
                "reported_total": values["total"],
                "total_segment_sum": values["total"],
                "reconciliation_delta": 0.0,
            }.items()
        ):
            updated.append(prior)
            continue
        updated.append(
            dict(
                period_id=period,
                date=period.replace("M", "-") + "-01",
                period_type="month",
                domestic=values["domestic"],
                international=values["international"],
                total_segment_sum=values["total"],
                reported_total=values["total"],
                reconciliation_delta=0.0,
                source_id=f"afac-native-annual-{period[:4]}M{source['through']:02d}",
                source_hash=source["sha256"],
                cutoff_date=None,
                agent_eligible=False,
                availability="reported_operator_cells_group_sum",
            )
        )
    series["records"] = [*retained, *updated]
    first, last = series["records"][0]["period_id"], periods[-1]
    calendar_months = (int(last[:4]) - int(first[:4])) * 12 + int(last[-2:]) - int(first[-2:]) + 1
    if len(series["records"]) != calendar_months:
        raise ValueError("AFAC monthly projection cannot bridge an unobserved month")
    # Capture metadata comes from the latest source, never from the replay date.
    captured = sources[last_year]["downloaded_at"]
    if datetime.fromisoformat(captured).tzinfo is None:
        raise ValueError("AFAC monthly source capture requires its timezone")
    series.update(
        period_end=f"{last_year}-{int(last[-2:]):02d}-{monthrange(last_year, int(last[-2:]))[1]}",
        observed_months=len(series["records"]),
        calendar_months=calendar_months,
        as_of=captured,
        eligibility_reason=NOTE,
    )
    return result
