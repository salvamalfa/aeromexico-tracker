"""Product-specific outbox routes; no native send or publication side effects."""

from __future__ import annotations

from src.source_updates.aerocivil_operational import accepted as aerocivil_accepted


def impact_status(product: str) -> str:
    if product == "aerocivil":
        return "recorded_movements_in_existing_flights_map"
    return (
        "existing_issuer_executive_projection"
        if product
        in {
            "am_financials",
            "volaris_sec",
            "viva_financials",
        }
        else "no_public_impact"
    )


def native_item(item: dict) -> dict:
    """Keep the Q3 job separate from the one observed July source month."""
    if item.get("product") != "aerocivil":
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
    if set(item) - fields or item.get("adapter") != "aerocivil":
        raise ValueError("Use the complete dedicated Aerocivil source binding")
    if item.get("period") != "2026Q3" or item.get("source_period") != "2026M07":
        raise ValueError("Aerocivil movements route currently verifies 2026Q3 with native 2026M07 only")
    if (
        item.get("cadence", "quarterly") != "quarterly"
        or item.get("used", True) is not True
        or item.get("required", True) is not True
        or item.get("depends_on", []) != []
    ):
        raise ValueError("Do not omit or reinterpret Aerocivil task requirements/dependencies")
    return {
        **{
            key: value
            for key, value in item.items()
            if key
            not in {
                "source_period",
                "cadence",
                "used",
                "depends_on",
            }
        },
        "period": item["source_period"],
        "required": True,
    }


def verify_movement_acceptance(checked: dict):
    if (
        not aerocivil_accepted(checked)
        or checked.get("semantic_acceptance_verified") is not False
        or checked.get("operational_acceptance", {}).get("official_confirmation") is not False
    ):
        raise ValueError("Aerocivil needs its physically bound provisional operational acceptance")


def verify_release(job: dict, source: dict, binding: dict):
    """Only the product's own strong gate can certify its public data binding."""
    product = source["source_binding"]["item"]["product"]
    if source.get("product", product) != product:
        raise ValueError("Source product alias differs from its immutable binding")
    if product == "aerocivil":
        from src.publish.movements_scope import anchor

        spec = anchor()
        if (
            job["release_kind"] != "movements"
            or job["entity"] != "AEROMEXICO"
            or spec.get("product") != "aerocivil"
            or spec.get("source_binding") != binding
            or spec.get("period_id") != job["period"]
            or spec.get("stage") != "movements"
        ):
            raise ValueError("Movement release does not consume this exact source/period/stage")
        return
    if job["release_kind"] not in {"data", "editorial"}:
        raise ValueError("A financial source cannot use another product's release stage")
    from src.publish.issuer_scope import anchor

    spec = anchor()
    allowed = {"data_only"} if job["release_kind"] == "data" else {"editorial_only", "combined"}
    if (
        spec.get("source_binding") != binding
        or spec.get("entity_key") != job["entity"]
        or spec.get("period_id") != job["period"]
        or spec.get("stage") not in allowed
    ):
        raise ValueError("Dashboard publication does not consume this exact source and release stage")


def verify_site(site, repo):
    from importlib import import_module

    from scripts.check_pages_publication import verifier_for

    module = verifier_for(site, repo)
    function = {
        "src.publish.movements_scope": "verify_movements",
        "src.publish.issuer_scope": "verify_issuer",
        "src.publish.financial_scope": "verify_financial",
        "src.publish.editorial": "verify_editorial",
        "src.publish.verify": "verify_site",
    }[module]
    return getattr(import_module(module), function)(site)
