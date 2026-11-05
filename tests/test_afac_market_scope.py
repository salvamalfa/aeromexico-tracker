"""Scope regression, with optional independent checks against retained originals."""

import hashlib
import json
from copy import deepcopy

import duckdb
import openpyxl
import pytest

from scripts.build_afac_market_review import build
from src.config import PATHS
from src.dashboard.market import build_market_payload
from src.parse.afac.market_scope import TOTAL_FORMULA, TOTAL_KEY, carrier_identity, market_cells
from src.parse.afac.monthly_stats import _load_crosswalk, parse_annual_passenger_workbook


def native_workbook(path, *, broken=False):
    book = openpyxl.Workbook()
    book.remove(book.active)
    for sheet in ("PAXREG", "PAXFLET"):
        ws = book.create_sheet(sheet)
        for mexican, market in ((True, "NACIONAL"), (True, "INTERNACIONAL"), (False, "INTERNACIONAL")):
            ws.append([None, None, "EMPRESAS NACIONALES" if mexican else "EMPRESAS EXTRANJERAS"])
            ws.append([None, None, f"EN SERVICIO {market}"])
            ws.append(["EMPRESA / AIR CARRIER", "ENE/JAN", *[str(n) for n in range(2, 13)]])
            ws.append(["Unknown charter operator", *([3 if mexican else 1000] * 12)])
            # A blank TOTAL belongs only to the anchored Mexican layout.
            ws.append(
                [None if mexican else "TOTAL", *([4 if broken and mexican else 3 if mexican else 1000] * 12)]
            )
    book.save(path)


def test_unlabelled_native_totals_and_unknown_country_are_preserved(tmp_path):
    path = tmp_path / "native.xlsx"
    native_workbook(path)
    facts, checks = parse_annual_passenger_workbook(path, 2019)
    cells, receipt = market_cells(facts, checks, 2019, 12, {})
    assert receipt["checks"] == 48
    assert cells[TOTAL_KEY, "2019M01", "international"] == 6
    assert cells[TOTAL_KEY, "2019M01", "total"] == 12
    keys = {carrier_identity(row, {})[0] for row in facts}
    assert len(keys) == 2
    assert any(key.startswith("OTHER_AFAC_MX_") for key in keys)
    assert any(key.startswith("OTHER_AFAC_FOREIGN_") for key in keys)
    assert not any(key.startswith("OTHER_AFAC_FOREIGN_") for key, _, _ in cells)


def test_unlabelled_total_must_equal_every_native_month(tmp_path):
    path = tmp_path / "broken.xlsx"
    native_workbook(path, broken=True)
    with pytest.raises(ValueError, match="Unlabelled AFAC TOTAL"):
        parse_annual_passenger_workbook(path, 2019)


@pytest.mark.parametrize("mutation", ["missing", "duplicate", "false_check", "foreign_only"])
def test_total_receipt_cannot_replace_native_reconciliation(tmp_path, mutation):
    path = tmp_path / "native.xlsx"
    native_workbook(path)
    facts, checks = parse_annual_passenger_workbook(path, 2019)
    checks = deepcopy(checks)
    if mutation == "missing":
        checks.pop(0)
    elif mutation == "duplicate":
        checks.append(checks[0])
    elif mutation == "false_check":
        facts[0]["value"] += 1
    else:
        checks = [row for row in checks if not row["is_domestic_carrier"]]
    with pytest.raises(ValueError, match="TOTAL"):
        market_cells(facts, checks, 2019, 12, {})


def test_market_rejects_legacy_mixed_total_and_missing_native_total(tmp_path):
    path = tmp_path / "market.duckdb"
    with duckdb.connect(str(path)) as db:
        db.execute(
            "CREATE TABLE v_carrier_default AS SELECT 'AEROMEXICO' carrier_key, '2026M09' period_id, "
            "'total' segment, 100.0 AS value, 'passengers_afac' metric_key, "
            "'month' period_type, '' derivation_formula"
        )
        db.execute("CREATE TABLE dim_source_artifact(source_system VARCHAR, downloaded_at TIMESTAMP)")
    with pytest.raises(ValueError, match="TOTAL missing"):
        build_market_payload(str(path))
    with duckdb.connect(str(path)) as db:
        db.execute(
            "INSERT INTO v_carrier_default SELECT 'MARKET_TOTAL_MX',period_id,segment,200,"
            "metric_key,period_type,"
            "'SUM(all passengers)' FROM v_carrier_default"
        )
    with pytest.raises(ValueError, match="lacks verified native scope"):
        build_market_payload(str(path))


@pytest.mark.parametrize("timestamp_type", ["TIMESTAMPTZ", "TIMESTAMP"])
def test_market_capture_date_is_utc_even_in_mexico_session(tmp_path, monkeypatch, timestamp_type):
    path = tmp_path / "utc.duckdb"
    with duckdb.connect(str(path)) as db:
        db.execute(
            "CREATE TABLE v_carrier_default(carrier_key VARCHAR,period_id VARCHAR,segment VARCHAR,"
            "value DOUBLE,metric_key VARCHAR,period_type VARCHAR,derivation_formula VARCHAR)"
        )
        for month in range(1, 4):
            for segment in ("domestic", "international", "total"):
                for key, value in (
                    ("AEROMEXICO", 10),
                    ("VOLARIS", 20),
                    ("VIVA_AEROBUS", 30),
                    (TOTAL_KEY, 100),
                ):
                    db.execute(
                        "INSERT INTO v_carrier_default VALUES(?,?,?,?,'passengers_afac','month',?)",
                        [key, f"2026M{month:02d}", segment, value, TOTAL_FORMULA],
                    )
        db.execute(f"CREATE TABLE dim_source_artifact(source_system VARCHAR,downloaded_at {timestamp_type})")
        db.execute("INSERT INTO dim_source_artifact VALUES('afac','2026-11-02T00:17:23+00:00')")
    connect = duckdb.connect

    def mexico(*args, **kwargs):
        db = connect(*args, **kwargs)
        db.execute("SET TimeZone='America/Mexico_City'")
        return db

    monkeypatch.setattr(duckdb, "connect", mexico)
    payload = build_market_payload(str(path))
    assert payload["metadata"]["data_as_of"] == "2026-11-02"


@pytest.mark.local_data
def test_retained_2019_2026_originals_reconcile_every_mexican_total(tmp_path):
    archive = PATHS.root.parent / "private-linux-release/snapshot/data/bronze/afac"
    current = (
        PATHS.root.parent
        / "airline-prepared-review-20261104/tmp/source-updates/public-refresh-20261101"
        / "afac-current/data/bronze/afac"
    )
    if not archive.is_dir() or not current.is_dir():
        pytest.skip("Restore the retained official AFAC originals and their capture metadata")
    # Physical TOTAL coordinates independently audited in the retained files.
    total_rows = {
        2019: (16, 29, 13, 26),
        2020: (16, 29, 14, 28),
        2021: (18, 29, 16, 29),
        2022: (18, 29, 15, 27),
        2023: (20, 31, 19, 30),
        2024: (19, 30, 20, 32),
        2025: (18, 29, 20, 32),
        2026: (18, 29, 19, 32),
    }
    baseline = {"months": []}
    all_cells, sources = {}, {}
    checked = 0
    for year in range(2019, 2027):
        path = (
            next((archive / str(year)).glob("*.xlsx"))
            if year < 2026
            else next(current.glob("*carriers-sep*.xlsx"))
        )
        metadata = json.loads(path.with_suffix(".xlsx.meta.json").read_bytes())
        assert hashlib.sha256(path.read_bytes()).hexdigest() == metadata["sha256"]
        facts, checks = parse_annual_passenger_workbook(path, year)
        through = 9 if year == 2026 else 12
        cells, receipt = market_cells(facts, checks, year, through, _load_crosswalk())
        all_cells.update(cells)
        sources[year] = {
            "sha256": metadata["sha256"],
            "downloaded_at": metadata["downloaded_at"],
            "through": through,
        }
        assert receipt["total_formula"] == TOTAL_FORMULA
        book = openpyxl.load_workbook(path, read_only=True, data_only=True)
        try:
            for month in range(1, through + 1):
                domestic = sum(
                    book[sheet].cell(row, month + 1).value
                    for sheet, row in zip(("PAXREG", "PAXFLET"), total_rows[year][::2], strict=True)
                )
                international = sum(
                    book[sheet].cell(row, month + 1).value
                    for sheet, row in zip(("PAXREG", "PAXFLET"), total_rows[year][1::2], strict=True)
                )
                for segment, expected in (
                    ("domestic", domestic),
                    ("international", international),
                    ("total", domestic + international),
                ):
                    assert cells[TOTAL_KEY, f"{year}M{month:02d}", segment] == expected
                    checked += 1
        finally:
            book.close()
        baseline, proof = build(
            baseline, path, year, through, metadata["downloaded_at"], tmp_path / "market.duckdb"
        )
        assert proof["all_reconciled"]
    assert checked == 279
    january = baseline["months"][0]["segments"]
    assert january["domestic"]["carriers"]["AEROMEXICO"]["passengers"] == 1_058_787
    assert january["international"]["carriers"]["AEROMEXICO"]["passengers"] == 677_190
    assert baseline["metadata"]["last_period"] == "2026M09"
    assert baseline["metadata"]["default_quarter"] == "2026Q3"
    from src.publish.afac_native_monthly import project_monthly_series

    before = json.loads((PATHS.root / "site/data/v1/flights/quarters.json").read_bytes())
    after = project_monthly_series(before, all_cells, sources)
    assert len(after["monthly_passengers"]["records"]) == 141
    assert after["monthly_passengers"]["records"][-1]["period_id"] == "2026M09"
    unchanged = [
        row
        for row in before["monthly_passengers"]["records"]
        if row["period_id"] < "2019M01" or row["period_id"].startswith("2026")
    ]
    projected = {row["period_id"]: row for row in after["monthly_passengers"]["records"]}
    assert all(projected[row["period_id"]] == row for row in unchanged)
    assert {k: v for k, v in after.items() if k != "monthly_passengers"} == {
        k: v for k, v in before.items() if k != "monthly_passengers"
    }
    assert project_monthly_series(after, all_cells, sources) == after
