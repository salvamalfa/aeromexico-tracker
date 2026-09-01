"""Dimension builders for the Stage 6 business model."""

from __future__ import annotations

from datetime import date, timedelta
import hashlib
import re
from typing import Any

import numpy as np
import pandas as pd

from src.config import PATHS


MILES_TO_KM = 1.609344

CURATED_CARRIERS: dict[str, dict[str, Any]] = {
    "MARKET_TOTAL_MX": dict(carrier_name="Mercado aéreo mexicano AFAC", carrier_name_short="Mercado México", iata_code=None, icao_code=None, country="Mexico", business_model="market_aggregate", is_public=False, ticker=None, exchange=None, cik=None, reporting_standard=None, reporting_currency=None, unit_system="metric", fiscal_year_end_month=None, parent_carrier_key=None, is_peer=False, is_focus=False),
    "AEROMEXICO": dict(carrier_name="Grupo Aeroméxico S.A.B. de C.V.", carrier_name_short="Aeroméxico", iata_code="AM", icao_code="AMX", country="Mexico", business_model="network", is_public=True, ticker="AERO", exchange="NYSE + BMV", cik="1561861", reporting_standard="IFRS", reporting_currency="USD", unit_system="imperial", fiscal_year_end_month=12, parent_carrier_key=None, is_peer=False, is_focus=True),
    "AEROMEXICO_CONNECT": dict(carrier_name="Aerolitoral S.A. de C.V.", carrier_name_short="Aeroméxico Connect", iata_code="5D", icao_code="SLI", country="Mexico", business_model="regional", is_public=False, ticker=None, exchange=None, cik=None, reporting_standard="IFRS", reporting_currency="USD", unit_system="imperial", fiscal_year_end_month=12, parent_carrier_key="AEROMEXICO", is_peer=False, is_focus=False),
    "VOLARIS": dict(carrier_name="Controladora Vuela Compañía de Aviación, S.A.B. de C.V.", carrier_name_short="Volaris", iata_code="Y4", icao_code="VOI", country="Mexico", business_model="ulcc", is_public=True, ticker="VLRS", exchange="NYSE + BMV", cik="1520504", reporting_standard="IFRS", reporting_currency="USD", unit_system="imperial", fiscal_year_end_month=12, parent_carrier_key=None, is_peer=True, is_focus=False),
    "VIVA_AEROBUS": dict(carrier_name="Aeroenlaces Nacionales, S.A. de C.V.", carrier_name_short="Viva Aerobus", iata_code="VB", icao_code="VIV", country="Mexico", business_model="ulcc", is_public=False, ticker=None, exchange=None, cik=None, reporting_standard="IFRS", reporting_currency="USD", unit_system="imperial", fiscal_year_end_month=12, parent_carrier_key=None, is_peer=True, is_focus=False),
    "RYANAIR": dict(carrier_name="Ryanair Holdings plc", carrier_name_short="Ryanair", iata_code="FR", icao_code="RYR", country="Ireland", business_model="ulcc", is_public=True, ticker="RYAAY", exchange="NASDAQ", cik="1038683", reporting_standard="IFRS", reporting_currency="EUR", unit_system="metric", fiscal_year_end_month=3, parent_carrier_key=None, is_peer=True, is_focus=False),
    "DELTA": dict(carrier_name="Delta Air Lines, Inc.", carrier_name_short="Delta", iata_code="DL", icao_code="DAL", country="United States", business_model="network", is_public=True, ticker="DAL", exchange="NYSE", cik="27904", reporting_standard="US-GAAP", reporting_currency="USD", unit_system="imperial", fiscal_year_end_month=12, parent_carrier_key=None, is_peer=True, is_focus=False),
    "IAG": dict(carrier_name="International Consolidated Airlines Group, S.A.", carrier_name_short="IAG", iata_code=None, icao_code=None, country="Spain / United Kingdom", business_model="group", is_public=True, ticker="ICAGY", exchange="OTC", cik=None, reporting_standard="IFRS", reporting_currency="EUR", unit_system="metric", fiscal_year_end_month=12, parent_carrier_key=None, is_peer=False, is_focus=False),
}

GLOSSARY_MAP: dict[str, dict[str, Any]] = {
    "asm_total": dict(section="ASK / ASM", es="ASM — asientos-milla disponibles", en="Available Seat Miles", category="capacity", unit="miles", better=None, fmt="0,0"),
    "rpm_total": dict(section="RPK / RPM", es="RPM — pasajeros-milla de pago", en="Revenue Passenger Miles", category="demand", unit="miles", better=True, fmt="0,0"),
    "load_factor_total": dict(section="Load Factor", es="Factor de ocupación", en="Load Factor", category="demand", unit="fraction", better=None, fmt="0.0%"),
    "load_factor_derived": dict(section="Load Factor", es="Factor de ocupación derivado", en="Derived Load Factor", category="demand", unit="fraction", better=None, fmt="0.0%"),
    "passengers": dict(section="Passengers", es="Pasajeros transportados", en="Passengers", category="demand", unit="count", better=True, fmt="0,0"),
    "passengers_afac": dict(section="Passengers", es="Pasajeros AFAC", en="AFAC Passengers", category="demand", unit="count", better=True, fmt="0,0"),
    "passengers_afac_sa": dict(section="Passengers", es="Pasajeros AFAC desestacionalizados", en="Seasonally Adjusted AFAC Passengers", category="demand", unit="count", better=True, fmt="0,0"),
    "average_stage_length": dict(section="Average Stage Length", es="Etapa promedio", en="Average Stage Length", category="operational", unit="kilometers", better=None, fmt="0,0"),
    "rask": dict(section="RASK / RASM", es="RASK", en="Revenue per ASK", category="unit_revenue", unit="usd_cents_per_km", better=True, fmt="$0.00"),
    "sla_rask": dict(section="RASK / RASM", es="RASK ajustado por etapa", en="Stage-length-adjusted RASK", category="unit_revenue", unit="usd_cents_per_km", better=True, fmt="$0.00"),
    "trasm": dict(section="TRASM", es="TRASM", en="Total Revenue per ASM", category="unit_revenue", unit="usd_cents", better=True, fmt="$0.00"),
    "prasm": dict(section="PRASM", es="PRASM", en="Passenger Revenue per ASM", category="unit_revenue", unit="usd_cents", better=True, fmt="$0.00"),
    "prask": dict(section="PRASM", es="PRASK", en="Passenger Revenue per ASK", category="unit_revenue", unit="usd_cents_per_km", better=True, fmt="$0.00"),
    "yield": dict(section="Yield", es="Yield", en="Yield", category="unit_revenue", unit="usd_cents", better=True, fmt="$0.00"),
    "yield_derived": dict(section="Yield", es="Yield derivado", en="Derived Yield", category="unit_revenue", unit="usd_cents_per_km", better=True, fmt="$0.00"),
    "casm": dict(section="CASK / CASM", es="CASM", en="Cost per ASM", category="unit_cost", unit="usd_cents", better=False, fmt="$0.00"),
    "cask": dict(section="CASK / CASM", es="CASK", en="Cost per ASK", category="unit_cost", unit="usd_cents_per_km", better=False, fmt="$0.00"),
    "sla_cask": dict(section="CASK / CASM", es="CASK ajustado por etapa", en="Stage-length-adjusted CASK", category="unit_cost", unit="usd_cents_per_km", better=False, fmt="$0.00"),
    "casm_ex_fuel": dict(section="CASK ex-fuel / CASM ex-fuel", es="CASM ex combustible", en="CASM ex fuel", category="unit_cost", unit="usd_cents", better=False, fmt="$0.00"),
    "cask_ex_fuel": dict(section="CASK ex-fuel / CASM ex-fuel", es="CASK ex combustible", en="CASK ex fuel", category="unit_cost", unit="usd_cents_per_km", better=False, fmt="$0.00"),
    "unit_margin": dict(section="Spread RASK", es="Margen unitario", en="Unit Margin", category="profitability", unit="usd_cents_per_km", better=True, fmt="$0.00"),
    "pask": dict(section="Spread RASK", es="PASK", en="Profit per ASK", category="profitability", unit="usd_cents_per_km", better=True, fmt="$0.00"),
    "break_even_load_factor": dict(section="Break-even Load Factor", es="Factor de ocupación de equilibrio", en="Break-even Load Factor", category="profitability", unit="fraction", better=False, fmt="0.0%"),
    "adjusted_ebitdar": dict(section="EBITDAR ajustado", es="EBITDAR ajustado", en="Adjusted EBITDAR", category="profitability", unit="usd", better=True, fmt="$0,0"),
    "operating_margin": dict(section="Margen operativo", es="Margen operativo", en="Operating Margin", category="profitability", unit="fraction", better=True, fmt="0.0%"),
    "ancillary_share": dict(section="Ancillary Revenue Share", es="Participación de ingresos auxiliares", en="Ancillary Revenue Share", category="financial", unit="fraction", better=True, fmt="0.0%"),
    "fleet_size": dict(section="Fleet Size", es="Flota", en="Fleet Size", category="operational", unit="count", better=None, fmt="0,0"),
    "aircraft_utilization": dict(section="Aircraft Utilization", es="Utilización de flota", en="Aircraft Utilization", category="operational", unit="hours_per_day", better=True, fmt="0.0"),
    "asm_per_aircraft": dict(section="ASM per Aircraft", es="ASM por aeronave", en="ASM per Aircraft", category="operational", unit="miles_per_aircraft", better=True, fmt="0,0"),
    "on_time_departure_pct": dict(section="OTP", es="Puntualidad", en="On-Time Performance", category="operational", unit="fraction", better=True, fmt="0.0%"),
    "market_share_domestic_mx": dict(section="Market Share doméstico", es="Participación doméstica en México", en="Mexico Domestic Market Share", category="market", unit="fraction", better=None, fmt="0.0%"),
    "route_hhi": dict(section="HHI", es="HHI de red", en="Route Network HHI", category="market", unit="index", better=None, fmt="0.000"),
    "fuel_cost_share": dict(section="Fuel Cost Share", es="Participación del combustible en costos", en="Fuel Cost Share", category="unit_cost", unit="fraction", better=False, fmt="0.0%"),
    "jet_fuel_elasticity": dict(section="Elasticidad al jet fuel", es="Elasticidad al jet fuel", en="Jet Fuel Elasticity", category="unit_cost", unit="ratio", better=False, fmt="0.00"),
}

SPANISH_FALLBACK_LABELS = {
    "total_revenue": "Ingreso total",
    "operating_income": "Utilidad operativa",
    "net_income": "Utilidad neta",
    "jet_fuel_expense": "Gasto de combustible",
    "wages_salaries_benefits": "Sueldos, salarios y prestaciones",
    "maintenance_expense": "Gasto de mantenimiento",
    "aircraft_leasing_expense": "Arrendamiento de aeronaves",
    "selling_administrative_expense": "Gastos de venta y administración",
    "cash_and_cash_equivalents": "Efectivo y equivalentes",
    "total_assets": "Activos totales",
    "total_liabilities": "Pasivos totales",
    "total_equity": "Capital contable",
    "ebitdar_margin": "Margen EBITDAR ajustado",
}

FALLBACK_USD_METRICS = {
    "total_revenue", "operating_income", "net_income", "jet_fuel_expense",
    "wages_salaries_benefits", "maintenance_expense", "aircraft_leasing_expense",
    "selling_administrative_expense", "cash_and_cash_equivalents", "total_assets",
    "total_liabilities", "total_equity",
}
FALLBACK_HIGHER_IS_BETTER = {
    "total_revenue": True,
    "operating_income": True,
    "net_income": True,
    "jet_fuel_expense": False,
    "wages_salaries_benefits": False,
    "maintenance_expense": False,
    "aircraft_leasing_expense": False,
    "selling_administrative_expense": False,
    "cash_and_cash_equivalents": True,
    "total_assets": None,
    "total_liabilities": False,
    "total_equity": True,
    "ebitdar_margin": True,
}


def gregorian_easter(year: int) -> date:
    """Meeus/Jones/Butcher Gregorian Easter algorithm."""

    a = year % 19
    b, c = divmod(year, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    ell = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * ell) // 451
    month = (h + ell - 7 * m + 114) // 31
    day = (h + ell - 7 * m + 114) % 31 + 1
    return date(year, month, day)


def build_dim_period() -> pd.DataFrame:
    monthly = pd.period_range("2015-01", "2026-08", freq="M")
    quarterly = pd.period_range("2015Q1", "2026Q3", freq="Q")
    yearly = pd.period_range("2015", "2026", freq="Y")
    rows: list[dict[str, Any]] = []
    for period_type, periods in (("month", monthly), ("quarter", quarterly), ("year", yearly)):
        for period in periods:
            start = period.start_time.date()
            end = period.end_time.date()
            year = end.year
            quarter = (end.month - 1) // 3 + 1 if period_type in {"month", "quarter"} else None
            month = end.month if period_type == "month" else None
            if period_type == "month":
                period_id = f"{year}M{month:02d}"
                prior = f"{(period - 1).year}M{(period - 1).month:02d}"
                prior_year = f"{year - 1}M{month:02d}"
            elif period_type == "quarter":
                period_id = f"{year}Q{quarter}"
                pprev = period - 1
                prior = f"{pprev.year}Q{pprev.quarter}"
                prior_year = f"{year - 1}Q{quarter}"
            else:
                period_id = str(year)
                prior = str(year - 1)
                prior_year = str(year - 1)
            easter = gregorian_easter(year)
            window = [easter + timedelta(days=offset) for offset in range(-7, 2)]
            rows.append(
                {
                    "period_id": period_id,
                    "period_type": period_type,
                    "period_start_date": start,
                    "period_end_date": end,
                    "year": year,
                    "quarter": quarter,
                    "month": month,
                    "days_in_period": (end - start).days + 1,
                    "is_covid_period": start <= date(2021, 12, 31) and end >= date(2020, 3, 1),
                    "prior_period_id": prior if start > date(2015, 1, 1) else None,
                    "prior_year_period_id": prior_year if year > 2015 else None,
                    "fiscal_period_id": period_id,
                    "calendar_period_id": period_id,
                    "easter_date": easter,
                    "easter_quarter": 1 if easter.month <= 3 else 2,
                    "easter_days_in_q1": sum(day.month <= 3 for day in window),
                    "easter_days_in_q2": sum(day.month >= 4 for day in window),
                }
            )
    return pd.DataFrame(rows).sort_values(["period_start_date", "period_type"]).reset_index(drop=True)


def build_dim_carrier() -> pd.DataFrame:
    t100 = pd.read_parquet(PATHS.silver / "bts_t100_segment.parquet")
    records: dict[str, dict[str, Any]] = {}
    for key, group in t100.groupby("carrier_key", dropna=False):
        if pd.isna(key):
            continue
        latest = group.sort_values(["year", "month"]).iloc[-1]
        records[str(key)] = dict(
            carrier_name=str(latest["source_carrier_name"]),
            carrier_name_short=str(latest["source_carrier_name"]),
            iata_code=latest.get("iata_code"),
            icao_code=latest.get("icao_code"),
            country=None,
            business_model="other",
            is_public=False,
            ticker=None,
            exchange=None,
            cik=None,
            reporting_standard=None,
            reporting_currency=None,
            unit_system="imperial",
            fiscal_year_end_month=None,
            parent_carrier_key=None,
            is_peer=False,
            is_focus=False,
        )
    afac = pd.read_parquet(PATHS.silver / "afac_monthly_stats.parquet")
    for key, group in afac.dropna(subset=["carrier_key"]).groupby("carrier_key"):
        records.setdefault(
            str(key),
            dict(
                carrier_name=str(group["source_carrier_name"].mode().iloc[0]),
                carrier_name_short=str(group["source_carrier_name"].mode().iloc[0]),
                iata_code=group["iata_code"].dropna().mode().iloc[0] if group["iata_code"].notna().any() else None,
                icao_code=None,
                country="Mexico" if group["is_domestic_carrier"].any() else None,
                business_model="other",
                is_public=False,
                ticker=None,
                exchange=None,
                cik=None,
                reporting_standard=None,
                reporting_currency=None,
                unit_system="metric",
                fiscal_year_end_month=None,
                parent_carrier_key=None,
                is_peer=False,
                is_focus=False,
            ),
        )
    records.update(CURATED_CARRIERS)
    rows = []
    for key, values in sorted(records.items()):
        rows.append(
            {
                "carrier_key": key,
                **values,
                "valid_from": date(1900, 1, 1),
                "valid_to": None,
                "is_current": True,
            }
        )
    return pd.DataFrame(rows)


def build_dim_route() -> pd.DataFrame:
    source = pd.read_parquet(PATHS.silver / "bts_t100_segment.parquet")
    grouped = source.groupby(["origin", "dest", "origin_country", "dest_country"], as_index=False).agg(distance_miles=("distance", "median"))
    grouped["route_key"] = grouped["origin"] + "-" + grouped["dest"]
    grouped["origin_iata"] = grouped["origin"]
    grouped["dest_iata"] = grouped["dest"]
    grouped["distance_km"] = grouped["distance_miles"] * MILES_TO_KM
    grouped["is_domestic_mx"] = grouped["origin_country"].eq("MX") & grouped["dest_country"].eq("MX")
    grouped["is_transborder_us"] = grouped[["origin_country", "dest_country"]].apply(lambda row: set(row) == {"MX", "US"}, axis=1)
    grouped["is_international"] = grouped["origin_country"].ne(grouped["dest_country"])
    grouped["market_key"] = grouped[["origin", "dest"]].apply(lambda row: "<>".join(sorted(row)), axis=1)
    return grouped[["route_key", "origin_iata", "dest_iata", "origin_country", "dest_country", "distance_km", "distance_miles", "is_domestic_mx", "is_transborder_us", "is_international", "market_key"]].sort_values("route_key").reset_index(drop=True)


def augment_dim_airport() -> pd.DataFrame:
    """Resolve T-100 codes absent from OurAirports using BTS source metadata."""

    dimension = pd.read_parquet(PATHS.gold / "dim_airport.parquet")
    source = pd.read_parquet(PATHS.silver / "bts_t100_segment.parquet")
    origin = source[["origin", "origin_city_name", "origin_country", "source_hash", "ingested_at"]].rename(
        columns={"origin": "airport_iata", "origin_city_name": "city_name", "origin_country": "country"}
    )
    destination = source[["dest", "dest_city_name", "dest_country", "source_hash", "ingested_at"]].rename(
        columns={"dest": "airport_iata", "dest_city_name": "city_name", "dest_country": "country"}
    )
    codes = pd.concat([origin, destination], ignore_index=True)
    missing = codes[~codes["airport_iata"].isin(set(dimension["airport_iata"].dropna()))]
    rows = []
    for code, group in missing.groupby("airport_iata"):
        hashes = sorted(set(group["source_hash"].astype(str)))
        rows.append(
            {
                "airport_iata": code,
                "airport_icao": None,
                "name": str(group["city_name"].mode().iloc[0]),
                "city": str(group["city_name"].mode().iloc[0]),
                "country": str(group["country"].mode().iloc[0]),
                "latitude": np.nan,
                "longitude": np.nan,
                "elevation": np.nan,
                "type": "historical_or_bts_only_code",
                "operator_group": None,
                "source_system": "bts_t100",
                "source_file": "silver/bts_t100_segment.parquet",
                "source_hash": hashlib.sha256("|".join(hashes).encode("utf-8")).hexdigest(),
                "ingested_at": pd.to_datetime(group["ingested_at"], utc=True).max().tz_convert(None),
                "parser_version": "stage6_v1.0.0",
            }
        )
    if rows:
        output = pd.concat([dimension, pd.DataFrame(rows, columns=dimension.columns)], ignore_index=True)
    else:
        output = dimension.copy()
    output["ingested_at"] = pd.to_datetime(output["ingested_at"], utc=True).dt.tz_convert(None)
    return output


def build_dim_airport_group() -> pd.DataFrame:
    """Build operator groups without pretending their totals are airports."""

    source = pd.read_parquet(PATHS.silver / "airport_traffic.parquet")
    groups = source[source["is_group_total"].fillna(False)].copy()
    if groups.empty:
        return pd.DataFrame(
            columns=[
                "airport_group_key", "airport_group_name", "country", "source_system",
                "source_file", "source_hash", "ingested_at",
            ]
        )
    groups["airport_group_key"] = groups["operator_group"].astype(str).str.upper()
    rows = []
    for key, frame in groups.groupby("airport_group_key"):
        source_systems = sorted(set(frame["source_system"].astype(str)))
        source_files = sorted(set(frame["source_file"].astype(str)))
        source_hashes = sorted(set(frame["source_hash"].astype(str)))
        rows.append(
            {
                "airport_group_key": key,
                "airport_group_name": f"{key} — aeropuertos operados en México",
                "country": "MX",
                "source_system": " | ".join(source_systems),
                "source_file": " | ".join(source_files),
                "source_hash": hashlib.sha256("|".join(source_hashes).encode("utf-8")).hexdigest(),
                "ingested_at": pd.to_datetime(frame["ingested_at"], utc=True).max().tz_convert(None),
            }
        )
    return pd.DataFrame(rows).sort_values("airport_group_key").reset_index(drop=True)


def _parse_glossary() -> dict[str, dict[str, str]]:
    text = (PATHS.root / "docs" / "plan" / "11-glosario-kpis.md").read_text(encoding="utf-8")
    sections: dict[str, dict[str, str]] = {}
    matches = list(re.finditer(r"^###\s+(.+)$", text, flags=re.MULTILINE))
    for index, match in enumerate(matches):
        heading = re.sub(r"[*`]", "", match.group(1)).strip()
        body = text[match.end(): matches[index + 1].start() if index + 1 < len(matches) else len(text)]
        fields: dict[str, str] = {"body": " ".join(line.strip() for line in body.splitlines() if line.strip() and line.strip() != "---")}
        for label in ["Qué es", "Fórmula", "Si sube", "Si baja", "Por qué importa más que PRASM", "Por qué es LA métrica", "Uso", "Advertencia", "Advertencia clave", "Regla"]:
            field_match = re.search(rf"\*\*{re.escape(label)}[^*]*:\*\*\s*(.*?)(?=\n\*\*|\n###|\n---|$)", body, flags=re.DOTALL)
            if field_match:
                fields[label] = " ".join(field_match.group(1).split())
        sections[heading] = fields
    return sections


def _find_section(sections: dict[str, dict[str, str]], needle: str) -> tuple[str, dict[str, str]]:
    for heading, fields in sections.items():
        if needle.lower() in heading.lower():
            return heading, fields
    raise KeyError(f"Glosario section not found: {needle}")


_ADDITIVE_METRICS = {
    "adjusted_ebitdar",
    "adjusted_ebitdar_company_normalized",
    "aircraft_communications_traffic_services",
    "aircraft_leasing_expense",
    "asm_total",
    "cargo_revenue",
    "depreciation_amortization",
    "equity_investees_share",
    "fuel_liters",
    "impairment_reversal",
    "income_before_tax",
    "income_tax",
    "jet_fuel_expense",
    "maintenance_expense",
    "net_finance_cost",
    "net_income",
    "operating_income_company_normalized",
    "operating_expenses_total",
    "operating_income",
    "other_income_loss_net",
    "other_revenue",
    "passenger_revenue",
    "passenger_services_expense",
    "passengers",
    "passengers_afac",
    "passengers_afac_sa",
    "rpm_total",
    "selling_administrative_expense",
    "total_revenue",
    "total_revenue_company_normalized",
    "travel_agent_commissions",
    "wages_salaries_benefits",
}

_LATEST_METRICS = {
    "cash_and_cash_equivalents",
    "fleet_size",
    "total_assets",
    "total_equity",
    "total_liabilities",
}

_NON_ADDITIVE_METRICS = {
    "aircraft_utilization",
    "ancillary_share",
    "asm_per_aircraft",
    "average_stage_length",
    "break_even_load_factor",
    "cask",
    "cask_derived",
    "cask_ex_fuel",
    "cask_ex_fuel_derived",
    "casm",
    "casm_ex_fuel",
    "ebitdar_margin",
    "ebitdar_margin_company_normalized",
    "fuel_cost_share",
    "jet_fuel_elasticity",
    "load_factor_derived",
    "load_factor_total",
    "market_share_domestic_mx",
    "on_time_departure_pct",
    "operating_margin",
    "operating_margin_company_normalized",
    "pask",
    "prask",
    "prask_derived",
    "prasm",
    "rask",
    "rask_derived",
    "revenue_per_passenger",
    "route_hhi",
    "sla_cask",
    "sla_rask",
    "trasm",
    "unit_margin",
    "yield",
    "yield_derived",
}


def consolidation_method(metric_key: str) -> str:
    """Return the declared parent/subsidiary aggregation for one metric."""

    if metric_key in _ADDITIVE_METRICS:
        return "sum"
    if metric_key in _LATEST_METRICS:
        return "latest"
    if metric_key in _NON_ADDITIVE_METRICS:
        return "non_additive"
    if metric_key.startswith("ttm_") and metric_key.removeprefix("ttm_") in _ADDITIVE_METRICS:
        return "sum"
    if metric_key.startswith(("qoq_growth_", "yoy_growth_")):
        return "non_additive"
    raise ValueError(
        f"Metric {metric_key!r} has no consolidation rule; declare sum, latest, "
        "non_additive or weighted with an explicit weight."
    )


def build_dim_metric(metric_keys: set[str]) -> pd.DataFrame:
    sections = _parse_glossary()
    rows: list[dict[str, Any]] = []
    all_keys = sorted(metric_keys | set(GLOSSARY_MAP))
    for order, key in enumerate(all_keys, start=1):
        metadata = GLOSSARY_MAP.get(key)
        if metadata:
            heading, fields = _find_section(sections, metadata["section"])
            what = fields.get("Qué es") or fields["body"]
            up = fields.get("Si sube") or f"Cuando sube, revisa su efecto junto con las métricas relacionadas. {what}"
            down = fields.get("Si baja") or f"Cuando baja, revisa su efecto junto con las métricas relacionadas. {what}"
            why = fields.get("Por qué importa más que PRASM") or fields.get("Por qué es LA métrica") or fields.get("Uso") or what
            caveats = fields.get("Advertencia clave") or fields.get("Advertencia") or fields.get("Regla") or "Compara siempre periodos y definiciones homogéneas."
            if metadata["category"] in {"unit_revenue", "unit_cost"}:
                caveats += " No compares entre aerolíneas sin ajustar por etapa promedio; usa SLA = métrica × sqrt(stage_length_km / 1834)."
            caveats += " Entre aerolíneas, considera IFRS frente a US-GAAP y el año fiscal de Ryanair."
            rows.append(
                dict(
                    metric_key=key,
                    metric_name_es=metadata["es"],
                    metric_name_en=metadata["en"],
                    metric_category=metadata["category"],
                    unit_normalized=metadata["unit"],
                    formula=fields.get("Fórmula"),
                    higher_is_better=metadata["better"],
                    business_interpretation_up=up,
                    business_interpretation_down=down,
                    why_it_matters=why,
                    typical_range_network="84–87%" if key in {"load_factor_total", "load_factor_derived"} else None,
                    typical_range_ulcc="90–96%" if key in {"load_factor_total", "load_factor_derived"} else None,
                    caveats=caveats,
                    display_format=metadata["fmt"],
                    display_order=order,
                    glossary_section=heading,
                    is_dashboard_metric=True,
                    consolidation_method=consolidation_method(key),
                )
            )
        else:
            label = SPANISH_FALLBACK_LABELS.get(key, key.replace("_", " ").strip().title())
            unit = "usd" if key in FALLBACK_USD_METRICS else ("fraction" if key == "ebitdar_margin" else "varies")
            higher_is_better = FALLBACK_HIGHER_IS_BETTER.get(key)
            direction_up = "puede ser favorable" if higher_is_better is True else ("aumenta la presión financiera" if higher_is_better is False else "no es mejor ni peor por sí solo")
            direction_down = "puede presionar el desempeño" if higher_is_better is True else ("puede aliviar la presión financiera" if higher_is_better is False else "no es mejor ni peor por sí solo")
            rows.append(
                dict(
                    metric_key=key,
                    metric_name_es=label,
                    metric_name_en=label,
                    metric_category="financial" if any(token in key for token in ("revenue", "income", "expense", "margin", "tax")) else "operational",
                    unit_normalized=unit,
                    formula=None,
                    higher_is_better=higher_is_better,
                    business_interpretation_up=f"Si {label} sube, {direction_up}; confirma sus impulsores y el periodo comparable.",
                    business_interpretation_down=f"Si {label} baja, {direction_down}; confirma sus impulsores y el periodo comparable.",
                    why_it_matters=f"{label} ayuda a leer la escala y la salud financiera reportada; debe interpretarse junto con márgenes, capacidad y caja.",
                    typical_range_network=None,
                    typical_range_ulcc=None,
                    caveats="Métrica de detalle no seleccionada para el dashboard; compara solo definiciones y periodos homogéneos.",
                    display_format="0,0.00",
                    display_order=1000 + order,
                    glossary_section=None,
                    is_dashboard_metric=False,
                    consolidation_method=consolidation_method(key),
                )
            )
    return pd.DataFrame(rows)
