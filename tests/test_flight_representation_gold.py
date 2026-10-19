"""Candidate components cannot certify themselves against independent parquet Gold."""

from copy import deepcopy
import json

import pandas as pd
import pytest

from scripts.research.flight_representation import audit_snapshot, route_values


def _gold(tmp_path):
    root = tmp_path / "gold"
    root.mkdir(exist_ok=True)
    pd.DataFrame(
        [
            dict(
                carrier_key="VOLARIS",
                route_key="r1",
                period_id="2026M04",
                service_class=service,
                departures_performed=count,
                source_system="bts_t100",
                source_hash="bts-original",
            )
            for service, count in (("F", 80), ("L", 20))
        ]
    ).to_parquet(root / "fact_route_traffic.parquet")
    pd.DataFrame(
        [dict(route_key="r1", market_key="GDL<>LAX", origin_iata="GDL", dest_iata="LAX")]
    ).to_parquet(root / "dim_route.parquet")
    pd.DataFrame(
        [
            dict(
                source_system=system,
                operator_icao="AMX",
                origin_iata="MEX",
                dest_iata=destination,
                period_id="2026M04",
                departures=count,
                source_hash=system + "-original",
            )
            for system, destination, count in (
                ("aerocivil", "BOG", 80),
                ("anac", "GRU", 42),
                ("caa", "LHR", 10),
            )
        ]
    ).to_parquet(root / "fact_international_route_observations.parquet")
    return root


def _component(system="bts_t100"):
    if system == "bts_t100":
        return dict(
            carrier_key="VOLARIS",
            origin_iata="GDL",
            destination_iata="LAX",
            period_id="2026M04",
            kind="observed",
            departures=100,
            service_class_departures={"F": 80, "L": 20},
            source_label="Estados Unidos · BTS T-100",
            source_hashes=["bts-original"],
        )
    destination, count, label = {
        "aerocivil": ("BOG", 80, "Colombia · Aerocivil"),
        "anac": ("GRU", 42, "Brasil · ANAC"),
        "caa": ("LHR", 10, "Reino Unido · CAA"),
    }[system]
    return dict(
        carrier_key="AEROMEXICO",
        origin_iata="MEX",
        destination_iata=destination,
        period_id="2026M04",
        kind="observed",
        departures=count,
        source_label=label,
        source_hashes=[system + "-original"],
    )


def _audit(tmp_path, cell, system="bts_t100"):
    gold = _gold(tmp_path)
    entity = "VOLARIS" if system == "bts_t100" else "AEROMEXICO"
    base = tmp_path / "site/data/v1/flights"
    directory = base / ("entities/VOLARIS/international" if entity == "VOLARIS" else "international")
    directory.mkdir(parents=True, exist_ok=True)
    (base / "quarters.json").write_text("{}")
    market = "<>".join(sorted((cell["origin_iata"], cell["destination_iata"])))
    # Headline and embedded fields remain internally consistent even for forgeries.
    payload = {"routes": [dict(market_key=market, departures=cell["departures"], flight_components=[cell])]}
    (directory / "2026Q2.json").write_text(json.dumps(payload))
    rows = audit_snapshot("candidate", tmp_path / "site", gold, {}, ["2026Q2"])
    return next(row for row in rows if row["entity"] == entity and row["scope"] == "international")


@pytest.mark.parametrize(
    "system,regular", [("bts_t100", 80), ("aerocivil", 80), ("anac", None), ("caa", None)]
)
def test_authoritative_counts_pass_without_promoting_unknown_regularity(tmp_path, system, regular):
    cell = _component(system)
    row = _audit(tmp_path, cell, system)
    assert row["observed_flights"] == cell["departures"]
    assert row["strict_observed_regular_flights"] == regular


@pytest.mark.parametrize("change", ["count", "classes", "hash", "direction", "month", "operator"])
def test_internally_consistent_bts_forgery_cannot_override_gold(tmp_path, change):
    cell = _component()
    if change == "count":
        cell.update(departures=101, service_class_departures={"F": 81, "L": 20})
    elif change == "classes":
        cell["service_class_departures"] = {"F": 100}
    elif change == "hash":
        cell["source_hashes"] = ["forged"]
    elif change == "direction":
        cell["origin_iata"], cell["destination_iata"] = cell["destination_iata"], cell["origin_iata"]
    elif change == "month":
        cell["period_id"] = "2026M05"
    else:
        cell["carrier_key"] = "VIVA_AEROBUS"
    with pytest.raises(ValueError, match="Gold|Foreign operator"):
        _audit(tmp_path, cell)


@pytest.mark.parametrize("system", ["aerocivil", "anac", "caa"])
@pytest.mark.parametrize("change", ["count", "hash", "direction", "month", "operator"])
def test_authority_forgery_is_checked_by_operator_direction_month_and_hash(tmp_path, system, change):
    cell = _component(system)
    if change == "count":
        cell["departures"] += 1
    elif change == "hash":
        cell["source_hashes"] = ["forged"]
    elif change == "direction":
        cell["origin_iata"], cell["destination_iata"] = cell["destination_iata"], cell["origin_iata"]
    elif change == "month":
        cell["period_id"] = "2026M05"
    else:
        cell["carrier_key"] = "AEROMEXICO_CONNECT"
    with pytest.raises(ValueError, match="Gold|hashes"):
        _audit(tmp_path, cell, system)


def test_component_call_without_independent_gold_never_self_certifies():
    cell = _component()
    route = dict(market_key="GDL<>LAX", departures=100, flight_components=[deepcopy(cell)])
    with pytest.raises(ValueError, match="authoritative Gold"):
        route_values(route, "VOLARIS", "2026Q2", {}, {}, pd.DataFrame())
