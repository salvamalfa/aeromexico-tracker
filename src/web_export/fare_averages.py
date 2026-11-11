"""Allowlisted, contracted export of public fare means from private normalized data."""

from __future__ import annotations

import json
import math
from pathlib import Path

from jsonschema import Draft202012Validator

from src.config import PATHS
from src.fare_quotes.aggregate import build_averages
from src.web_export.privacy import check_file_size, check_privacy
from src.web_export.writer import write_json

CONTRACT = "fare-averages.schema.json"
PUBLIC_PATH = "fare-averages.json"


def validate_averages(payload):
    schema = json.loads((PATHS.root / "contracts/web" / CONTRACT).read_bytes())
    Draft202012Validator(schema).validate(payload)
    check_privacy(payload)
    if len({g["group_id"] for g in payload["groups"]}) != len(payload["groups"]):
        raise ValueError("Duplicate public fare group")
    if payload["periods"] != sorted({g["period_id"] for g in payload["groups"]}):
        raise ValueError("Fare period catalog disagrees with observations")
    for group in payload["groups"]:
        for summary in group["metrics"].values():
            if (summary["n"] == 0) != (summary["mean"] is None):
                raise ValueError("Missing mean/count mismatch")
            if summary["n"] > group["observations"]:
                raise ValueError("Metric count exceeds observed samples")
            if summary["mean"] is not None and not math.isfinite(summary["mean"]):
                raise ValueError("Fare mean must be finite")
        if group["paired_cash_points"] > min(group["metrics"][k]["n"] for k in ("cash_final_mxn", "points")):
            raise ValueError("Paired sample exceeds independent metric samples")
        if group["provider"] == "VOLARIS" and group["metrics"]["points"] != {"mean": None, "n": 0}:
            raise ValueError("Volaris points must be inapplicable")


def export_fare_averages(private: dict, out: Path) -> Path:
    payload = build_averages(private)
    validate_averages(payload)
    target = write_json(Path(out) / PUBLIC_PATH, payload)
    check_file_size(target)
    return target
