"""Selective monthly source routes using the existing native outbox and site gate."""

from __future__ import annotations

IMPACTS = {
    "am_traffic_ir": ["AEROMEXICO"],
    **{k: [] for k in ("aicm_traffic", "aifa_traffic", "asur_traffic", "gap_traffic")},
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
    if product in IMPACTS:
        return (
            "Only the validated source's airport-demand observations in the existing airport chart; "
            "preserve other groups, AFAC, flight-map counts, all seven theses and every other "
            "data payload; no Industry editorial"
        )
    raise ValueError("No selective monthly publication scope")


def verify_release(job, source, binding):
    from src.publish.source_data_scope import anchor

    spec = anchor()
    product = source["source_binding"]["item"]["product"]
    if (
        product not in IMPACTS
        or job["release_kind"] != "source_data"
        or job["entity"] != entity(product)
        or spec["product"] != product
        or spec["source_binding"] != binding
        or spec["period_id"] != job["period"]
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
