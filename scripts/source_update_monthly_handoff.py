"""Selective monthly source routes using the existing native outbox and site gate."""

from __future__ import annotations

from scripts.check_pages_publication import verify_site as verify_site

IMPACTS = {
    "am_traffic_ir": ["AEROMEXICO"],
    "viva_traffic": ["VIVA_AEROBUS"],
    "volaris_traffic_ir": ["VOLARIS"],
    "afac_carriers": ["AEROMEXICO", "VIVA_AEROBUS", "VOLARIS"],
    "afac_airports": [],
    "bts_segments": [],
    **{k: [] for k in ("aicm_traffic", "aifa_traffic", "asur_traffic", "gap_traffic", "oma_traffic")},
}


def entity(product):
    if product not in IMPACTS:
        raise ValueError("No selective monthly route for this source")
    return {
        "am_traffic_ir": "AEROMEXICO",
        "viva_traffic": "VIVA_AEROBUS",
        "volaris_traffic_ir": "VOLARIS",
    }.get(product)


def _single_publication_scope(product):
    if product == "am_traffic_ir":
        return (
            "Only the separately labelled Aeromexico company-reported monthly passenger series; "
            "preserve AFAC, other airlines, all seven theses and every other data payload; "
            "no quarterly aggregation or Airline Monthly editorial"
        )
    if product in {"viva_traffic", "volaris_traffic_ir"}:
        return (
            "Only the separately labelled company-reported monthly booked passenger series and "
            "same-edition annual comparisons for this airline; preserve AFAC, other corporate "
            "series, all theses and unrelated data; no incomplete quarterly aggregation"
        )
    if product == "afac_airports":
        return (
            "Only the separately labelled AFAC alternative for the explicitly selected existing "
            "airport-demand keys in the existing airport-demand JSON export; do not reinstate "
            "retired airport UI; preserve direct issuer reports, groups, flight maps and theses; "
            "no new airports, historical backfill or fabricated annual comparison"
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
            "Only the validated source's airport-demand observations in the existing airport-demand "
            "JSON export; do not reinstate retired airport UI; "
            "preserve other groups, AFAC, flight-map counts, all seven theses and every other "
            "data payload; no Industry editorial"
        )
    raise ValueError("No selective monthly publication scope")


def publication_scope(product):
    scope = _single_publication_scope(product)
    if product == "bts_segments":
        return scope
    return (
        "Default single-source scope: " + scope + ". "
        "Only an explicitly authorized request with additional_sources may extend that scope "
        "to the exact union of its individually ready, pinned members. Do not select extra sources "
        "automatically or wait for other sources; preserve all data outside that authorized union."
    )


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


def publication_source_hashes(item, checked):
    """Bind a publication after readiness replay; BTS keeps literal ZIP hashes in Silver."""
    import hashlib
    import io
    from pathlib import Path

    import pandas as pd

    outputs = checked["output_sha256"]
    if item["product"] == "bts_segments":
        key = "silver/bts_t100_segment"
        if (
            checked.get("status") != "checks_passed"
            or not {key, "gold/fact_route_traffic", "gold/bridge_record_lineage"} <= outputs.keys()
        ):
            raise ValueError("BTS arrival requires replay-verified Gold, lineage and pinned native Silver")
        path = Path(item["workspace"]) / "data" / (key + ".parquet")
        if not path.is_file() or path.is_symlink() or path.resolve() != path:
            raise ValueError("BTS arrival requires the regular pinned native Silver path")
        raw = path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != outputs[key]:
            raise ValueError("BTS native Silver changed after its verified replay")
        frame = pd.read_parquet(io.BytesIO(raw))
        if "source_hash" not in frame:
            raise ValueError("BTS native Silver has no literal original source hashes")
        return set(frame["source_hash"].dropna().tolist())
    hashes = set()
    for name in outputs:
        if name.startswith("gold/fact_"):
            frame = pd.read_parquet(Path(item["workspace"]) / "data" / (name + ".parquet"))
            if "source_hash" in frame:
                hashes.update(frame["source_hash"].dropna().tolist())
    return hashes
