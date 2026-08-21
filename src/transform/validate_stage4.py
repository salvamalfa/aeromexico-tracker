"""Executable Definition of Done for Stage 4."""

from __future__ import annotations

import json

import pandas as pd

from src.config import PATHS
from src.ingest.stage4_common import write_parquet_atomic


SILVER_KEYS = {
    "fx_rates.parquet": ["date", "currency_pair", "series_id"],
    "fuel_prices.parquet": ["date", "series_id"],
    "market_prices.parquet": ["date", "ticker"],
    "airport_traffic.parquet": ["period_id", "operator_group", "airport_iata"],
    "news_headlines.parquet": ["url", "query_term"],
}
LINEAGE = ["source_system", "source_file", "source_hash", "ingested_at", "parser_version"]


def run() -> pd.DataFrame:
    evidence = json.loads((PATHS.quality / "stage4_acceptance.json").read_text(encoding="utf-8"))
    checks: list[dict[str, object]] = []

    def add(name: str, passed: bool, observed: object, expected: object) -> None:
        checks.append(
            {"check_name": name, "passed": bool(passed), "observed": str(observed), "expected": str(expected)}
        )

    add("fx_business_calendar_complete", evidence["fx_missing_after_fill"] == 0, evidence["fx_missing_after_fill"], 0)
    add("fuel_business_calendar_complete", evidence["fuel_missing_after_fill"] == 0, evidence["fuel_missing_after_fill"], 0)
    add("aero_starts_on_ipo", evidence["aero_first_date"] == "2025-11-06", evidence["aero_first_date"], "2025-11-06")
    add("aero_has_all_nyse_sessions", not evidence["aero_missing_nyse_sessions"], len(evidence["aero_missing_nyse_sessions"]), 0)
    add("airport_dimension_coverage", evidence["airport_coverage"]["coverage_pct"] == 1.0, evidence["airport_coverage"]["coverage_pct"], 1.0)
    add("airport_group_afac_correlation", evidence["airport_correlation"]["pearson_correlation"] > 0.9, evidence["airport_correlation"]["pearson_correlation"], ">0.9")
    add("airport_correlation_sample", evidence["airport_correlation"]["matched_months"] >= 6, evidence["airport_correlation"]["matched_months"], ">=6")
    for code in ["MEX", "NLU"]:
        hub = evidence["government_hubs"].get(code, {})
        complete = (
            hub.get("rows") == 7
            and hub.get("first_period") == "2026M01"
            and hub.get("last_period") == "2026M07"
        )
        add(
            f"{code.lower()}_government_hub_complete",
            complete,
            hub,
            "7 months from 2026M01 through 2026M07",
        )
    add("events_minimum", evidence["events"] >= 15, evidence["events"], ">=15")
    add("faa_current_category", evidence["faa"]["category"] == 1, evidence["faa"]["category"], 1)

    events = pd.read_parquet(PATHS.gold / "dim_events.parquet")
    add("event_urls_present", events["source_url"].str.startswith("https://").all(), int(events["source_url"].notna().sum()), len(events))
    news = pd.read_parquet(PATHS.silver / "news_headlines.parquet")
    add("news_collection_nonempty", len(news) > 0, len(news), ">0")
    add("news_is_media_coverage", news["source_system"].isin(["rss", "gdelt"]).all(), sorted(news["source_system"].unique()), "rss/gdelt only")

    for filename, keys in SILVER_KEYS.items():
        frame = pd.read_parquet(PATHS.silver / filename)
        add(f"{filename}:lineage_complete", not frame[LINEAGE].isna().any().any(), int(frame[LINEAGE].isna().sum().sum()), 0)
        add(f"{filename}:natural_key_unique", not frame.duplicated(keys).any(), int(frame.duplicated(keys).sum()), 0)

    market = pd.read_parquet(PATHS.silver / "market_prices.parquet")
    add("market_ohlc_valid", ((market["low"] <= market["high"]) & (market["volume"] >= 0)).all(), len(market), "all rows")
    fuel = pd.read_parquet(PATHS.silver / "fuel_prices.parquet")
    add("fuel_prices_positive", fuel["price_usd_per_gallon"].gt(0).all(), float(fuel["price_usd_per_gallon"].min()), ">0")
    fx = pd.read_parquet(PATHS.silver / "fx_rates.parquet")
    add("fx_rates_positive", fx["rate_close"].gt(0).all(), float(fx["rate_close"].min()), ">0")

    output = pd.DataFrame(checks)
    write_parquet_atomic(output, PATHS.quality / "stage4_validation_checks.parquet")
    failed = output.loc[~output["passed"]]
    if not failed.empty:
        raise AssertionError(f"Stage 4 validation failures: {failed['check_name'].tolist()}")
    return output


def main() -> int:
    checks = run()
    print(f"{int(checks['passed'].sum())}/{len(checks)} Stage 4 checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
