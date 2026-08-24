"""Fact builders and business derivations for Stage 6."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import math
from typing import Any, Iterable
import warnings

import numpy as np
import pandas as pd
from statsmodels.tsa.seasonal import STL

from src.config import PATHS
from src.transform.stage6_dimensions import MILES_TO_KM


PARSER_VERSION = "stage6_v1.0.0"
POUNDS_TO_KG = 0.45359237
BMV_CONCEPTS = {
    "ifrs-full_Revenue": ("total_revenue", "pnl"),
    "ifrs-full_ProfitLossFromOperatingActivities": ("operating_income", "pnl"),
    "ifrs-full_ProfitLoss": ("net_income", "pnl"),
    "ifrs-full_Assets": ("total_assets", "balance"),
    "ifrs-full_Liabilities": ("total_liabilities", "balance"),
    "ifrs-full_Equity": ("total_equity", "balance"),
    "ifrs-full_CashAndCashEquivalents": ("cash_and_cash_equivalents", "balance"),
}
FACT_COLUMNS = [
    "carrier_key", "period_id", "calendar_period_id", "fiscal_period_id", "period_type",
    "period_start_date", "period_end_date", "metric_key", "segment", "value",
    "value_metric", "value_imperial", "value_as_reported", "unit_as_reported",
    "unit_normalized", "currency", "value_original_currency", "value_usd",
    "fx_rate_used", "fx_rate_type", "is_derived", "is_preliminary", "is_estimated",
    "derivation_formula", "valid_from", "valid_to", "is_current", "restatement_count",
    "source_system", "source_file", "source_hash", "ingested_at", "confidence",
]


def stable_hash(values: Iterable[Any]) -> str:
    payload = "|".join("" if pd.isna(value) else str(value) for value in values)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def stage_length_adjusted(value: float | None, stage_length_km: float | None) -> float | None:
    """Apply Aeroméxico's prospectus stage-length normalization."""

    if value is None or stage_length_km is None or pd.isna(value) or pd.isna(stage_length_km):
        return None
    if stage_length_km <= 0:
        raise ValueError("stage_length_km must be positive")
    return float(value) * math.sqrt(float(stage_length_km) / 1834.0)


def _period_ids(frame: pd.DataFrame) -> tuple[pd.Series, pd.Series]:
    calendar = frame["calendar_period_id"] if "calendar_period_id" in frame else frame["period_id"]
    fiscal = frame["fiscal_period_id"] if "fiscal_period_id" in frame else frame["period_id"]
    return calendar.fillna(frame["period_id"]), fiscal.fillna(frame["period_id"])


def _standard_source(frame: pd.DataFrame) -> pd.DataFrame:
    calendar, fiscal = _period_ids(frame)
    metric = frame["metric_key"]
    normalized = pd.to_numeric(frame["value_normalized"], errors="coerce")
    unit = frame["unit_normalized"].fillna("unknown")
    currency = pd.Series(np.where(unit.eq("usd"), "USD", None), index=frame.index, dtype="object")
    money = unit.eq("usd")
    value_metric = pd.Series(np.nan, index=frame.index, dtype=float)
    value_imperial = pd.Series(np.nan, index=frame.index, dtype=float)
    distance = metric.isin(["asm_total", "rpm_total"])
    per_mile = metric.isin(["casm", "casm_ex_fuel", "trasm", "prasm", "yield"])
    value_imperial.loc[distance | per_mile] = normalized.loc[distance | per_mile]
    value_metric.loc[distance] = normalized.loc[distance] * MILES_TO_KM
    value_metric.loc[per_mile] = normalized.loc[per_mile] / MILES_TO_KM
    ingested = pd.to_datetime(frame["ingested_at"], utc=True).dt.tz_convert(None)
    confidence = pd.to_numeric(frame.get("extraction_confidence", 1.0), errors="coerce").fillna(0.8)
    output = pd.DataFrame(
        {
            "carrier_key": frame["carrier_key"],
            "period_id": frame["period_id"],
            "calendar_period_id": calendar,
            "fiscal_period_id": fiscal,
            "period_type": frame["period_type"],
            "period_start_date": pd.to_datetime(frame["period_start_date"]).dt.date,
            "period_end_date": pd.to_datetime(frame["period_end_date"]).dt.date,
            "metric_key": metric,
            "segment": frame.get("segment", pd.Series("total", index=frame.index)).fillna("total"),
            "value": normalized,
            "value_metric": value_metric,
            "value_imperial": value_imperial,
            "value_as_reported": pd.to_numeric(frame["value_raw"], errors="coerce"),
            "unit_as_reported": frame["unit_raw"],
            "unit_normalized": unit,
            "currency": currency,
            "value_original_currency": normalized.where(money),
            "value_usd": normalized.where(money),
            "fx_rate_used": pd.Series(np.where(money, 1.0, np.nan), index=frame.index),
            "fx_rate_type": pd.Series(np.where(money, "average", None), index=frame.index),
            "is_derived": False,
            "is_preliminary": frame.get("is_preliminary", False).fillna(False),
            "is_estimated": False,
            "derivation_formula": None,
            "valid_from": ingested,
            "valid_to": pd.NaT,
            "is_current": True,
            "restatement_count": 0,
            "source_system": frame["source_system"],
            "source_file": frame["source_file"],
            "source_hash": frame["source_hash"],
            "ingested_at": ingested,
            "confidence": confidence,
        }
    )
    return output[FACT_COLUMNS]


def _package_order(value: str) -> tuple[int, int]:
    match = __import__("re").fullmatch(r"(\d{4})(?:Q([1-4]))?", str(value))
    return (int(match.group(1)), int(match.group(2) or 4)) if match else (0, 0)


def _fx_lookup() -> dict[tuple[str, str], float]:
    fx = pd.read_parquet(PATHS.gold / "dim_fx_period.parquet")
    output: dict[tuple[str, str], float] = {}
    for row in fx.itertuples(index=False):
        output[(str(row.period_id), "average")] = float(row.rate_avg)
        output[(str(row.period_id), "close")] = float(row.rate_close)
    return output


def _bmv_rows() -> pd.DataFrame:
    source = pd.read_parquet(PATHS.silver / "bmv_financials.parquet")
    source = source[
        source["concept"].isin(BMV_CONCEPTS)
        & source["is_consolidated"].fillna(False)
        & source["dimension_count"].eq(0)
        & source["period_type"].isin(["quarter", "year"])
    ].copy()
    source["metric_key"] = source["concept"].map(lambda value: BMV_CONCEPTS[value][0])
    source["statement_class"] = source["concept"].map(lambda value: BMV_CONCEPTS[value][1])
    pnl_valid = source["statement_class"].eq("pnl") & (
        (source["period_type"].eq("quarter") & ~source["is_ytd"].fillna(False))
        | (source["period_type"].eq("year") & source["is_ytd"].fillna(False))
    )
    balance_valid = source["statement_class"].eq("balance") & pd.to_datetime(source["period_start_date"]).eq(pd.to_datetime(source["period_end_date"]))
    source = source[pnl_valid | balance_valid].copy()
    source["package_order"] = source["package_period_id"].map(_package_order)
    source["currency_rank"] = source["currency"].map({"USD": 0, "MXN": 1}).fillna(2)
    dedupe = ["carrier_key", "package_period_id", "period_id", "metric_key"]
    source = source.sort_values(dedupe + ["currency_rank", "source_file"]).drop_duplicates(dedupe, keep="first")
    fx = _fx_lookup()
    rows: list[dict[str, Any]] = []
    for (carrier, period, metric), group in source.groupby(["carrier_key", "period_id", "metric_key"]):
        group = group.sort_values(["package_order", "source_file"])
        versions = []
        previous: tuple[float, str] | None = None
        for row in group.itertuples(index=False):
            signature = (float(row.value), str(row.currency))
            if signature == previous:
                versions[-1] = row
            else:
                versions.append(row)
            previous = signature
        for index, row in enumerate(versions):
            fx_type = "close" if row.statement_class == "balance" else "average"
            rate = 1.0 if row.currency == "USD" else fx.get((str(row.period_id), fx_type))
            value_usd = float(row.value) if row.currency == "USD" else (float(row.value) / rate if rate else np.nan)
            ingested = pd.to_datetime(row.ingested_at, utc=True).tz_convert(None)
            valid_to = pd.to_datetime(versions[index + 1].ingested_at, utc=True).tz_convert(None) - pd.Timedelta(microseconds=1) if index + 1 < len(versions) else pd.NaT
            rows.append(
                {
                    "carrier_key": carrier,
                    "period_id": period,
                    "calendar_period_id": period,
                    "fiscal_period_id": period,
                    "period_type": row.period_type,
                    "period_start_date": pd.to_datetime(row.period_start_date).date(),
                    "period_end_date": pd.to_datetime(row.period_end_date).date(),
                    "metric_key": metric,
                    "segment": "total",
                    "value": value_usd,
                    "value_metric": np.nan,
                    "value_imperial": np.nan,
                    "value_as_reported": float(row.value),
                    "unit_as_reported": row.unit,
                    "unit_normalized": "usd",
                    "currency": row.currency,
                    "value_original_currency": float(row.value),
                    "value_usd": value_usd,
                    "fx_rate_used": rate,
                    "fx_rate_type": fx_type,
                    "is_derived": bool(row.is_derived),
                    "is_preliminary": False,
                    "is_estimated": False,
                    "derivation_formula": row.derivation_formula,
                    "valid_from": ingested,
                    "valid_to": valid_to,
                    "is_current": index == len(versions) - 1,
                    "restatement_count": index,
                    "source_system": "bmv_xbrl",
                    "source_file": row.source_file,
                    "source_hash": row.source_hash,
                    "ingested_at": ingested,
                    "confidence": 1.0,
                }
            )
    return pd.DataFrame(rows, columns=FACT_COLUMNS)


def _afac_rows() -> tuple[pd.DataFrame, pd.DataFrame]:
    source = pd.read_parquet(PATHS.silver / "afac_monthly_stats.parquet")
    exceptions = source[source["carrier_key"].isna()].groupby(["source_system", "source_carrier_name"], dropna=False).agg(
        rows=("value", "size"), first_period=("period_id", "min"), last_period=("period_id", "max"), passengers=("value", "sum")
    ).reset_index()
    exceptions["reason"] = "Nombre fuera del alcance del crosswalk de entidades prioritarias; se conserva en silver y participa en el denominador de mercado."
    mapped = source.dropna(subset=["carrier_key"]).copy()
    dimensions = ["carrier_key", "period_id", "period_start_date", "period_end_date", "market"]
    aggregate = mapped.groupby(dimensions, as_index=False).agg(
        value=("value", "sum"),
        is_preliminary=("is_preliminary", "max"),
        is_estimated=("is_estimated", "max"),
        ingested_at=("ingested_at", "max"),
        source_hash=("source_hash", lambda values: stable_hash(sorted(set(values)))),
    )
    total = mapped.groupby(["carrier_key", "period_id", "period_start_date", "period_end_date"], as_index=False).agg(
        value=("value", "sum"),
        is_preliminary=("is_preliminary", "max"),
        is_estimated=("is_estimated", "max"),
        ingested_at=("ingested_at", "max"),
        source_hash=("source_hash", lambda values: stable_hash(sorted(set(values)))),
    )
    total["market"] = "total"
    aggregate = pd.concat([aggregate, total], ignore_index=True)
    market = source.groupby(["period_id", "period_start_date", "period_end_date", "market"], as_index=False).agg(
        value=("value", "sum"),
        is_preliminary=("is_preliminary", "max"),
        is_estimated=("is_estimated", "max"),
        ingested_at=("ingested_at", "max"),
        source_hash=("source_hash", lambda values: stable_hash(sorted(set(values)))),
    )
    market_total = source.groupby(["period_id", "period_start_date", "period_end_date"], as_index=False).agg(
        value=("value", "sum"),
        is_preliminary=("is_preliminary", "max"),
        is_estimated=("is_estimated", "max"),
        ingested_at=("ingested_at", "max"),
        source_hash=("source_hash", lambda values: stable_hash(sorted(set(values)))),
    )
    market_total["market"] = "total"
    market = pd.concat([market, market_total], ignore_index=True)
    market["carrier_key"] = "MARKET_TOTAL_MX"
    aggregate = pd.concat([aggregate, market[aggregate.columns]], ignore_index=True)
    ingested = pd.to_datetime(aggregate["ingested_at"], utc=True).dt.tz_convert(None)
    rows = pd.DataFrame(
        {
            "carrier_key": aggregate["carrier_key"],
            "period_id": aggregate["period_id"],
            "calendar_period_id": aggregate["period_id"],
            "fiscal_period_id": aggregate["period_id"],
            "period_type": "month",
            "period_start_date": pd.to_datetime(aggregate["period_start_date"]).dt.date,
            "period_end_date": pd.to_datetime(aggregate["period_end_date"]).dt.date,
            "metric_key": "passengers_afac",
            "segment": aggregate["market"],
            "value": aggregate["value"].astype(float),
            "value_metric": np.nan,
            "value_imperial": np.nan,
            "value_as_reported": aggregate["value"].astype(float),
            "unit_as_reported": "passengers",
            "unit_normalized": "count",
            "currency": None,
            "value_original_currency": np.nan,
            "value_usd": np.nan,
            "fx_rate_used": np.nan,
            "fx_rate_type": None,
            "is_derived": True,
            "is_preliminary": aggregate["is_preliminary"],
            "is_estimated": aggregate["is_estimated"],
            "derivation_formula": "SUM(AFAC passengers) across service_type for carrier, period and market",
            "valid_from": ingested,
            "valid_to": pd.NaT,
            "is_current": True,
            "restatement_count": 0,
            "source_system": "afac",
            "source_file": "silver/afac_monthly_stats.parquet",
            "source_hash": aggregate["source_hash"],
            "ingested_at": ingested,
            "confidence": 1.0,
        }
    )
    return rows[FACT_COLUMNS], exceptions


def _derived_row(template: pd.Series, metric_key: str, value: float | None, unit: str, formula: str, *, value_metric: float | None = None, value_imperial: float | None = None) -> dict[str, Any]:
    ingested = pd.to_datetime(template["ingested_at"])
    return {
        "carrier_key": template["carrier_key"], "period_id": template["period_id"],
        "calendar_period_id": template["calendar_period_id"], "fiscal_period_id": template["fiscal_period_id"],
        "period_type": template["period_type"], "period_start_date": template["period_start_date"],
        "period_end_date": template["period_end_date"], "metric_key": metric_key, "segment": "total",
        "value": np.nan if value is None or pd.isna(value) else float(value), "value_metric": value_metric, "value_imperial": value_imperial,
        "value_as_reported": np.nan, "unit_as_reported": None, "unit_normalized": unit,
        "currency": "USD" if unit.startswith("usd") else None,
        "value_original_currency": np.nan, "value_usd": np.nan, "fx_rate_used": np.nan,
        "fx_rate_type": None, "is_derived": True, "is_preliminary": False, "is_estimated": False,
        "derivation_formula": formula, "valid_from": ingested, "valid_to": pd.NaT, "is_current": True,
        "restatement_count": 0, "source_system": "derived_gold", "source_file": "fact_carrier_metrics inputs",
        "source_hash": template["source_hash"], "ingested_at": ingested, "confidence": float(template["confidence"]),
    }


@dataclass
class DerivationResult:
    rows: pd.DataFrame
    issues: pd.DataFrame


def _derive_metrics(base: pd.DataFrame) -> DerivationResult:
    current = base[base["is_current"] & base["period_type"].eq("quarter") & base["segment"].eq("total") & base["value"].notna()].copy()
    priority = {"sec_edgar": 0, "sec_filing": 0, "aeromexico_ir": 0, "viva_ir": 1, "peer_profile": 1, "bmv_xbrl": 5}
    current["priority"] = current["source_system"].map(priority).fillna(2)
    current = current.sort_values(["carrier_key", "period_id", "metric_key", "priority", "ingested_at"]).drop_duplicates(["carrier_key", "period_id", "metric_key"], keep="first")
    derived: list[dict[str, Any]] = []
    issues: list[dict[str, Any]] = []
    for (carrier, period), group in current.groupby(["carrier_key", "period_id"]):
        values = group.set_index("metric_key")["value"].to_dict()
        template = group.sort_values("ingested_at").iloc[-1].copy()
        template["source_hash"] = stable_hash(sorted(group["source_hash"].astype(str).unique()))
        template["confidence"] = group["confidence"].min()
        asm, rpm = values.get("asm_total"), values.get("rpm_total")
        revenue, passenger_revenue = values.get("total_revenue"), values.get("passenger_revenue")
        opex, fuel = values.get("operating_expenses_total"), values.get("jet_fuel_expense")
        passengers, fleet = values.get("passengers"), values.get("fleet_size")
        stage = values.get("average_stage_length")
        raw: dict[str, tuple[float, str, str]] = {}
        if asm and rpm is not None:
            raw["load_factor_derived"] = (rpm / asm, "fraction", "rpm_total / asm_total")
        if asm and revenue is not None:
            raw["rask_derived"] = (revenue / asm * 100 / MILES_TO_KM, "usd_cents_per_km", "total_revenue / (asm_total × 1.609344) × 100")
        if asm and passenger_revenue is not None:
            raw["prask_derived"] = (passenger_revenue / asm * 100 / MILES_TO_KM, "usd_cents_per_km", "passenger_revenue / (asm_total × 1.609344) × 100")
        if asm and opex is not None:
            raw["cask_derived"] = (opex / asm * 100 / MILES_TO_KM, "usd_cents_per_km", "operating_expenses_total / (asm_total × 1.609344) × 100")
        if asm and opex is not None and fuel is not None:
            raw["cask_ex_fuel_derived"] = ((opex - fuel) / asm * 100 / MILES_TO_KM, "usd_cents_per_km", "(operating_expenses_total - jet_fuel_expense) / (asm_total × 1.609344) × 100")
        if rpm and passenger_revenue is not None:
            raw["yield_derived"] = (passenger_revenue / rpm * 100 / MILES_TO_KM, "usd_cents_per_km", "passenger_revenue / (rpm_total × 1.609344) × 100")
        if opex and fuel is not None:
            raw["fuel_cost_share"] = (fuel / opex, "fraction", "jet_fuel_expense / operating_expenses_total")
        if passengers and revenue is not None:
            raw["revenue_per_passenger"] = (revenue / passengers, "usd_per_passenger", "total_revenue / passengers")
        if fleet and asm is not None:
            raw["asm_per_aircraft"] = (asm / fleet, "miles_per_aircraft", "asm_total / fleet_size")
        for key, (value, unit, formula) in raw.items():
            derived.append(_derived_row(template, key, value, unit, formula))

        preferred: dict[str, tuple[float, str]] = {}
        if values.get("trasm") is not None:
            preferred["rask"] = (values["trasm"] / MILES_TO_KM, "reported TRASM / 1.609344")
        elif "rask_derived" in raw:
            preferred["rask"] = (raw["rask_derived"][0], raw["rask_derived"][2])
        if values.get("prasm") is not None:
            preferred["prask"] = (values["prasm"] / MILES_TO_KM, "reported PRASM / 1.609344")
        elif "prask_derived" in raw:
            preferred["prask"] = (raw["prask_derived"][0], raw["prask_derived"][2])
        if values.get("casm") is not None:
            preferred["cask"] = (values["casm"] / MILES_TO_KM, "reported CASM / 1.609344")
        elif "cask_derived" in raw:
            preferred["cask"] = (raw["cask_derived"][0], raw["cask_derived"][2])
        if values.get("casm_ex_fuel") is not None:
            preferred["cask_ex_fuel"] = (values["casm_ex_fuel"] / MILES_TO_KM, "reported CASM ex fuel / 1.609344")
        elif "cask_ex_fuel_derived" in raw:
            preferred["cask_ex_fuel"] = (raw["cask_ex_fuel_derived"][0], raw["cask_ex_fuel_derived"][2])
        for key, (value, formula) in preferred.items():
            derived.append(_derived_row(template, key, value, "usd_cents_per_km", formula, value_metric=value))
        if "rask" in preferred and "cask" in preferred:
            margin = preferred["rask"][0] - preferred["cask"][0]
            derived.append(_derived_row(template, "unit_margin", margin, "usd_cents_per_km", "rask - cask", value_metric=margin))
            derived.append(_derived_row(template, "pask", margin, "usd_cents_per_km", "rask - cask", value_metric=margin))
        if "cask" in preferred:
            yield_value = values.get("yield")
            yield_km = yield_value / MILES_TO_KM if yield_value is not None else (raw.get("yield_derived") or (None,))[0]
            if yield_km:
                derived.append(_derived_row(template, "break_even_load_factor", preferred["cask"][0] / yield_km, "fraction", "cask / yield"))
        for key in ("rask", "cask"):
            if key in preferred:
                sla = stage_length_adjusted(preferred[key][0], stage)
                derived.append(_derived_row(template, f"sla_{key}", sla, "usd_cents_per_km", f"{key} × sqrt(average_stage_length / 1834); NULL when stage length is unavailable", value_metric=sla))

        comparisons = {
            "load_factor_total": (raw.get("load_factor_derived"), values.get("load_factor_total")),
            "trasm": (raw.get("rask_derived"), values.get("trasm") / MILES_TO_KM if values.get("trasm") is not None else None),
            "prasm": (raw.get("prask_derived"), values.get("prasm") / MILES_TO_KM if values.get("prasm") is not None else None),
            "casm": (raw.get("cask_derived"), values.get("casm") / MILES_TO_KM if values.get("casm") is not None else None),
            "casm_ex_fuel": (raw.get("cask_ex_fuel_derived"), values.get("casm_ex_fuel") / MILES_TO_KM if values.get("casm_ex_fuel") is not None else None),
            "yield": (raw.get("yield_derived"), values.get("yield") / MILES_TO_KM if values.get("yield") is not None else None),
        }
        for metric, (derived_tuple, reported) in comparisons.items():
            if derived_tuple is None or reported is None or reported == 0:
                continue
            derived_value = derived_tuple[0]
            difference = abs(derived_value - reported) / abs(reported)
            if difference > 0.01:
                detail = "La cifra reportada prevalece en vistas de negocio; la derivada se conserva para auditoría."
                issue_id = stable_hash(["reported_derived_discrepancy", carrier, period, metric])[:24]
                issues.append(dict(issue_id=issue_id, issue_type="reported_derived_discrepancy", severity="warning", source_system="derived_gold", carrier_key=carrier, period_id=period, metric_key=metric, observed_value=derived_value, expected_value=reported, difference_pct=difference, detail=detail, source_file="fact_carrier_metrics inputs", detected_at=template["ingested_at"]))
    derived_frame = pd.DataFrame(derived, columns=FACT_COLUMNS)
    return DerivationResult(derived_frame, pd.DataFrame(issues))


def _quarter_ordinal(period_id: str) -> int | None:
    match = __import__("re").fullmatch(r"(\d{4})Q([1-4])", str(period_id))
    return int(match.group(1)) * 4 + int(match.group(2)) - 1 if match else None


def _growth_and_ttm(base: pd.DataFrame) -> pd.DataFrame:
    selected = ["total_revenue", "adjusted_ebitdar", "operating_income", "net_income", "passengers", "asm_total", "rpm_total", "rask", "cask", "load_factor_total"]
    current = base[base["is_current"] & base["period_type"].eq("quarter") & base["segment"].eq("total") & base["metric_key"].isin(selected) & base["value"].notna()].copy()
    current["priority"] = current["source_system"].map({"sec_edgar": 0, "derived_gold": 0, "viva_ir": 1, "bmv_xbrl": 5}).fillna(2)
    current = current.sort_values(["carrier_key", "metric_key", "period_id", "priority"]).drop_duplicates(["carrier_key", "metric_key", "period_id"], keep="first")
    output: list[dict[str, Any]] = []
    additive = {"total_revenue", "adjusted_ebitdar", "operating_income", "net_income", "passengers", "asm_total", "rpm_total"}
    for (carrier, metric), group in current.groupby(["carrier_key", "metric_key"]):
        group = group.assign(ordinal=group["period_id"].map(_quarter_ordinal)).dropna(subset=["ordinal"]).sort_values("ordinal")
        lookup = {int(row.ordinal): row for row in group.itertuples(index=False)}
        for row in group.itertuples(index=False):
            template = pd.Series(row._asdict())
            ordinal = int(row.ordinal)
            for prefix, lag in (("qoq_growth", 1), ("yoy_growth", 4)):
                prior = lookup.get(ordinal - lag)
                if prior is not None and prior.value not in (None, 0) and not pd.isna(prior.value):
                    value = row.value / prior.value - 1
                    output.append(_derived_row(template, f"{prefix}_{metric}", value, "fraction", f"{metric}(t) / {metric}(t-{lag}) - 1"))
            if metric in additive:
                window = [lookup.get(ordinal - lag) for lag in range(4)]
                if all(item is not None for item in window):
                    value = sum(float(item.value) for item in window)
                    output.append(_derived_row(template, f"ttm_{metric}", value, row.unit_normalized, f"rolling sum of four quarters of {metric}"))
    return pd.DataFrame(output, columns=FACT_COLUMNS)


def _seasonally_adjusted(afac: pd.DataFrame) -> pd.DataFrame:
    series = afac[(afac["metric_key"] == "passengers_afac") & (afac["segment"] == "total") & (afac["carrier_key"].isin(["AEROMEXICO", "AEROMEXICO_CONNECT"]))].groupby("period_id", as_index=False).agg(value=("value", "sum"), ingested_at=("ingested_at", "max"), source_hash=("source_hash", lambda values: stable_hash(sorted(values))))
    series = series.sort_values("period_id")
    if len(series) < 24:
        return pd.DataFrame(columns=FACT_COLUMNS)
    adjusted = STL(series["value"].astype(float), period=12, robust=True).fit()
    series["adjusted"] = adjusted.trend + adjusted.resid
    rows = []
    for row in series.itertuples(index=False):
        year, month = int(row.period_id[:4]), int(row.period_id[-2:])
        start = pd.Timestamp(year=year, month=month, day=1)
        end = start + pd.offsets.MonthEnd(0)
        template = pd.Series(dict(carrier_key="AEROMEXICO", period_id=row.period_id, calendar_period_id=row.period_id, fiscal_period_id=row.period_id, period_type="month", period_start_date=start.date(), period_end_date=end.date(), source_hash=row.source_hash, ingested_at=row.ingested_at, confidence=1.0))
        rows.append(_derived_row(template, "passengers_afac_sa", row.adjusted, "count", "STL(period=12, robust=True); Aeroméxico + Aeroméxico Connect; observed - seasonal"))
    return pd.DataFrame(rows, columns=FACT_COLUMNS)


def build_fact_carrier_metrics() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    operating = _standard_source(pd.read_parquet(PATHS.silver / "sec_operating_metrics.parquet"))
    financial = _standard_source(pd.read_parquet(PATHS.silver / "sec_financials.parquet"))
    peers = _standard_source(pd.read_parquet(PATHS.silver / "peer_financials.parquet"))
    bmv = _bmv_rows()
    afac, exceptions = _afac_rows()
    base = pd.concat([operating, financial, peers, bmv, afac], ignore_index=True)
    derivation = _derive_metrics(base)
    # All-NA lineage/conversion columns are intentional for non-monetary metrics.
    # Pandera coerces the declared types immediately after this build.
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", category=FutureWarning, message="The behavior of DataFrame concatenation with empty or all-NA entries is deprecated.*")
        combined = pd.concat([base, derivation.rows], ignore_index=True)
        growth = _growth_and_ttm(combined)
        seasonal = _seasonally_adjusted(afac)
        output = pd.concat([combined, growth, seasonal], ignore_index=True)
    output = output.sort_values(["carrier_key", "period_id", "metric_key", "segment", "source_system", "valid_from"]).reset_index(drop=True)
    issue_columns = ["issue_id", "issue_type", "severity", "source_system", "carrier_key", "period_id", "calendar_period_id", "fiscal_period_id", "metric_key", "observed_value", "expected_value", "difference_pct", "detail", "source_file", "detected_at"]
    issues = derivation.issues.copy()
    issues["calendar_period_id"] = issues["period_id"]
    issues["fiscal_period_id"] = issues["period_id"]
    issues = issues.reindex(columns=issue_columns)
    return output[FACT_COLUMNS], issues, exceptions


def build_fact_route_traffic() -> pd.DataFrame:
    source = pd.read_parquet(PATHS.silver / "bts_t100_segment.parquet")
    source["route_key"] = source["origin"] + "-" + source["dest"]
    source["period_id"] = source.apply(lambda row: f"{int(row.year)}M{int(row.month):02d}", axis=1)
    keys = ["carrier_key", "route_key", "period_id", "aircraft_type", "class"]
    output = source.groupby(keys, as_index=False).agg(
        departures_scheduled=("departures_scheduled", "sum"), departures_performed=("departures_performed", "sum"),
        seats=("seats", "sum"), passengers=("passengers", "sum"), freight=("freight", "sum"), mail=("mail", "sum"),
        asm_miles=("asm_miles", "sum"), rpm_miles=("rpm_miles", "sum"), distance_miles=("distance", "median"),
        source_hash=("source_hash", lambda values: stable_hash(sorted(set(values)))), ingested_at=("ingested_at", "max"),
    )
    output["service_class"] = output.pop("class")
    output["calendar_period_id"] = output["period_id"]
    output["fiscal_period_id"] = output["period_id"]
    output["freight_kg"] = output.pop("freight") * POUNDS_TO_KG
    output["mail_kg"] = output.pop("mail") * POUNDS_TO_KG
    output["ask_km"] = output["asm_miles"] * MILES_TO_KM
    output["rpk_km"] = output["rpm_miles"] * MILES_TO_KM
    output["load_factor"] = output["rpm_miles"].div(output["asm_miles"].replace(0, np.nan))
    output["distance_km"] = output["distance_miles"] * MILES_TO_KM
    output["source_system"] = "bts_t100"
    output["source_file"] = "silver/bts_t100_segment.parquet"
    columns = ["carrier_key", "route_key", "period_id", "calendar_period_id", "fiscal_period_id", "aircraft_type", "service_class", "departures_scheduled", "departures_performed", "seats", "passengers", "freight_kg", "mail_kg", "asm_miles", "ask_km", "rpm_miles", "rpk_km", "load_factor", "distance_miles", "distance_km", "source_system", "source_file", "source_hash", "ingested_at"]
    return output[columns].sort_values(keys[:-1] + ["service_class"]).reset_index(drop=True)


def build_fact_airport_traffic() -> pd.DataFrame:
    source = pd.read_parquet(PATHS.silver / "airport_traffic.parquet")
    output = source.rename(columns={"source": "source_system"}) if "source_system" not in source else source.copy()
    output["source_system"] = source["source_system"]
    output["calendar_period_id"] = output["period_id"]
    output["fiscal_period_id"] = output["period_id"]
    columns = ["airport_iata", "period_id", "calendar_period_id", "fiscal_period_id", "passengers_domestic", "passengers_international", "passengers_total", "cargo_tons", "operations", "operator_group", "country", "is_group_total", "source_system", "source_file", "source_hash", "ingested_at"]
    return output[columns].sort_values(["period_id", "operator_group", "airport_iata"]).reset_index(drop=True)


def build_fact_market_data() -> pd.DataFrame:
    source = pd.read_parquet(PATHS.silver / "market_prices.parquet").sort_values(["carrier_key", "date"]).copy()
    source["return_1d"] = source.groupby("carrier_key")["adj_close"].pct_change(fill_method=None)
    source["year"] = pd.to_datetime(source["date"]).dt.year
    first = source.groupby(["carrier_key", "year"])["adj_close"].transform("first")
    source["return_ytd"] = source["adj_close"] / first - 1
    source["volatility_30d"] = source.groupby("carrier_key")["return_1d"].transform(lambda values: values.rolling(30, min_periods=20).std() * np.sqrt(252))
    source["calendar_period_id"] = pd.to_datetime(source["date"]).dt.strftime("%Y-%m-%d")
    source["fiscal_period_id"] = source["calendar_period_id"]
    columns = ["carrier_key", "ticker", "date", "calendar_period_id", "fiscal_period_id", "close", "adj_close", "volume", "currency", "return_1d", "return_ytd", "volatility_30d", "source_system", "source_file", "source_hash", "ingested_at"]
    return source[columns].reset_index(drop=True)


def build_fact_macro() -> pd.DataFrame:
    source = pd.read_parquet(PATHS.silver / "macro_indicators.parquet").copy()
    fuel = pd.read_parquet(PATHS.silver / "fuel_prices.parquet").rename(columns={"price_usd_per_gallon": "value"})
    fuel["indicator_key"] = "jet_fuel_usd_per_gallon"
    fuel["source_system"] = "eia"
    source = pd.concat([source, fuel[source.columns]], ignore_index=True)
    source["date"] = pd.to_datetime(source["date"])
    rows = []
    units = {"usd_mxn_fix": "mxn_per_usd", "jet_fuel_usd_per_gallon": "usd_per_gallon"}
    for period_type, period_values in (("month", source["date"].dt.to_period("M")), ("quarter", source["date"].dt.to_period("Q"))):
        work = source.assign(_period=period_values)
        for (period, indicator), group in work.groupby(["_period", "indicator_key"]):
            period_id = f"{period.year}M{period.month:02d}" if period_type == "month" else f"{period.year}Q{period.quarter}"
            lineage_hash = stable_hash(sorted(set(group["source_hash"].astype(str))))
            common = dict(period_id=period_id, period_type=period_type, indicator_key=indicator, unit=units.get(indicator, "index"), source_system=str(group["source_system"].iloc[-1]), source_file="silver/macro_indicators.parquet" if indicator != "jet_fuel_usd_per_gallon" else "silver/fuel_prices.parquet", source_hash=lineage_hash, ingested_at=pd.to_datetime(group["ingested_at"], utc=True).max().tz_convert(None))
            rows.append({**common, "value": float(group["value"].mean()), "aggregation": "average"})
            rows.append({**common, "value": float(group.sort_values("date")["value"].iloc[-1]), "aggregation": "close"})
    output = pd.DataFrame(rows)
    output["calendar_period_id"] = output["period_id"]
    output["fiscal_period_id"] = output["period_id"]
    columns = ["period_id", "period_type", "calendar_period_id", "fiscal_period_id", "indicator_key", "value", "unit", "aggregation", "source_system", "source_file", "source_hash", "ingested_at"]
    return output[columns].sort_values(["period_id", "indicator_key", "aggregation"]).reset_index(drop=True)
