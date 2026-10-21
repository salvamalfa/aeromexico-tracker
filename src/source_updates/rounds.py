"""Validate a complete bounded round before its first acquisition or write."""

from __future__ import annotations

import re
from pathlib import Path

from src.source_updates.build import build_plan
from src.source_updates.calendar import local_time
from src.source_updates.catalog import CHECK_TABLES
from src.source_updates.checks import period_end
from src.source_updates.collection import selection_plan


def validate_recipe(recipe: dict, workspace: Path) -> None:
    """Static preflight; it neither reads candidate tables nor constructs clients.

    Runtime checks still validate the actual source bytes, tables and lineage.
    Discovery-only selections belong to `collect`, never a successful data round.
    """
    selection_plan(recipe["selection"], workspace)
    build_plan(workspace, recipe["steps"])
    specification = recipe["checks"]
    cutoff = local_time(specification["as_of"])
    checks = specification.get("checks")
    if not isinstance(checks, list) or not checks:
        raise ValueError("Round requires explicit source/product/period checks before acquisition")
    selected = {
        item["product"] for item in recipe["selection"]["items"] if item["purpose"] == "data"
    }
    if not selected:
        raise ValueError("A data round needs explicit data selection; use collect for catalogue discovery")
    checked = set()
    for item in checks:
        product = item["product"]
        if item["layer"] not in {"silver", "gold"} or item["table"] not in CHECK_TABLES.get(product, ()):
            raise ValueError("Round check needs a supported product, layer and table")
        if not isinstance(item.get("filters", {}), dict):
            raise ValueError("Round check filters must be an explicit object")
        if item.get("kind") == "reference":
            if (
                product != "airports_reference"
                or item["layer"] != "gold"
                or not re.fullmatch(r"[0-9a-f]{64}", item.get("sha256", ""))
                or not item.get("required_codes")
            ):
                raise ValueError("Reference round check requires the direct snapshot hash and airport codes")
        else:
            if period_end(item["expected_period"]) >= cutoff.date():
                raise ValueError("Round observation period must be closed before the cutoff")
            values = item.get("value_columns")
            if (
                not isinstance(values, list)
                or not values
                or any(not isinstance(value, str) or not value for value in values)
                or len(values) != len(set(values))
            ):
                raise ValueError("Round check requires unique explicit value columns")
        if item.get("baseline_file"):
            baseline = (workspace / item["baseline_file"]).resolve()
            if not baseline.is_relative_to(workspace.resolve()) or not baseline.is_file():
                raise ValueError("Round baseline must exist inside the candidate workspace")
            if not item.get("revision_keys") and item.get("kind") != "reference":
                raise ValueError("Round revision comparison requires explicit natural keys")
        checked.add(product)
    if checked != selected:
        raise ValueError(
            "Round checks must match acquired data products; "
            f"unchecked={sorted(selected - checked)}, unselected={sorted(checked - selected)}"
        )
