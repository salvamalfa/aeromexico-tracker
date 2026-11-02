"""Rebuild the financial export and audit a non-active industry candidate offline."""

import argparse
import hashlib
import json
from pathlib import Path

import pandas as pd

from src.dashboard.entities import aggregate_industry
from src.dashboard.financial_periods import financial_periods
from src.web_export.executive import export_executive

ROOT = Path(__file__).resolve().parents[1]
MEMBERS = ("AEROMEXICO", "VIVA_AEROBUS", "VOLARIS")


def audit(site: Path, build_dir: Path, *, review_industry: bool = False) -> dict:
    source = site / "data/v1/executive.json"
    raw = source.read_bytes()
    payload = json.loads(raw)
    periods = financial_periods(payload)
    latest = periods[-1]
    result = {
        "reference_master": "3a299fbc",
        "source_sha256": hashlib.sha256(raw).hexdigest(),
        "published_default": payload["metadata"]["default_period"],
        "financial_latest": latest,
        "entity_latest": {key: block["last_period"] for key, block in payload["entities"].items()},
        "production_verified_for_this_change": False,
        "data_activation": "none",
        "industry_candidate": None,
    }
    build_dir.mkdir(parents=True, exist_ok=True)
    # Input is the real constructed financial payload. This runs the normal
    # exporter and its schema/privacy checks, without claiming a warehouse rebuild.
    if review_industry:
        from src.dashboard.industry_review import build_industry_review

        review_payload = build_industry_review(payload, latest)
        export_executive(review_payload, build_dir / "data/v1", skip_input_check=True)
    else:
        export_executive(payload, build_dir / "data/v1", skip_input_check=True)
    result["industry_review_written"] = review_industry
    keys = (
        "passengers",
        "ask_km",
        "load_factor",
        "rask_cents_per_km",
        "cask_cents_per_km",
        "unit_margin_cents_per_km",
        "load_factor_basis",
        "cask_ex_fuel_cents_per_km",
        "rpk_km",
    )
    inputs = []
    for entity in MEMBERS:
        record = next((r for r in payload["entities"][entity]["records"] if r["period_id"] == latest), None)
        if record is None:
            raise ValueError(f"Missing real issuer quarter: {entity} {latest}")
        inputs.append({"carrier_key": entity, "period_id": latest, **{key: record.get(key) for key in keys}})
    candidate = aggregate_industry(pd.DataFrame(inputs)).iloc[0].to_dict()
    assert abs(candidate["ask_km"] - sum(row["ask_km"] for row in inputs)) < 1e-5
    assert candidate["passengers"] == sum(row["passengers"] for row in inputs)
    assert (
        abs(
            candidate["unit_margin_cents_per_km"]
            - (candidate["rask_cents_per_km"] - candidate["cask_cents_per_km"])
        )
        < 1e-9
    )
    result["industry_candidate"] = {
        "status": "calculated_for_review_not_activated",
        "record": candidate,
        "inputs": inputs,
        "method": (
            "Existing aggregate_industry: additive passengers/ASK/RPK; "
            "ASK-weighted unit ratios and reported load factors."
        ),
        "requirements": [
            (
                "Review the source-versioned passenger and unit-cost definitions of all three issuers; "
                "native rounded unit costs differ from statement expenses/ASM."
            ),
            (
                "Accept an exact industry data projection with lineage, prior-period comparisons and "
                "reconciliations; individual issuer authorizations preserve Industry "
                "and do not activate this aggregate."
            ),
            (
                "Use the normal source-data publication gate and exact data authorization, "
                "then UI and deployment checks; "
                "no Industry thesis is required or activated by this calculation."
            ),
        ],
    }
    market = json.loads((site / "data/v1/market.json").read_bytes())
    result["afac"] = {
        "last_month": market["months"][-1]["period_id"],
        "last_quarter": market["quarters"][-1]["period_id"],
        "method_breaks": market["metadata"].get("method_breaks", []),
    }
    result["maps"] = {}
    for entity in ("AEROMEXICO", "INDUSTRY", "VIVA_AEROBUS", "VOLARIS"):
        prefix = "flights" if entity == "AEROMEXICO" else f"flights/entities/{entity}"
        network = json.loads((site / f"data/v1/{prefix}/international/{latest}.json").read_bytes())
        result["maps"][entity] = {
            key: network.get(key)
            for key in (
                "period_label",
                "availability",
                "observed_months",
                "expected_months",
                "coverage_by_source",
            )
        }
    assert source.read_bytes() == raw
    (build_dir / "industry-candidate.json").write_text(
        json.dumps(result["industry_candidate"], ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--site", type=Path, default=ROOT / "site")
    parser.add_argument("--build-dir", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument(
        "--review-industry",
        action="store_true",
        help="Write an explicit local Industry preview; no production activation",
    )
    args = parser.parse_args()
    result = audit(args.site, args.build_dir, review_industry=args.review_industry)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        json.dumps(
            {
                key: result[key]
                for key in ("published_default", "financial_latest", "entity_latest", "data_activation")
            }
        )
    )
