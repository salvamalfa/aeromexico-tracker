"""Operational products supplement (and never replace) the source catalogue."""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import yaml

from src.source_updates.calendar import local_time

ROOT = Path(__file__).resolve().parents[2]
FAMILIES = {
    "corporate": ("sec_edgar", "bmv", "aeromexico_ir", "viva_ir", "ryanair_ir"),
    "traffic": ("afac", "bts_t100"),
    "airports": ("oma_ir", "aicm", "aifa"),
    "macro_market": ("banxico_sie", "federal_reserve_h10", "eia", "yahoo_finance"),
    "routes": (
        "international_route_authorities",
        "aena_spain",
        "aeromexico_route_press",
        "oma_route_newsroom",
        "colima_route_statement",
        "expansion_aifa_roster",
    ),
    "context": ("ourairports", "faa_iasa", "loughran_mcdonald"),
    "news": ("google_news", "gdelt", "news_http_error"),
    "internal": ("peer_profile", "curated_primary_sources", "derived_gold"),
}

# id, source_key, monthly/quarterly scope, acquisition limitation, existing parser step.
# Separate subproducts prevent SEC, AFAC, airports and route authorities from
# being treated as one homogeneous available/validated period.
PRODUCTS = (
    (
        "am_financials",
        "aeromexico_ir",
        "quarterly",
        "discover_new_ir_links_parser_historical_only",
        "parse.aeromexico_ir_financial",
    ),
    (
        "am_traffic_ir",
        "aeromexico_ir",
        "monthly",
        "monthly_ir_discovery_missing_use_selected_documents",
        None,
    ),
    ("am_sec", "sec_edgar", "both", "sec_identity_requires_dedicated_adapter_or_manual_import", "parse.sec"),
    ("volaris_sec", "sec_edgar", "both", "refresh_current_catalog_then_select_exhibits", "parse.peers"),
    ("delta_sec", "sec_edgar", "quarterly", "refresh_catalog_preserve_us_gaap", "parse.peers"),
    ("ryanair_sec", "sec_edgar", "quarterly", "refresh_catalog_preserve_fiscal_year", "parse.peers"),
    (
        "gap_traffic",
        "sec_edgar",
        "monthly",
        "select_gap_exhibits_separate_from_airline_financials",
        "parse.airports",
    ),
    ("asur_traffic", "sec_edgar", "monthly", "separate_mexico_from_other_countries", "parse.airports"),
    ("bmv_xbrl", "bmv", "quarterly", "offline_zip_member_registration_adapter_pending", None),
    (
        "viva_financials",
        "viva_ir",
        "quarterly",
        "legacy_downloader_stops_2026Q2_select_actual_new_url",
        "parse.peers",
    ),
    ("viva_traffic", "viva_ir", "monthly", "monthly_product_discovery_requires_selection", None),
    ("ryanair_ir", "ryanair_ir", "quarterly", "refresh_current_catalog_fiscal_comparability", "parse.peers"),
    ("afac_carriers", "afac", "monthly", "pdf_parser_and_validation_capped_june_2026", "parse.afac"),
    ("afac_airports", "afac", "monthly", "independent_product_manual_selection_parser_not_certified", None),
    ("afac_countries", "afac", "monthly", "independent_product_manual_selection_parser_not_certified", None),
    ("afac_margins", "afac", "monthly", "select_matching_cumulative_vintage_od_and_carrier", None),
    (
        "bts_segments",
        "bts_t100",
        "monthly",
        "explicit_years_including_revisions_verify_actual_mx_us_month",
        "parse.bts",
    ),
    ("oma_traffic", "oma_ir", "monthly", "discover_report_keep_group_totals_distinct", "parse.airports"),
    ("aicm_traffic", "aicm", "monthly", "select_latest_report_airport_total", "parse.airports"),
    ("aicm_slots", "aicm", "quarterly", "seasonal_schedule_is_not_observed_flights", None),
    ("aifa_traffic", "aifa", "monthly", "select_latest_workbook_schema_may_drift", "parse.airports"),
    ("banxico", "banxico_sie", "both", "fix_inpc_rate_independent_series_history_to_cutoff", "parse.fx"),
    (
        "h10",
        "federal_reserve_h10",
        "both",
        "explicit_fx_fallback_not_fix_no_inpc_or_policy_rate",
        "parse.h10",
    ),
    ("fuel", "eia", "both", "market_reference_report_days_covered", "parse.fuel"),
    (
        "equities",
        "yahoo_finance",
        "both",
        "ticker_identity_and_adjustment_revisions_no_pre_ipo_aero_splice",
        "parse.market",
    ),
    (
        "anac",
        "international_route_authorities",
        "quarterly",
        "access_challenge_not_absence_partial_geography",
        None,
    ),
    (
        "aerocivil",
        "international_route_authorities",
        "quarterly",
        "bounded_pagination_counts_operations_not_passengers",
        None,
    ),
    ("caa", "international_route_authorities", "quarterly", "flight_punctuality_is_not_airport_data", None),
    ("aena", "aena_spain", "quarterly", "manual_export_no_login_or_credentials_company_airport_not_od", None),
    ("am_routes", "aeromexico_route_press", "quarterly", "dated_announcements_not_observed_volume", None),
    ("oma_routes", "oma_route_newsroom", "quarterly", "dated_announcements_not_observed_volume", None),
    ("colima", "colima_route_statement", "quarterly", "secondary_mirror_presence_only", None),
    ("aifa_roster", "expansion_aifa_roster", "quarterly", "secondary_dated_roster_inference_only", None),
    (
        "airports_reference",
        "ourairports",
        "quarterly",
        "community_reference_version_crosswalk",
        "parse.airport_reference",
    ),
    ("iasa", "faa_iasa", "quarterly", "country_category_not_airline_safety_or_causality", None),
    (
        "dictionary",
        "loughran_mcdonald",
        "quarterly",
        "version_dictionary_no_automatic_tone_recalculation",
        None,
    ),
    ("rss", "google_news", "monthly", "metadata_only_dedupe_urls_no_complete_month_guarantee", "parse.news"),
    ("gdelt", "gdelt", "monthly", "metadata_only_dedupe_urls_no_complete_month_guarantee", "parse.news"),
    ("news_errors", "news_http_error", "never", "inactive_error_evidence_never_valid_news", None),
    ("peer_profiles", "peer_profile", "quarterly", "curated_no_endpoint_require_parent_lineage", None),
    (
        "curated_context",
        "curated_primary_sources",
        "quarterly",
        "curated_no_endpoint_require_parent_lineage",
        None,
    ),
    ("derived", "derived_gold", "both", "offline_formula_parent_lineage_no_models_or_activation", None),
)

# A shared institution is not an interchangeable data product. Unknown product
# adapters stay blocked instead of borrowing another table from that institution.
CHECK_TABLES = {
    "am_financials": ("aeromexico_ir_financial_history", "fact_carrier_metrics"),
    "am_sec": ("sec_operating_metrics", "sec_financials", "fact_carrier_metrics"),
    "volaris_sec": ("peer_operating_metrics", "peer_financials", "fact_carrier_metrics"),
    "delta_sec": ("peer_operating_metrics", "peer_financials", "fact_carrier_metrics"),
    "ryanair_sec": ("peer_operating_metrics", "peer_financials", "fact_carrier_metrics"),
    "bmv_xbrl": ("bmv_financials", "fact_carrier_metrics"),
    "viva_financials": ("peer_operating_metrics", "peer_financials", "fact_carrier_metrics"),
    "ryanair_ir": ("peer_operating_metrics", "peer_financials", "fact_carrier_metrics"),
    "afac_carriers": ("afac_monthly_stats", "fact_carrier_metrics"),
    "bts_segments": ("bts_t100_segment", "fact_route_traffic"),
    "oma_traffic": ("airport_traffic", "fact_airport_traffic", "fact_airport_group_traffic"),
    "gap_traffic": ("airport_traffic", "fact_airport_traffic", "fact_airport_group_traffic"),
    "asur_traffic": ("airport_traffic", "fact_airport_traffic", "fact_airport_group_traffic"),
    "aicm_traffic": ("airport_traffic", "fact_airport_traffic"),
    "aifa_traffic": ("airport_traffic", "fact_airport_traffic"),
    "banxico": ("fx_rates", "macro_indicators", "fact_macro"),
    "h10": ("fx_rates", "fact_macro"),
    "fuel": ("fuel_prices", "fact_macro"),
    "equities": ("market_prices", "fact_market_data"),
    "airports_reference": ("dim_airport",),
    "rss": ("news_headlines",),
    "gdelt": ("news_headlines",),
}


def bronze_aliases(product_id: str) -> tuple[str, ...]:
    """Institution aliases span layers; collection must match the advertised parser."""
    legacy = {
        "am_sec": ("sec",),
        "volaris_sec": ("sec",),
        "delta_sec": ("sec",),
        "ryanair_sec": ("sec",),
        "afac_carriers": ("afac",),
    }
    declared = tuple(load_catalog()[product_map()[product_id]["source_key"]]["source_systems"])
    supported = legacy.get(product_id, declared)
    if not set(supported) <= set(declared):
        raise ValueError("Parser-compatible Bronze alias is absent from the institution catalogue")
    return supported


def load_catalog() -> dict:
    sources = yaml.safe_load((ROOT / "config/source_catalog.yaml").read_text())["sources"]
    mapped = [key for keys in FAMILIES.values() for key in keys]
    if len(mapped) != len(set(mapped)) or set(mapped) != set(sources):
        raise ValueError("Source catalogue drift: update family policy before running")
    if set(item[1] for item in PRODUCTS) != set(sources):
        raise ValueError("Operational products do not cover the source catalogue")
    return sources


def product_map() -> dict:
    return {
        item[0]: {
            "id": item[0],
            "source_key": item[1],
            "cadence": item[2],
            "limitation": item[3],
            "parser_step": item[4],
            "family": next(f for f, keys in FAMILIES.items() if item[1] in keys),
        }
        for item in PRODUCTS
    }


def plan(round_kind: str, as_of: str, quarter: str | None = None, family: str | None = None) -> dict:
    sources = load_catalog()
    cutoff = local_time(as_of)
    previous = cutoff.date().replace(day=1) - timedelta(days=1)
    if round_kind not in {"monthly", "quarterly", "combined"}:
        raise ValueError("Only monthly, quarterly or combined rounds are supported")
    if round_kind != "monthly" and (
        not quarter
        or len(quarter) != 6
        or quarter[4] != "Q"
        or quarter[5] not in "1234"
        or not quarter[:4].isdigit()
    ):
        raise ValueError("Quarterly/combined rounds need an explicit YYYYQn period")
    if quarter:
        end = date(int(quarter[:4]), int(quarter[-1]) * 3, 1)
        next_month = (end.replace(day=28) + timedelta(days=4)).replace(day=1)
        if next_month > cutoff.date():
            raise ValueError("Cannot prepare a quarter that has not closed by the cutoff")
    products = []
    for product in product_map().values():
        cadence = product["cadence"]
        if cadence == "never" or (family and product["family"] != family):
            continue
        if round_kind != "combined" and cadence not in {"both", round_kind}:
            continue
        source = sources[product["source_key"]]
        target = (
            quarter
            if cadence == "quarterly" or (cadence == "both" and round_kind == "quarterly")
            else previous.strftime("%YM%m")
        )
        products.append(
            {
                **product,
                "target_period": target,
                "status": "selection_required" if source["artifact_expected"] else "offline_or_curated",
                "discovery_url": source["official_page_url"],
                "latest_available_period": None,
                "latest_validated_period": None,
                "latest_published_period": None,
                "release_lag_days": None,
                "acquisition_instructions": f"python -m src.source_updates recipe --product {product['id']}",
            }
        )
    return {
        "version": 1,
        "mode": "dry_run",
        "round": round_kind,
        "timezone": str(cutoff.tzinfo),
        "as_of": cutoff.isoformat(),
        "catalogue_sources": len(sources),
        "products": products,
        "network_requests": 0,
        "paid_requests": 0,
        "writes": [],
        "publication": "blocked_pending_separate_review_and_existing_gate",
        "activation": "none",
        "aerodatabox": "retained_untouched_no_new_calls",
    }
