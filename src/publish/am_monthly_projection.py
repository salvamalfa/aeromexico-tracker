"""Project a replayed IR month into a separate chart series, without activation.

This function does not publish, approve, mutate Gold, or mix the company's
reported universe with AFAC. A scoped publication gate must bind its output to
source authorization and the exact prior dashboard before making it visible.
"""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import pandas as pd

from src.source_updates.am_traffic_candidate import run


def project(workspace: Path, period: str, as_of: str, collection: str) -> dict:
    """Replay every retained source/output before selecting passengers."""
    checked = run(workspace, period, as_of, collection, check=True)
    frame = pd.read_parquet(workspace / "data/silver/aeromexico_ir_monthly_metrics.parquet")
    frame = frame[frame.metric_key.eq("passengers")]
    expected = {period, f"{int(period[:4]) - 1}M{period[-2:]}"}
    if set(frame.period_id) != expected or len(frame) != 6:
        raise ValueError("Expected precisely one corporate month and its reported prior-year comparison")
    if (
        set(frame.carrier_key) != {"AEROMEXICO"}
        or set(frame.source_system) != {"aeromexico_ir"}
        or set(frame.unit_normalized) != {"count"}
        or frame.duplicated(["period_id", "segment"]).any()
        or frame.value_normalized.isna().any()
        or (frame.value_normalized < 0).any()
    ):
        raise ValueError("Corporate monthly passengers have incompatible identity, units or grain")
    records = []
    for month, rows in frame.groupby("period_id", sort=True):
        values = dict(zip(rows.segment, rows.value_normalized, strict=True))
        if set(values) != {"domestic", "international", "total"}:
            raise ValueError("Expected the three separately reported passenger cells")
        combined = float(values["domestic"] + values["international"])
        records.append(
            {
                "period_id": month,
                "date": f"{month[:4]}-{month[-2:]}-01",
                "domestic": float(values["domestic"]),
                "international": float(values["international"]),
                "reported_total": float(values["total"]),
                "total_segment_sum": combined,
                "reconciliation_delta": float(values["total"]) - combined,
            }
        )
    original = workspace / "data/bronze" / checked["source_file"]
    provenance = json.loads(original.with_suffix(original.suffix + ".meta.json").read_text())
    return {
        "entity": "AEROMEXICO",
        "source_url": provenance["source_url"],
        "source_sha256": checked["source_sha256"],
        "captured_at": provenance["downloaded_at"],
        "documentary_date": checked["source_report_date_as_reported"],
        "scope": "company_reported_month_including_charter_and_its_prior_year_comparative_not_AFAC",
        "records": records,
    }


def apply(quarters: dict, series: dict) -> dict:
    """Return a candidate payload; every preexisting field remains untouched."""
    from jsonschema import Draft202012Validator

    from src.web_export.schemas import FLIGHTS_SCHEMA

    schema = {"$defs": FLIGHTS_SCHEMA["$defs"], "$ref": "#/$defs/corporate_monthly_passengers"}
    json.dumps(series, allow_nan=False)
    Draft202012Validator(schema).validate(series)
    result = deepcopy(quarters)
    result["corporate_monthly_passengers"] = deepcopy(series)
    return result


PRODUCTS = frozenset({"am_traffic_ir"})
TARGETS = ("data/v1/flights/quarters.json",)
CONTRACTS = ("flights.schema.json",)


def public_outputs(before: dict[str, bytes], projection: dict) -> dict[str, bytes]:
    """Add only the separate company-reported series to one published payload."""
    from .source_data_scope import encoded

    if set(before) != set(TARGETS):
        raise ValueError("Monthly passenger projection only changes the quarters document")
    original = json.loads(before[TARGETS[0]])
    result = apply(original, projection)
    return {TARGETS[0]: encoded(result)}


def replay(profile: dict, baseline: Path) -> dict:
    """Replay the frozen source and availability without claiming current freshness."""
    from src.config import PATHS
    from src.source_updates import readiness
    from src.source_updates.am_traffic_candidate import OUTPUTS, sha
    from src.source_updates.closed_editions import accepted

    if (
        set(profile) != {"schema_version", "item", "as_of"}
        or profile["schema_version"] != "am_monthly_source_profile_v1"
    ):
        raise ValueError("Unsupported monthly IR source profile")
    item = profile["item"]
    if item.get("product") != "am_traffic_ir" or item.get("adapter") != "am_traffic_ir":
        raise ValueError("Monthly profile needs the dedicated source adapter")
    recipe = {"version": 1, "as_of": profile["as_of"], "required_items": [item["id"]], "items": [item]}
    selected = readiness.preflight(recipe, PATHS.root / "tmp/source-updates/am-monthly-replay")[0]
    checked = readiness.check_task(selected, item["candidate_as_of"], profile["as_of"])
    if not accepted(selected, checked):
        raise ValueError("Monthly source availability was not verified at its retained cutoff")
    workspace = Path(item["workspace"])
    workspace = workspace if workspace.is_absolute() else PATHS.root / workspace
    binding = {
        "product": item["product"],
        "period": item["period"],
        "receipt_id": item["receipt_id"],
        "candidate_as_of": item["candidate_as_of"],
        "output_sha256": checked["output_sha256"],
    }
    receipt = workspace / "receipts" / f"am-traffic-{binding['period']}.json"
    series = project(workspace, binding["period"], binding["candidate_as_of"], binding["receipt_id"])
    inputs = [receipt]
    roots = [(workspace, item["receipt_id"])]
    if item.get("availability"):
        availability = item["availability"]
        other = Path(availability["workspace"])
        other = other if other.is_absolute() else PATHS.root / other
        roots.append((other, availability["run_id"]))
    for root, run_id in roots:
        collection = root / "receipts" / f"collection-{run_id}.json"
        manifest = root / "data/bronze/_manifest.jsonl"
        inputs.extend([collection, manifest])
        for row in map(json.loads, manifest.read_text().splitlines()):
            path = root / "data/bronze" / row["source_file"]
            inputs.extend([path, path.with_suffix(path.suffix + ".meta.json")])
    for name in OUTPUTS:
        path = workspace / "data" / (name + ".parquet")
        if sha(path) != binding["output_sha256"][name]:
            raise ValueError("Monthly candidate changed after its physical replay")
        inputs.append(path)
    return {
        "source_binding": binding,
        "projection": series,
        "input_files": [str(p) for p in sorted(set(inputs))],
    }
