"""Select a financial calendar from complete records and their published views."""

import copy
import math
import re

CORE = (
    "passengers",
    "ask_km",
    "load_factor_reported",
    "rask_cents_per_km",
    "cask_cents_per_km",
    "unit_margin_cents_per_km",
)


def financial_periods(payload: dict) -> list[str]:
    blocks = [
        {"records": payload["records"], "views": payload["views"]},
        *payload.get("entities", {}).values(),
    ]
    return sorted(
        {
            row["period_id"]
            for row in payload["records"]
            if re.fullmatch(r"\d{4}Q[1-4]", row["period_id"])
            and row["period_id"] in payload["views"]
            and all(type(row.get(key)) in (int, float) and math.isfinite(row[key]) for key in CORE)
        }
        | {
            row["period_id"]
            for block in blocks[1:]
            for row in block["records"]
            if re.fullmatch(r"\d{4}Q[1-4]", row["period_id"])
            and row["period_id"] in block["views"]
            and all(
                type(row.get("load_factor" if key == "load_factor_reported" else key)) in (int, float)
                and math.isfinite(row["load_factor" if key == "load_factor_reported" else key])
                for key in CORE
            )
        }
    )


def with_financial_default(payload: dict) -> dict:
    """Normalize a new export, leaving the input and historical signed sites intact."""
    periods = financial_periods(payload)
    if not periods:
        raise ValueError("No complete financial quarter with a matching view")
    result = copy.deepcopy(payload)
    result["metadata"]["default_period"] = periods[-1]
    return result
