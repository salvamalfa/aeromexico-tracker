"""Resolve canonical acquisition entries and emit executable, bounded macro recipes."""

from __future__ import annotations

import importlib
import json
from urllib.parse import urlencode

from src.source_updates.calendar import local_time
from src.source_updates.catalog import ROOT, bronze_aliases, load_catalog, product_map
from src.source_updates.checks import period_end
from src.source_updates.collection import validate_url


def acquisition_config() -> dict:
    config = json.loads((ROOT / "config/source_update_acquisition.json").read_text())
    if set(config["products"]) != set(product_map()):
        raise ValueError("Acquisition recipes drifted from operational products")
    return config


def resolve_entry(reference: str):
    parts = reference.split(":")
    if parts[0] == "catalogue":
        return load_catalog()[parts[1]]["official_page_url"]
    if parts[0] == "url":
        return reference.removeprefix("url:")
    if parts[0] in {"constant", "mapping"}:
        value = getattr(importlib.import_module(parts[1]), parts[2])
        for key in parts[3:]:
            value = value[key]
        return value
    if parts[0] in {"sec", "sec_group"}:
        from src.config import CARRIERS
        from src.ingest.airports.groups import SEC_GROUPS
        from src.ingest.peers.stage5 import submissions_url

        cik = CARRIERS[parts[1]]["cik"] if parts[0] == "sec" else SEC_GROUPS[parts[1]]
        return submissions_url(str(cik))
    raise ValueError("Unknown canonical acquisition binding")


def describe(product_id: str) -> dict:
    product = product_map()[product_id]
    instructions = acquisition_config()["products"][product_id]
    evidence_path = ROOT / "docs/referencias/source-updates-20261018/real-source-pilot.json"
    evidence = json.loads(evidence_path.read_text()) if evidence_path.exists() else {}
    captured = next((row for row in evidence.get("acquisitions", []) if row["product"] == product_id), {})
    checked = next(
        (row for row in evidence.get("silver_checks", {}).get("checks", []) if row["product"] == product_id),
        {},
    )
    return {
        **product,
        **instructions,
        "entry_url": resolve_entry(instructions["entry_ref"]),
        **(
            {"discovery_url": resolve_entry(instructions["discovery_ref"])}
            if instructions.get("discovery_ref")
            else {}
        ),
        "canonical_config": "config/source_update_acquisition.json",
        "institution_catalogue": "config/source_catalog.yaml",
        "bronze_source_systems": list(bronze_aliases(product_id)),
        "pilot_evidence": {
            "as_of": evidence.get("finished_at"),
            "capture_status": captured.get("status", "not_exercised"),
            "parser_checks": checked.get("status", "not_exercised"),
            "reference": "docs/referencias/source-updates-20261018/real-source-pilot.json",
        },
        "activation": "none",
    }


def catalog_selection(product_id: str) -> dict:
    recipe = describe(product_id)
    source = load_catalog()[recipe["source_key"]]
    direct = {
        "airports_reference": ("airports", "csv"),
        "iasa": ("country_results", "pdf"),
        "rss": ("google_es", "xml"),
        "gdelt": ("aeromexico_articles", "json"),
    }
    if product_id in direct:
        url = recipe["entry_url"]
        if product_id == "gdelt":
            from src.ingest.news.rss_gdelt import GDELT_API_URL, GDELT_QUERY_PARAMS

            url = GDELT_API_URL + "?" + urlencode(GDELT_QUERY_PARAMS)
        validate_url(url, source["allowed_hosts"])
        entity, extension = direct[product_id]
        return {
            "version": 1,
            "items": [
                {
                    "id": product_id,
                    "product": product_id,
                    "source_system": source["source_systems"][0],
                    "entity": entity,
                    "period": "current",
                    "purpose": "data",
                    "url": url,
                    "extension": extension,
                    "mode": "get",
                }
            ],
        }
    if (
        recipe["state"] in {"manual", "internal", "disabled"}
        or not recipe.get("discovery_url", recipe["entry_url"])
        or not (recipe["format"].startswith("HTML") or recipe.get("discovery_url"))
    ):
        raise ValueError(
            "No generic catalog capture for this product; follow its explicit acquisition procedure"
        )
    url = recipe.get("discovery_url", recipe["entry_url"])
    validate_url(url, source["allowed_hosts"])
    return {
        "version": 1,
        "items": [
            {
                "id": product_id + "-catalog",
                "product": product_id,
                "source_system": source["source_systems"][0],
                "entity": product_id + "_catalog",
                "period": "current",
                "purpose": "catalog",
                "url": url,
                "extension": "html",
                "mode": "get",
            }
        ],
    }


def macro_round(product_id: str, period: str, as_of: str) -> dict:
    if product_id == "equities":
        from src.source_updates.market import round_recipe

        return round_recipe(period, as_of)
    from src.ingest.macro.banxico import (
        BANXICO_SERIES,
        FED_H10_SERIES_ID,
        H10_EXPORT_URL,
        SIE_EXPORT_URL,
        h10_export_params,
        sie_export_form,
    )
    from src.ingest.macro.fuel import EIA_SERIES_ID, EIA_XLS_URL

    if product_id not in {"fuel", "banxico", "h10"}:
        raise ValueError("No complete candidate round for this product; use its discovery/manual procedure")
    cutoff = local_time(as_of)
    end = period_end(period)
    if end >= cutoff.date():
        raise ValueError("Recipe requires a period closed before the cutoff")
    months = (
        [period]
        if "M" in period
        else [
            f"{period[:4]}M{month:02d}" for month in range(int(period[-1]) * 3 - 2, int(period[-1]) * 3 + 1)
        ]
    )
    base = {"product": product_id, "period": f"2015-01-01_{end}", "purpose": "data"}
    items, controls = [], []
    for month in months:
        if product_id == "fuel":
            controls.append(
                {
                    "product": product_id,
                    "layer": "silver",
                    "table": "fuel_prices",
                    "period_column": "date",
                    "expected_period": month,
                    "filters": {"series_id": EIA_SERIES_ID},
                    "value_columns": ["price_usd_per_gallon"],
                }
            )
        elif product_id == "banxico":
            for series in BANXICO_SERIES:
                controls.append(
                    {
                        "product": product_id,
                        "layer": "silver",
                        "table": "macro_indicators",
                        "period_column": "date",
                        "expected_period": month,
                        "filters": {"series_id": series},
                        "value_columns": ["value"],
                    }
                )
        else:
            controls.append(
                {
                    "product": product_id,
                    "layer": "silver",
                    "table": "fx_rates",
                    "period_column": "date",
                    "expected_period": month,
                    "filters": {"series_id": FED_H10_SERIES_ID},
                    "value_columns": ["rate_close"],
                }
            )
    if product_id == "fuel":
        items = [
            {
                **base,
                "id": "eia-history",
                "source_system": "eia",
                "entity": EIA_SERIES_ID,
                "url": EIA_XLS_URL,
                "extension": "xls",
                "mode": "get",
            }
        ]
    elif product_id == "banxico":
        items = [
            {
                **base,
                "id": series,
                "source_system": "banxico_sie",
                "entity": series,
                "url": SIE_EXPORT_URL,
                "extension": "csv",
                "mode": "banxico_series",
                "end_date": end.isoformat(),
                "public_form": sie_export_form(series, end.isoformat()),
            }
            for series in BANXICO_SERIES
        ]
    else:
        items = [
            {
                **base,
                "id": "h10-usd-mxn",
                "source_system": "federal_reserve_h10",
                "entity": "usd_mxn",
                "url": H10_EXPORT_URL + "?" + urlencode(h10_export_params(end.isoformat())),
                "extension": "csv",
                "mode": "get",
            }
        ]
    return {
        "version": 1,
        "product": product_id,
        "pipeline_state": "candidate_executable_not_approved",
        "acquisition": describe(product_id),
        "selection": {"version": 1, "items": items},
        "steps": [{"fuel": "parse.fuel", "banxico": "parse.fx", "h10": "parse.h10"}[product_id]],
        "checks": {"as_of": cutoff.isoformat(), "checks": controls},
        "coverage": "explicit_period_checks_only_no_day_completeness_or_Gold_certification",
        "activation": "none",
        "publication": "not_authorized",
    }
