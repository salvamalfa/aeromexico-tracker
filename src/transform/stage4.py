"""Stage 4 gold dimensions and acceptance-quality evidence."""

from __future__ import annotations

from io import BytesIO
import json
import re

import pandas as pd
from pypdf import PdfReader

from src.config import PATHS
from src.ingest.regulatory.faa import FAA_RESULTS_URL
from src.ingest.stage4_common import latest_bronze, lineage, write_parquet_atomic


FAA_CURRENT_PAGE = "https://www.faa.gov/about/initiatives/iasa/iasa-program-results"
AERO_TRAFFIC_PAGE = "https://ir.aeromexico.com/news-events/traffic-reports"
AERO_RESULTS_PAGE = "https://ir.aeromexico.com/financial-information/quarterly-results"
AERO_FAQ_PAGE = "https://ir.aeromexico.com/ir-resources/investor-faqs"


EVENTS = [
    ("2020-06-30", "corporate", "restructuring", "Voluntary Chapter 11 filing", "Aeroméxico filed for Chapter 11 protection while continuing operations.", "negative", "https://ir.aeromexico.com/node/7751/html"),
    ("2021-05-25", "regulatory", "regulatory", "FAA downgraded Mexico to Category 2", "FAA found that Mexico did not meet ICAO safety oversight standards.", "negative", "https://www.faa.gov/newsroom/federal-aviation-administration-announces-results-mexicos-safety-assessment"),
    ("2022-03-17", "corporate", "restructuring", "Aeroméxico emerged from Chapter 11", "The restructuring plan became effective and the company emerged from Chapter 11.", "positive", "https://ir.aeromexico.com/static-files/27874233-295c-44d2-8f60-ccf676aedc9a"),
    ("2022-12-22", "corporate", "restructuring", "Chapter 11 cases formally closed", "The U.S. Bankruptcy Court issued the final decree closing the cases.", "positive", "https://ir.aeromexico.com/static-files/3205ca50-9601-4285-bdc2-8b13ed830334"),
    ("2023-09-14", "regulatory", "regulatory", "FAA restored Mexico to Category 1", "FAA restored the highest IASA safety rating after more than two years.", "positive", "https://www.faa.gov/newsroom/federal-aviation-administration-returns-mexico-highest-aviation-safety-status"),
    ("2024-05-13", "corporate", "market", "Aeroméxico filed Form F-1", "The company filed its initial registration statement for a proposed offering.", "positive", "https://ir.aeromexico.com/static-files/4e6ea709-46eb-4967-a867-b875adb3459e"),
    ("2025-07-19", "regulatory", "regulatory", "DOT proposed ending Delta-Aeroméxico ATI", "DOT issued tentative Order 2025-7-12 concerning the joint venture.", "negative", "https://www.transportation.gov/sites/dot.gov/files/2025-07/Order%202025-7-12.pdf"),
    ("2025-10-28", "regulatory", "regulatory", "DOT cancelled 13 Mexican-carrier routes", "DOT cancelled current or planned routes involving MEX and NLU, including Aeroméxico services.", "negative", "https://www.transportation.gov/briefing-room/trumps-transportation-secretary-sean-duffy-slashes-13-mexican-carrier-routes-us"),
    ("2025-11-05", "market", "market", "Global offering priced", "Aeroméxico priced ADSs at USD 19 and Mexican shares at MXN 35.34.", "positive", "https://ir.aeromexico.com/node/8281/html"),
    ("2025-11-06", "market", "market", "AERO began trading on NYSE and BMV", "ADSs and common shares began trading under ticker AERO.", "positive", AERO_FAQ_PAGE),
    ("2025-12-08", "operational", "operational", "November 2025 traffic results", "Aeroméxico published its November monthly traffic report.", "neutral", AERO_TRAFFIC_PAGE),
    ("2026-01-06", "operational", "operational", "December 2025 traffic results", "Aeroméxico published its December monthly traffic report.", "neutral", AERO_TRAFFIC_PAGE),
    ("2026-02-05", "operational", "operational", "January 2026 traffic results", "Aeroméxico published its January monthly traffic report.", "neutral", AERO_TRAFFIC_PAGE),
    ("2026-03-06", "operational", "operational", "February 2026 traffic results", "Aeroméxico published its February monthly traffic report.", "neutral", AERO_TRAFFIC_PAGE),
    ("2026-04-08", "operational", "operational", "March 2026 traffic results", "Aeroméxico published its March monthly traffic report.", "neutral", AERO_TRAFFIC_PAGE),
    ("2026-04-23", "corporate", "earnings", "First-quarter 2026 results", "Aeroméxico furnished its first-quarter results.", "neutral", AERO_RESULTS_PAGE),
    ("2026-05-07", "operational", "operational", "April 2026 traffic results", "Aeroméxico published its April monthly traffic report.", "neutral", AERO_TRAFFIC_PAGE),
    ("2026-06-04", "operational", "operational", "May 2026 traffic results", "Aeroméxico published its May monthly traffic report.", "neutral", AERO_TRAFFIC_PAGE),
    ("2026-07-02", "operational", "operational", "June 2026 traffic results", "Aeroméxico published its June monthly traffic report.", "neutral", AERO_TRAFFIC_PAGE),
    ("2026-07-13", "corporate", "earnings", "Second-quarter 2026 results", "Aeroméxico furnished its second-quarter results.", "neutral", AERO_RESULTS_PAGE),
    ("2026-08-03", "operational", "operational", "July 2026 traffic results", "Aeroméxico published its July monthly traffic report.", "neutral", AERO_TRAFFIC_PAGE),
]


def _complete_business_calendar(frame: pd.DataFrame, value_column: str) -> pd.DataFrame:
    source = frame.sort_values("date").drop_duplicates("date", keep="last").set_index("date")
    calendar = pd.DataFrame(index=pd.bdate_range(source.index.min(), source.index.max()))
    joined = calendar.join(source[[value_column]], how="left")
    joined["is_published"] = joined[value_column].notna()
    joined[value_column] = joined[value_column].ffill()
    joined["fill_method"] = joined["is_published"].map({True: "published", False: "prior_published_value"})
    return joined.reset_index(names="date")


def _period_dimensions(frame: pd.DataFrame, value_column: str, prefix: str) -> pd.DataFrame:
    parts: list[pd.DataFrame] = []
    for period_type, period in [
        ("month", frame["date"].dt.to_period("M")),
        ("quarter", frame["date"].dt.to_period("Q")),
    ]:
        item = frame.assign(_period=period).groupby("_period", observed=True)[value_column].agg(
            rate_avg="mean", rate_close="last", rate_min="min", rate_max="max"
        ).reset_index()
        if period_type == "month":
            item["period_id"] = item["_period"].map(
                lambda value: f"{value.year}M{value.month:02d}"
            )
        else:
            item["period_id"] = item["_period"].astype(str)
        item["period_type"] = period_type
        item = item.drop(columns="_period")
        parts.append(item)
    output = pd.concat(parts, ignore_index=True)
    if prefix == "fuel":
        output = output.rename(
            columns={
                "rate_avg": "price_avg_usd_per_gallon",
                "rate_close": "price_close_usd_per_gallon",
                "rate_min": "price_min_usd_per_gallon",
                "rate_max": "price_max_usd_per_gallon",
            }
        )
        output["price_avg_yoy_pct"] = pd.NA
        for period_type, periods in {"month": 12, "quarter": 4}.items():
            mask = output["period_type"].eq(period_type)
            output.loc[mask, "price_avg_yoy_pct"] = output.loc[
                mask, "price_avg_usd_per_gallon"
            ].pct_change(periods=periods)
    return output


def _events() -> tuple[pd.DataFrame, dict[str, object]]:
    results_path = latest_bronze("faa_iasa", "country_results")
    if results_path is None:
        raise FileNotFoundError("Missing FAA IASA bronze artifact; run Stage 4 ingestion first")
    text = "\n".join(page.extract_text() or "" for page in PdfReader(BytesIO(results_path.read_bytes())).pages)
    mexico_match = __import__("re").search(r"Mexico\s+([12])", text)
    if not mexico_match:
        raise RuntimeError("Mexico was not found in the FAA IASA results PDF")
    status = int(mexico_match.group(1))
    results_lineage = lineage(results_path)
    verified_at = pd.Timestamp(results_lineage["ingested_at"])
    verified_local = verified_at.tz_convert("America/Mexico_City")
    rows = []
    for event_date, event_type, category, title, description, direction, url in EVENTS:
        rows.append(
            {
                "event_date": pd.Timestamp(event_date),
                "event_type": event_type,
                "event_category": category,
                "title": title,
                "description": description,
                "affected_carriers": "AEROMEXICO",
                "impact_direction": direction,
                "source_url": url,
                "confidence": "high",
                "source_system": "curated_primary_sources",
                "source_file": None,
                "source_hash": None,
                "ingested_at": verified_at,
                "parser_version": "stage4_v1.0.0",
            }
        )
    rows.append(
        {
            "event_date": verified_local.tz_localize(None).normalize(),
            "event_type": "regulatory",
            "event_category": "regulatory",
            "title": f"FAA IASA verification: Mexico Category {status}",
            "description": "Verified against the current results file linked by FAA. No later published category change was found.",
            "affected_carriers": "ALL_MEXICAN_CARRIERS",
            "impact_direction": "positive" if status == 1 else "negative",
            "source_url": FAA_CURRENT_PAGE,
            "confidence": "high",
            "source_system": "faa_iasa",
            **results_lineage,
        }
    )
    return pd.DataFrame(rows).sort_values("event_date"), {
        "country": "Mexico", "category": status,
        "verified_at": verified_local.isoformat(),
        "results_file_url": FAA_RESULTS_URL, "results_page_url": FAA_CURRENT_PAGE,
        "results_file_publication_date": "2025-04-18",
        "page_last_updated": "2026-04-16",
    }


def _airport_correlation() -> dict[str, object]:
    traffic = pd.read_parquet(PATHS.silver / "airport_traffic.parquet")
    group_pivot = traffic.loc[traffic["is_group_total"]].pivot(
        index="period_id", columns="operator_group", values="passengers_total"
    )
    required_groups = ["ASUR", "GAP", "OMA"]
    groups = group_pivot[required_groups].dropna().sum(axis=1)
    afac = pd.read_parquet(PATHS.silver / "afac_monthly_stats.parquet")
    afac_total = afac.groupby("period_id")["value"].sum(min_count=1)
    joined = pd.concat([groups.rename("airport_groups"), afac_total.rename("afac")], axis=1).dropna()
    correlation = float(joined["airport_groups"].corr(joined["afac"]))
    return {
        "matched_months": len(joined), "first_period": joined.index.min(),
        "last_period": joined.index.max(), "pearson_correlation": correlation,
    }


def _airport_coverage() -> dict[str, object]:
    traffic = pd.read_parquet(PATHS.silver / "airport_traffic.parquet")
    dimension = pd.read_parquet(PATHS.gold / "dim_airport.parquet")
    dim_codes = set(dimension["airport_iata"].dropna().astype(str))
    traffic_codes = set(
        traffic.loc[~traffic["is_group_total"], "airport_iata"].dropna().astype(str)
    )
    sec_codes: set[str] = set()
    sec_path = PATHS.silver / "sec_reference_text.parquet"
    if sec_path.exists():
        sec = pd.read_parquet(sec_path)
        raw_codes = set(re.findall(r"\b[A-Z]{3}\b", " ".join(sec["text"].dropna().astype(str))))
        sec_codes = raw_codes & dim_codes
    # AFAC's Stage 3 source is carrier-level and exposes no airport field.
    required = traffic_codes | sec_codes
    missing = sorted(required - dim_codes)
    details = pd.DataFrame(
        [
            {
                "airport_iata": code,
                "appears_in_airport_traffic": code in traffic_codes,
                "appears_in_aeromexico_sec_text": code in sec_codes,
                "appears_in_afac_structured_data": False,
                "is_in_dim_airport": code in dim_codes,
            }
            for code in sorted(required)
        ]
    )
    write_parquet_atomic(details, PATHS.quality / "airport_source_coverage.parquet")
    return {
        "required_airport_codes": len(required),
        "traffic_airport_codes": len(traffic_codes),
        "aeromexico_text_airport_codes": len(sec_codes),
        "afac_airport_codes": 0,
        "missing_codes": missing,
        "coverage_pct": 1.0 if not required else (len(required) - len(missing)) / len(required),
        "scope_note": "AFAC monthly airline statistics contain no airport field; textual SEC tokens are retained only when they resolve to a current OurAirports IATA code.",
    }


def run() -> dict[str, object]:
    fx = pd.read_parquet(PATHS.silver / "fx_rates.parquet")
    fx["date"] = pd.to_datetime(fx["date"])
    fx_daily = _complete_business_calendar(fx, "rate_close")
    fx_daily["currency_pair"] = "USD/MXN"
    write_parquet_atomic(fx_daily, PATHS.gold / "fx_business_calendar.parquet")
    fx_period = _period_dimensions(fx_daily, "rate_close", "fx")
    fx_period["currency_pair"] = "USD/MXN"
    fx_period["pnl_conversion_method"] = "period_average"
    fx_period["balance_conversion_method"] = "period_close"
    write_parquet_atomic(fx_period, PATHS.gold / "dim_fx_period.parquet")

    fuel = pd.read_parquet(PATHS.silver / "fuel_prices.parquet")
    fuel["date"] = pd.to_datetime(fuel["date"])
    fuel_daily = _complete_business_calendar(fuel, "price_usd_per_gallon")
    write_parquet_atomic(fuel_daily, PATHS.gold / "fuel_business_calendar.parquet")
    fuel_period = _period_dimensions(fuel_daily, "price_usd_per_gallon", "fuel")
    write_parquet_atomic(fuel_period, PATHS.gold / "dim_fuel_period.parquet")

    events, faa = _events()
    write_parquet_atomic(events, PATHS.gold / "dim_events.parquet")
    faa_path = PATHS.quality / "faa_iasa_verification.json"
    faa_path.parent.mkdir(parents=True, exist_ok=True)
    faa_path.write_text(json.dumps(faa, indent=2) + "\n", encoding="utf-8")

    market = pd.read_parquet(PATHS.silver / "market_prices.parquet")
    nyse_reference = set(market.loc[market["ticker"].isin(["DAL", "VLRS"]), "date"])
    aero_dates = set(market.loc[market["ticker"].eq("AERO"), "date"])
    expected = {date for date in nyse_reference if pd.Timestamp(date) >= pd.Timestamp("2025-11-06")}
    missing_aero = sorted(pd.Timestamp(date).date().isoformat() for date in expected - aero_dates)

    correlation = _airport_correlation()
    coverage = _airport_coverage()
    traffic = pd.read_parquet(PATHS.silver / "airport_traffic.parquet")
    government = traffic.loc[traffic["airport_iata"].isin(["MEX", "NLU"])]
    government_hubs = {
        code: {
            "rows": int(len(group)),
            "first_period": group["period_id"].min(),
            "last_period": group["period_id"].max(),
        }
        for code, group in government.groupby("airport_iata")
    }
    quality = {
        "fx_business_days": len(fx_daily),
        "fx_missing_after_fill": int(fx_daily["rate_close"].isna().sum()),
        "fx_forward_filled_days": int((~fx_daily["is_published"]).sum()),
        "fuel_business_days": len(fuel_daily),
        "fuel_missing_after_fill": int(fuel_daily["price_usd_per_gallon"].isna().sum()),
        "fuel_forward_filled_days": int((~fuel_daily["is_published"]).sum()),
        "aero_first_date": str(market.loc[market["ticker"].eq("AERO"), "date"].min().date()),
        "aero_missing_nyse_sessions": missing_aero,
        "events": len(events),
        "faa": faa,
        "airport_correlation": correlation,
        "airport_coverage": coverage,
        "government_hubs": government_hubs,
    }
    (PATHS.quality / "stage4_acceptance.json").write_text(
        json.dumps(quality, indent=2, default=str) + "\n", encoding="utf-8"
    )
    return quality


def main() -> int:
    print(json.dumps(run(), indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
