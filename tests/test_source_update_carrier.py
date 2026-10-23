"""Synthetic report contracts; actual retained source certification is recorded separately."""

from __future__ import annotations

import hashlib
import html
import json

import pandas as pd
import pytest

from src.source_updates import volaris_sec_source as vol
from src.source_updates.carrier_source_contract import identifier
from src.source_updates.carrier_source_gold import projection, verify_projection
from src.source_updates.volaris_source_spec import TABLES


def synthetic_volaris():
    # Values are constructed accounting/aviation identities, never issuer amounts.
    income = {
        2: 800,
        3: 500,
        4: 300,
        6: 200,
        7: 100,
        8: 100,
        10: 1000,
        **{i: 80 for i in range(12, 22)},
        22: 800,
        24: 200,
        26: 0,
        27: 0,
        28: 0,
        29: 0,
        31: 200,
        32: 0,
        33: 200,
    }
    op = {
        1: 1000,
        2: 800,
        3: 200,
        4: 20,
        5: 160,
        6: 80,
        7: 200,
        8: 20,
        10: 1,
        11: 1,
        13: 10,
        14: 10,
        16: 200000000,
        17: 200000000,
        19: 10,
        20: 50,
        21: 50,
        22: 100,
        23: 8,
        24: 7.2,
        26: 10000,
        27: 6000,
        28: 4000,
        29: 8000,
        30: 4800,
        31: 3200,
        32: 80,
        33: 80,
        34: 80,
        35: 10000,
        36: 6000,
        37: 4000,
        38: 100,
        39: 200,
        40: 20,
        41: 1,
        42: 100,
        43: 1,
        44: 20,
        45: 20,
    }
    ancillary = {2: 300, 3: 200, 4: 500, 6: 10000, 8: 50}
    balance = {
        **{i: 10 for i in TABLES[313]["rows"]},
        2: 100,
        4: 110,
        9: 150,
        16: 60,
        17: 210,
        27: 80,
        34: 60,
        35: 140,
        44: 70,
        45: 210,
    }
    cash = {2: 20, 3: -10, 4: -10, 5: 0, 6: 0, 7: 100, 8: 100}
    highlight_rows = {
        2: 1,
        3: 19,
        4: 26,
        5: 32,
        6: 35,
        7: 40,
        8: 2,
        9: 23,
        10: 24,
        11: 3,
        12: 4,
        13: 7,
        14: 8,
    }
    highlight = {**{r: op[i] for r, i in highlight_rows.items()}, 15: 440, 16: 44, 17: 2}
    values = {
        276: highlight,
        289: {3: 4, 4: 4, 5: 4, 7: 4, 8: 4, 9: 20},
        297: op,
        300: op,
        303: income,
        306: income,
        309: ancillary,
        310: ancillary,
        313: balance,
        316: cash,
        317: cash,
    }
    tables = ["<table><tr><td>synthetic non-report layout</td></tr></table>"] * 318
    for index, definition in TABLES.items():
        rows = [[""] for _ in range(definition["row_count"])]
        rows[: len(definition["headers"])] = definition["headers"]
        for r, (label, _, unit, _, _) in definition["rows"].items():
            token = str(values[index][r]) + ("%" if unit == "percent" else "x" if unit == "times_ltm" else "")
            rows[r] = [label, token, token, "unused comparative variation"]
            if index == 289:
                rows[r] += [token, "unused Q1 variation"]
            elif index in {313, 316, 317}:
                rows[r] = rows[r][:3]
        tables[index] = (
            "<table>"
            + "".join(
                "<tr>" + "".join("<td>" + html.escape(cell) + "</td>" for cell in row) + "</tr>"
                for row in rows
            )
            + "</table>"
        )
    content = (
        "<html>Consolidated Quarter: 2 Year: 2026 Mexico City, Mexico July 21, 2026 "
        "International Financial Reporting Standards (IFRS) "
        "(2) Includes scheduled and charter. (4) Includes scheduled. "
        "Each ADS represents ten CPOs EBITDAR " + "".join(tables) + "</html>"
    ).encode()
    directory = "/Archives/edgar/data/1520504/000129281426003836"
    primary = (
        "<html>FORM 6-K " + vol.ENTITY + " July 2026 July 21, 2026 "
        'Financial Results for the Second Quarter 2026 <a href="ex99-1.htm">99.1</a></html>'
    ).encode()
    recent = dict(
        accessionNumber=["0001292814-26-003836"],
        form=["6-K"],
        reportDate=["2026-06-30"],
        filingDate=["2026-07-21"],
        acceptanceDateTime=["2026-07-21T21:30:26.000Z"],
        primaryDocument=["vlrspr2q26_6k.htm"],
    )
    bodies = dict(
        html=content,
        primary=primary,
        submissions=json.dumps(
            dict(
                cik="0001520504",
                name="Controladora Vuela Compania de Aviacion, S.A.B. de C.V.",
                filings=dict(recent=recent),
            )
        ).encode(),
    )
    bodies["index"] = json.dumps(
        dict(
            directory=dict(
                name=directory,
                item=[
                    dict(name="ex99-1.htm", size=str(len(content))),
                    dict(name="vlrspr2q26_6k.htm", size=str(len(primary))),
                ],
            )
        )
    ).encode()
    urls = dict(
        html="https://www.sec.gov" + directory + "/ex99-1.htm",
        primary="https://www.sec.gov" + directory + "/vlrspr2q26_6k.htm",
        index="https://www.sec.gov" + directory + "/index.json",
        submissions="https://data.sec.gov/submissions/CIK0001520504.json",
    )
    return {
        role: (
            body,
            dict(
                source_system="sec",
                source_url=urls[role],
                source_file=role + ".json" if role in {"index", "submissions"} else role + ".htm",
                sha256=hashlib.sha256(body).hexdigest(),
                downloaded_at="2026-08-01T12:00:00Z",
            ),
        )
        for role, body in bodies.items()
    }


@pytest.fixture
def volaris_native():
    frame, details = vol.read(synthetic_volaris(), "2026Q2")
    frame["record_id"] = frame.apply(identifier, axis=1)
    return frame, details


def test_complete_synthetic_report_has_both_periods_audited_balance_and_miles(volaris_native):
    native, details = volaris_native
    gold = projection(native, "volaris_sec")
    verify_projection(native, gold, "volaris_sec")
    assert details["reconciliations_passed"] > 130
    assert {"2026Q2", "2026H1", "2025Q2", "2025H1", "2025-12-31", "2026-03-31"} <= set(native.period_id)
    assert set(native.loc[native.statement.eq("balance") & native.source_column.eq(2), "is_unaudited"]) == {
        False
    }
    booked = gold.loc[gold.metric_key.eq("booked_passengers_total") & gold.period_id.eq("2026Q2")]
    assert len(booked) == 1 and booked.iloc[0].value == 10000000
    assert set(gold.loc[gold.metric_key.eq("asm_total"), "unit"]) == {"seat_miles"}
    assert not gold.agent_eligible.any()


@pytest.mark.parametrize(
    "field,value",
    [
        ("unit", "passenger_miles"),
        ("scale", 1000),
        ("is_preliminary", True),
        ("is_unaudited", False),
        ("source_estimated", False),
        ("source_table", "298"),
        ("source_locator", "invented"),
        ("period_id", "2026H1"),
        ("segment", "domestic"),
        ("carrier_key", "AEROMEXICO"),
        ("source_system", "sec_edgar"),
    ],
)
def test_native_semantics_are_bound_to_reviewed_source_cell(volaris_native, field, value):
    native, _ = volaris_native
    native.loc[native.index[0], field] = value
    with pytest.raises(ValueError):
        projection(native, "volaris_sec")


@pytest.mark.parametrize("mode", ["casm", "identity", "drop_cell", "duplicate", "parent", "gold_scale"])
def test_report_inconsistency_or_projection_tamper_cannot_pass(volaris_native, mode):
    native, _ = volaris_native
    if mode in {"parent", "gold_scale"}:
        gold = projection(native, "volaris_sec")
        gold.loc[0, "native_parent_record_ids" if mode == "parent" else "scale"] = (
            json.dumps(["rec_" + "0" * 64]) if mode == "parent" else 1000
        )
        with pytest.raises((ValueError, AssertionError)):
            verify_projection(native, gold, "volaris_sec")
        return
    if mode in {"casm", "identity"}:
        mask = (
            native.source_table.eq("300" if mode == "casm" else "303")
            & native.source_row_number.eq(23 if mode == "casm" else 10)
            & native.source_column.eq(2)
        )
        native.loc[mask, ["source_value", "value"]] = ["99", 99]
    elif mode == "drop_cell":
        native = native.iloc[:-1]
    else:
        native = pd.concat([native, native.iloc[:1]], ignore_index=True)
    with pytest.raises(ValueError):
        projection(native, "volaris_sec")


def test_generic_retained_cannot_certify_complete_carrier_products():
    from pathlib import Path

    from src.source_updates.catalog import ROOT
    from src.source_updates.retained import frames, run

    workspace = ROOT / "tmp/source-updates/carrier-generic-guard"
    for product in ["volaris_sec", "afac_carriers"]:
        with pytest.raises(ValueError, match="carrier_source_candidate"):
            frames(workspace, product, "2026Q2", {}, pd.DataFrame())
        with pytest.raises(ValueError, match="carrier_source_candidate"):
            run(workspace, product, "2026Q2", "2026-10-23T16:00:00-06:00", "a" * 32, execute=True)
    assert isinstance(workspace, Path) and not workspace.exists()


@pytest.mark.parametrize(
    "product,period,adapter,accepted",
    [
        ("afac_carriers", "2026M08", "carrier_source", True),
        ("volaris_sec", "2026Q2", "carrier_source", True),
        ("afac_carriers", "2026M08", "retained", False),
        ("volaris_sec", "2026Q2", "retained", False),
        ("volaris_sec", "2026M08", "carrier_source", False),
        ("afac_airports", "2026M07", "carrier_source", False),
    ],
)
def test_readiness_requires_exact_dedicated_product_adapter(product, period, adapter, accepted):
    from src.source_updates.catalog import ROOT
    from src.source_updates.readiness import preflight

    candidate = ROOT / "tmp/source-updates/carrier-static-candidate"
    item = dict(
        id="carrier",
        product=product,
        period=period,
        adapter=adapter,
        workspace=str(candidate),
        receipt_id="a" * 32,
        required=True,
        candidate_as_of="2026-10-23T16:00:00-06:00",
    )
    recipe = dict(version=1, as_of=item["candidate_as_of"], required_items=["carrier"], items=[item])
    workspace = ROOT / "tmp/source-updates/carrier-static-round"
    if accepted:
        assert preflight(recipe, workspace)[0]["adapter"] == "carrier_source"
    else:
        with pytest.raises(ValueError):
            preflight(recipe, workspace)
    assert not workspace.exists() and not candidate.exists()


def test_effective_carrier_crosswalk_reads_utf8_under_non_utf8_system_locale():
    import os
    import subprocess
    import sys

    from src.source_updates.catalog import ROOT

    env = {**os.environ, "LC_ALL": "C", "PYTHONUTF8": "0", "PYTHONCOERCECLOCALE": "0"}
    code = (
        "from src.source_updates.afac_carrier_source import mapping; "
        'assert mapping("Aerom\\u00e9xico (Aerov\\u00edas de M\\u00e9xico)", '
        '"2026-08-31")[0] == "AEROMEXICO"'
    )
    completed = subprocess.run(
        [sys.executable, "-c", code],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    assert completed.returncode == 0, completed.stderr
