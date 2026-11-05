"""Synthetic projection boundaries; real-original replay is retained privately."""

import copy
import hashlib
import json
from pathlib import Path

import pytest

from src.parse.afac.market_scope import TOTAL_FORMULA, TOTAL_KEY
from src.pipeline.offline import block_network
from src.publish.afac_history_projection import PROJECTION, TARGETS, public_outputs

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def before():
    return {name: (ROOT / "site" / name).read_bytes() for name in TARGETS}


@pytest.fixture
def projection(before):
    market = json.loads(before[TARGETS[1]])
    current = {row["period_id"]: row for row in market["months"] if row["period_id"].startswith("2026")}
    editions, cells = [], []
    for year in range(2019, 2027):
        through = 9 if year == 2026 else 12
        editions.append(
            {
                "year": year,
                "through": through,
                "source_sha256": hashlib.sha256(f"synthetic-{year}".encode()).hexdigest(),
                "source_file": f"afac/{year}/synthetic.xlsx",
                "captured_at": "2026-11-02T00:00:00+00:00" if year == 2026 else "2026-08-20T00:00:00+00:00",
                "native_total_checks": through * 4,
                "total_formula": TOTAL_FORMULA,
                "unmapped_in_denominator": ["Synthetic unmapped Mexican operator"],
            }
        )
        for month in range(1, through + 1):
            period = f"{year}M{month:02d}"
            segments = {}
            for segment in ("domestic", "international"):
                if year == 2026:
                    block = current[period]["segments"][segment]
                    values = {key: row["passengers"] for key, row in block["carriers"].items()}
                    remainder = block["mexican_carriers_passengers"] - sum(values.values())
                else:
                    # Deliberately synthetic values, not another source or approval.
                    values = {"AEROMEXICO": 1.0, "VIVA_AEROBUS": 2.0, "VOLARIS": 3.0}
                    remainder = 4.0
                values["OTHER_AFAC_MX_" + "a" * 16] = remainder
                values[TOTAL_KEY] = sum(values.values())
                segments[segment] = values
            segments["total"] = {
                key: segments["domestic"][key] + segments["international"][key]
                for key in segments["domestic"]
            }
            cells.extend(
                {"carrier_key": key, "period_id": period, "segment": segment, "value": value}
                for segment, values in segments.items()
                for key, value in values.items()
            )
    return {
        "schema_version": PROJECTION,
        "candidate_as_of": "2026-11-04T00:00:00+00:00",
        "source_editions": editions,
        "cells": cells,
    }


def test_native_projection_changes_only_the_declared_afac_surfaces(before, projection):
    original = copy.deepcopy(before)
    with block_network():
        outputs = public_outputs(before, projection)
    assert before == original
    assert set(outputs) == set(TARGETS)
    old, new = json.loads(before[TARGETS[0]]), json.loads(outputs[TARGETS[0]])
    assert {k: v for k, v in new.items() if k != "monthly_passengers"} == {
        k: v for k, v in old.items() if k != "monthly_passengers"
    }
    records = {row["period_id"]: row for row in new["monthly_passengers"]["records"]}
    assert len(records) == 141 and max(records) == "2026M09"
    assert new["monthly_passengers"]["period_end"] == "2026-09-30"
    for row in old["monthly_passengers"]["records"]:
        if row["period_id"] < "2019M01" or row["period_id"].startswith("2026"):
            assert records[row["period_id"]] == row
    assert records["2019M01"]["international"] == 1.0
    assert records["2019M01"]["reported_total"] == 2.0
    revised_market = json.loads(outputs[TARGETS[1]])
    assert revised_market["months"][-9:] == json.loads(before[TARGETS[1]])["months"][-9:]
    historical = next(row for row in revised_market["months"] if row["period_id"] == "2019M01")
    assert historical["segments"]["international"]["mexican_carriers_passengers"] == 10
    assert historical["segments"]["international"]["carriers"]["AEROMEXICO"]["share"] == 0.1


@pytest.mark.parametrize(
    "mutation",
    [
        "unknown",
        "missing_year",
        "extra_month",
        "hash",
        "formula",
        "duplicate",
        "foreign",
        "missing_group",
        "wrong_total",
        "compensating_operator_totals",
        "nonfinite",
        "negative",
        "bool",
    ],
)
def test_partial_ambiguous_or_unscoped_native_projections_are_rejected(before, projection, mutation):
    value = copy.deepcopy(projection)
    if mutation == "unknown":
        value["unreviewed"] = True
    elif mutation == "missing_year":
        value["source_editions"].pop(0)
    elif mutation == "extra_month":
        value["source_editions"][-1]["through"] = 10
    elif mutation == "hash":
        value["source_editions"][0]["source_sha256"] = "g" * 64
    elif mutation == "formula":
        value["source_editions"][0]["total_formula"] = "sum_mapped_or_foreign"
    elif mutation == "duplicate":
        value["cells"].append(copy.deepcopy(value["cells"][0]))
    elif mutation == "foreign":
        value["cells"][0]["carrier_key"] = "OTHER_AFAC_FOREIGN_" + "a" * 16
    elif mutation == "missing_group":
        value["cells"] = [
            r
            for r in value["cells"]
            if (r["carrier_key"], r["period_id"], r["segment"]) != ("AEROMEXICO", "2019M01", "domestic")
        ]
    elif mutation == "wrong_total":
        next(r for r in value["cells"] if r["carrier_key"] == TOTAL_KEY)["value"] += 1
    elif mutation == "compensating_operator_totals":
        for carrier, change in (("AEROMEXICO", 1), ("OTHER_AFAC_MX_" + "a" * 16, -1)):
            next(
                row for row in value["cells"]
                if (row["carrier_key"], row["period_id"], row["segment"]) == (carrier, "2019M01", "total")
            )["value"] += change
    else:
        value["cells"][0]["value"] = {"nonfinite": float("nan"), "negative": -1, "bool": True}[mutation]
    with pytest.raises(ValueError):
        public_outputs(before, value)


@pytest.mark.parametrize("target", TARGETS)
def test_current_2026_observations_cannot_be_silently_replaced(before, projection, target):
    changed = dict(before)
    payload = json.loads(changed[target])
    if target == TARGETS[0]:
        next(r for r in payload["monthly_passengers"]["records"] if r["period_id"] == "2026M01")[
            "domestic"
        ] += 1
    else:
        next(r for r in payload["months"] if r["period_id"] == "2026M01")["segments"]["domestic"]["carriers"][
            "AEROMEXICO"
        ]["passengers"] += 1
    changed[target] = json.dumps(payload).encode()
    with pytest.raises(ValueError, match="2026"):
        public_outputs(changed, projection)
