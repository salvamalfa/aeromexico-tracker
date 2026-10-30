"""The legacy coverage CLI must preserve modern flight component semantics."""

import json

import pandas as pd
import pytest

from scripts.research import flight_coverage as coverage


def component(kind, departures, month, **extra):
    return dict(
        carrier_key="VOLARIS",
        origin_iata="GDL",
        destination_iata="LAX",
        period_id=month,
        kind=kind,
        departures=departures,
        source_label="Estados Unidos · BTS T-100" if kind == "observed" else "Retained estimate",
        source_hashes=["source-bts"] if kind == "observed" else [],
        **extra,
    )


def run_audit(tmp_path, monkeypatch, components, displayed, *, gold_cells=None):
    base = tmp_path / "site/data/v1/flights"
    folder = base / "entities/VOLARIS/international"
    folder.mkdir(parents=True)
    (base / "quarters.json").write_text(json.dumps({"quarters": [{"period_id": "2026Q2"}]}))
    route = dict(
        market_key="GDL<>LAX",
        departures=displayed,
        operation_status="mixed_observed_estimated_cells",
        flight_components=components,
    )
    (folder / "2026Q2.json").write_text(json.dumps({"routes": [route]}))
    gold = tmp_path / "gold"
    gold.mkdir()
    source_rows = [("2026M04", "F", 80), ("2026M04", "L", 20)] if gold_cells is None else gold_cells
    pd.DataFrame(
        [
            dict(
                carrier_key="VOLARIS",
                route_key="r",
                period_id=month,
                service_class=service,
                departures_performed=value,
                source_system="bts_t100",
                source_hash="source-bts",
            )
            for month, service, value in source_rows
        ],
        columns=[
            "carrier_key",
            "route_key",
            "period_id",
            "service_class",
            "departures_performed",
            "source_system",
            "source_hash",
        ],
    ).to_parquet(gold / "fact_route_traffic.parquet")
    pd.DataFrame([dict(route_key="r", market_key="GDL<>LAX", origin_iata="GDL", dest_iata="LAX")]).to_parquet(
        gold / "dim_route.parquet"
    )
    pd.DataFrame(
        [
            dict(
                source_system="aerocivil",
                operator_icao="AMX",
                period_id="2026M04",
                origin_iata="MEX",
                dest_iata="BOG",
                departures=1,
                source_hash="authority-source",
            )
        ]
    ).to_parquet(gold / "fact_international_route_observations.parquet")
    official = {("VOLARIS", "international", f"2026M{month:02d}"): 100 for month in (4, 5, 6)}
    rows = coverage.audit(tmp_path / "site", official, tmp_path / "gold")
    return {
        row["kind"]: row for row in rows if row["entity"] == "VOLARIS" and row["scope"] == "international"
    }


def test_legacy_audit_splits_observed_estimated_and_scheduled_cells(tmp_path, monkeypatch):
    cells = [
        component("observed", 100, "2026M04", service_class_departures={"F": 80, "L": 20}),
        component("estimated", 20, "2026M05"),
        component("scheduled", 50, "2026M06"),
    ]
    rows = run_audit(tmp_path, monkeypatch, cells, 120)
    assert rows["observed"]["map_flights"] == 100
    assert rows["estimated"]["map_flights"] == 20
    assert rows["scheduled"]["map_flights"] == 50
    assert rows["observed"]["comparable_observed_regular_flights"] == 80
    assert rows["observed"]["represented_months"] == "2026M04"
    assert rows["estimated"]["represented_months"] == "2026M05"
    assert rows["observed"]["mapped_route_records"] == 1
    assert coverage.flight_kind(dict(departures=120, flight_components=cells)) == "mixed"


def test_observed_zero_remains_known_beside_other_month_estimate(tmp_path, monkeypatch):
    rows = run_audit(
        tmp_path,
        monkeypatch,
        [
            component("observed", 0, "2026M04", service_class_departures={"F": 0}),
            component("estimated", 20, "2026M05"),
        ],
        20,
        gold_cells=[("2026M04", "F", 0)],
    )
    assert rows["observed"]["map_flights"] == 0
    assert rows["observed"]["comparable_observed_regular_flights"] == 0
    assert rows["observed"]["observed_minimum_quarter_pct"] == 0
    assert rows["estimated"]["map_flights"] == 20


def test_mixed_without_components_fails_explicitly():
    with pytest.raises(ValueError, match="requires flight_components"):
        coverage.flight_kind(dict(departures=120, operation_status="mixed_observed_estimated_cells"))


def test_bts_component_without_class_detail_fails_instead_of_using_market_total(tmp_path, monkeypatch):
    with pytest.raises(ValueError, match="reconciled service-class"):
        run_audit(
            tmp_path,
            monkeypatch,
            [component("observed", 100, "2026M04"), component("estimated", 20, "2026M05")],
            120,
        )


@pytest.mark.parametrize(
    "change, message",
    [
        ("overlap", "Duplicate or overlapping"),
        ("total", "component total"),
        ("month", "requested period"),
        ("classes", "reconciled service-class"),
    ],
)
def test_component_audit_rejects_inconsistent_provenance(tmp_path, monkeypatch, change, message):
    observed = component("observed", 100, "2026M04", service_class_departures={"F": 80, "G": 10, "P": 10})
    estimated = component("estimated", 20, "2026M05")
    displayed = 120
    if change == "overlap":
        estimated["period_id"] = "2026M04"
    elif change == "total":
        displayed = 125
    elif change == "month":
        estimated["period_id"] = "2026M07"
    else:
        observed["service_class_departures"] = {"F": 99}
    with pytest.raises(ValueError, match=message):
        run_audit(tmp_path, monkeypatch, [observed, estimated], displayed)


@pytest.mark.parametrize(
    "change, message",
    [
        ("count", "count/classes differ"),
        ("class", "count/classes differ"),
        ("hash", "hashes differ"),
        ("carrier", "operator differs"),
        ("direction", "lacks matching"),
        ("missing", "lacks matching"),
    ],
)
def test_component_must_match_authoritative_gold_grain(tmp_path, monkeypatch, change, message):
    c = component("observed", 100, "2026M04", service_class_departures={"F": 80, "L": 20})
    kwargs = {}
    if change == "count":
        c["departures"] = 99
        c["service_class_departures"] = {"F": 79, "L": 20}
    elif change == "class":
        c["service_class_departures"] = {"F": 100}
    elif change == "hash":
        c["source_hashes"] = ["false-source-hash"]
    elif change == "carrier":
        c["carrier_key"] = "AEROMEXICO"
    elif change == "direction":
        c["origin_iata"], c["destination_iata"] = "LAX", "GDL"
    else:
        kwargs["gold_cells"] = []
    with pytest.raises(ValueError, match=message):
        run_audit(tmp_path, monkeypatch, [c], c["departures"], **kwargs)


def test_direct_component_call_without_gold_never_self_certifies():
    c = component("observed", 100, "2026M04", service_class_departures={"F": 80, "L": 20})
    with pytest.raises(ValueError, match="lacks matching authoritative Gold"):
        coverage.regular_observed(
            {"_flight_component": c, "source_label": c["source_label"]},
            ["2026M04"],
            "VOLARIS",
            {},
            pd.DataFrame(),
        )


@pytest.mark.parametrize("change", [None, "count", "hash", "direction", "operator"])
def test_aerocivil_component_is_reconciled_to_authoritative_direction_and_operator(change):
    c = dict(
        carrier_key="AEROMEXICO",
        origin_iata="MEX",
        destination_iata="BOG",
        period_id="2026M04",
        kind="observed",
        departures=80,
        source_label="Colombia · Aerocivil",
        source_hashes=["authority-source"],
    )
    observations = pd.DataFrame(
        [
            dict(
                source_system="aerocivil",
                operator_icao="AMX",
                origin_iata="MEX",
                dest_iata="BOG",
                period_id="2026M04",
                departures=80,
                source_hash="authority-source",
            )
        ]
    )
    if change == "count":
        c["departures"] = 81
    elif change == "hash":
        c["source_hashes"] = ["false-hash"]
    elif change == "direction":
        c["origin_iata"], c["destination_iata"] = "BOG", "MEX"
    elif change == "operator":
        c["carrier_key"] = "AEROMEXICO_CONNECT"
    part = {"_flight_component": c, "source_label": c["source_label"]}
    with pytest.raises(ValueError, match="movements.*not.*departures"):
        coverage.regular_observed(part, ["2026M04"], "AEROMEXICO", {}, observations)
