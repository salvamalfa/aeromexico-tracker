"""Selective monthly source routes using the existing native outbox and site gate."""

from __future__ import annotations

IMPACTS = {
    "am_traffic_ir": ["AEROMEXICO"],
    "afac_carriers": ["AEROMEXICO", "VIVA_AEROBUS", "VOLARIS"],
    "afac_airports": [],
    "bts_segments": [],
    **{k: [] for k in ("aicm_traffic", "aifa_traffic", "asur_traffic", "gap_traffic", "oma_traffic")},
}


def entity(product):
    if product not in IMPACTS:
        raise ValueError("No selective monthly route for this source")
    return "AEROMEXICO" if product == "am_traffic_ir" else None


def publication_scope(product):
    if product == "am_traffic_ir":
        return (
            "Only the separately labelled Aeromexico company-reported monthly passenger series; "
            "preserve AFAC, other airlines, all seven theses and every other data payload; "
            "no quarterly aggregation or Airline Monthly editorial"
        )
    if product == "bts_segments":
        return (
            "Assess the existing July BTS flight-map dependency by exact physical replay; "
            "no new source or public data/model activation"
        )
    if product == "afac_carriers":
        return (
            "Only source-reported AFAC carrier months in passenger and market views; "
            "preserve corporate IR, prior periods, seven theses and no partial-quarter inference"
        )
    if product in IMPACTS:
        return (
            "Only the validated source's airport-demand observations in the existing airport chart; "
            "preserve other groups, AFAC, flight-map counts, all seven theses and every other "
            "data payload; no Industry editorial"
        )
    raise ValueError("No selective monthly publication scope")


def verify_release(job, source, binding):
    from src.publish.source_data_members import members
    from src.publish.source_data_scope import anchor

    spec = anchor()
    item = source["source_binding"]["item"]
    product = item["product"]
    matching = [u for u in members(spec) if u["source_binding"] == binding and u["product"] == product]
    if (
        product not in IMPACTS
        or job["release_kind"] != "source_data"
        or job["entity"] != entity(product)
        or len(matching) != 1
        or matching[0]["period"] != binding["period"]
        or job["period"] != item["period"]
    ):
        raise ValueError(
            "Selective monthly release does not consume this exact source, period and data stage"
        )


def verify_site(site, repo):
    from importlib import import_module

    from scripts.check_pages_publication import verifier_for

    module = verifier_for(site, repo)
    name = {
        "src.publish.source_data_scope": "verify_source_data",
        "src.publish.issuer_scope": "verify_issuer",
        "src.publish.movements_scope": "verify_movements",
        "src.publish.financial_scope": "verify_financial",
        "src.publish.editorial": "verify_editorial",
        "src.publish.verify": "verify_site",
    }[module]
    return getattr(import_module(module), name)(site)


def impact_status(product):
    if product == "bts_segments":
        return "existing_flights_dependency_assessment"
    return (
        "selective_monthly_source_projection"
        if product in IMPACTS
        else "existing_issuer_executive_projection"
    )


def scope_or_financial(product):
    return (
        publication_scope(product)
        if product in IMPACTS
        else "AEROMEXICO,VIVA_AEROBUS,VOLARIS; exclude Industria and unrelated products"
    )


def release_kind(product):
    return "source_dependency_assessment" if product == "bts_segments" else "source_data"


def native_item(item):
    """Apply the existing global calendar's explicit lagged-month semantics."""
    import re

    from src.source_updates.checks import period_end

    if item.get("product") not in IMPACTS:
        return item
    fields = {
        "id",
        "product",
        "period",
        "adapter",
        "workspace",
        "receipt_id",
        "candidate_as_of",
        "required",
        "availability",
        "source_period",
        "cadence",
        "used",
        "depends_on",
    }
    if set(item) - fields or item.get("cadence", "monthly") != "monthly":
        raise ValueError("Monthly source binding has undeclared overrides or another cadence")
    if (
        item.get("used", True) is not True
        or item.get("required", True) is not True
        or item.get("depends_on", []) != []
    ):
        raise ValueError("Do not omit or reinterpret this selected monthly source")
    source_period = item.get("source_period", item["period"])
    if not re.fullmatch(r"20\d{2}M(?:0[1-9]|1[0-2])", source_period):
        raise ValueError("Monthly source binding requires a literal native month")
    if source_period != item["period"] and (
        item["product"]
        not in {"afac_carriers", "afac_airports", "bts_segments", "aicm_traffic", "aifa_traffic"}
        or not re.fullmatch(r"20\d{2}M(?:0[1-9]|1[0-2])", item["period"])
        or period_end(source_period) > period_end(item["period"])
    ):
        raise ValueError("Native month is not admitted by the existing lagged-source calendar policy")
    result = {k: v for k, v in item.items() if k not in {"source_period", "cadence", "used", "depends_on"}}
    return {**result, "period": source_period, "required": True}
