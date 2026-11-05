"""Existing monthly workers can assess map impact without activating or publishing sources."""

PRODUCTS = frozenset({"afac_margins", "bts_segments"})


def consumer_plan(product):
    if product not in PRODUCTS:
        raise ValueError("Source has no official-route consumer")
    return dict(
        consumer="official_routes", target="data/v1/official-routes.json",
        scopes=["national", "international"] if product == "afac_margins" else ["us"],
        source_product=product, source_adapter="retained" if product == "afac_margins" else "bts",
        preparation="python -m src.source_updates.official_routes --selection <retained-selection.json> --execute",
        publication_adapter="src.publish.official_routes_projection",
        release_product="official_routes", activation="none", publication="exact_owner_authorization_required",
        constraints=["Keep the other source's accepted original and its actual months.",
                     "Replay selected originals; compare output identity before building.",
                     "No financial analysis, paid capture, new schedule or source calendar activation."],
    )
