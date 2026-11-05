"""Rebuild a local Market candidate from an official AFAC annual summary.

Reuse the existing annual passenger parser, crosswalk, market generator and web
contract. Preserve the historical public monthly baseline before the workbook
year. Never edits published site/, Gold or the publication manifest.
"""

import argparse
import hashlib
import json
from collections import defaultdict
from pathlib import Path

import duckdb
from jsonschema import Draft202012Validator

from src.config import PATHS
from src.dashboard.market import build_market_payload
from src.parse.afac.market_scope import RETAINED_TOTAL_FORMULA, TOTAL_FORMULA, TOTAL_KEY, market_cells
from src.parse.afac.monthly_stats import _load_crosswalk, parse_annual_passenger_workbook
from src.web_export.privacy import check_privacy, load_privacy_rules
from src.web_export.writer import write_json


def build(baseline, workbook, year, through, captured_at, database):
    facts, checks = parse_annual_passenger_workbook(workbook, year)
    native_values, receipt = market_cells(facts, checks, year, through, _load_crosswalk())
    values = defaultdict(float)
    for month in baseline["months"]:
        if int(month["period_id"][:4]) >= year:
            continue
        for segment, block in month["segments"].items():
            if block["mexican_carriers_passengers"] is None:
                continue
            if any(item["passengers"] is None for item in block["carriers"].values()):
                raise ValueError("Historical baseline has incomplete carrier cells")
            for key, item in block["carriers"].items():
                values[(key, month["period_id"], segment)] += item["passengers"]
            remainder = block["mexican_carriers_passengers"] - sum(
                item["passengers"] for item in block["carriers"].values()
            )
            if remainder < 0:
                raise ValueError("Negative historical remainder")
            values[("OTHER_MX", month["period_id"], segment)] += remainder
            values[(TOTAL_KEY, month["period_id"], segment)] = block["mexican_carriers_passengers"]
    values.update(native_values)
    with duckdb.connect(str(database)) as connection:
        connection.execute(
            "CREATE OR REPLACE TABLE v_carrier_default("
            "carrier_key VARCHAR, period_id VARCHAR, segment VARCHAR, value DOUBLE, "
            "metric_key VARCHAR, period_type VARCHAR, derivation_formula VARCHAR)"
        )
        connection.executemany(
            "INSERT INTO v_carrier_default VALUES (?,?,?,?, 'passengers_afac','month',?)",
            [
                (
                    key,
                    period,
                    segment,
                    value,
                    TOTAL_FORMULA if int(period[:4]) == year else RETAINED_TOTAL_FORMULA,
                )
                for (key, period, segment), value in values.items()
            ],
        )
        connection.execute(
            "CREATE OR REPLACE TABLE dim_source_artifact(source_system VARCHAR, downloaded_at TIMESTAMPTZ)"
        )
        connection.execute("INSERT INTO dim_source_artifact VALUES ('afac',?)", [captured_at])
    payload = build_market_payload(str(database))
    Draft202012Validator(json.loads((PATHS.root / "contracts/web/market.schema.json").read_bytes())).validate(
        payload
    )
    check_privacy(payload, load_privacy_rules())
    receipt.update(
        source_sha256=hashlib.sha256(Path(workbook).read_bytes()).hexdigest(),
        year=year,
        through=through,
        retained_before_year=year,
        retained_baseline_recertified=False,
        last_period=payload["metadata"]["last_period"],
        default_quarter=payload["metadata"]["default_quarter"],
    )
    return payload, receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workbook", type=Path, required=True)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--year", type=int, required=True)
    parser.add_argument("--through", type=int, required=True)
    parser.add_argument("--captured-at", required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    args.out.resolve().relative_to(PATHS.root / "tmp")
    args.out.mkdir(parents=True, exist_ok=True)
    payload, receipt = build(
        json.loads(args.baseline.read_bytes()),
        args.workbook,
        args.year,
        args.through,
        args.captured_at,
        args.out / "market.duckdb",
    )
    write_json(args.out / "market.json", payload)
    write_json(args.out / "receipt.json", receipt)
    print(json.dumps(receipt, ensure_ascii=False))


if __name__ == "__main__":
    main()
