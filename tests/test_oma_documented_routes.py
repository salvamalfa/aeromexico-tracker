"""OMA's dated route release is kept distinct from actual flight counts."""

import hashlib

import duckdb
import pandas as pd
import pytest

from src.config import PATHS
from src.transform.oma_documented_routes import GOLD, SILVER, SOURCE

pytestmark = pytest.mark.local_data


def test_oma_route_document_bronze_silver_gold_lineage():
    source_hash = hashlib.sha256(SOURCE.read_bytes()).hexdigest()
    silver = pd.read_parquet(SILVER)
    gold = pd.read_parquet(GOLD)
    assert len(silver) == len(gold) == 3
    assert gold.source_hash.eq(source_hash).all()
    assert gold.scheduled_movements.sum() == 68
    assert gold[gold.dest_iata.eq("MAD")].scheduled_movements.isna().all()
    with duckdb.connect(str(PATHS.warehouse), read_only=True) as connection:
        assert connection.execute(
            "SELECT count(*) FROM bridge_oma_documented_route_lineage WHERE artifact_sha256 = ?",
            [source_hash],
        ).fetchone()[0] == 3


def test_oma_routes_appear_without_invented_madrid_volume(flight_payload):
    network = flight_payload["international_networks"]["2026Q2"]
    by_market = {route["market_key"]: route for route in network["routes"]}
    with duckdb.connect(str(PATHS.warehouse), read_only=True) as connection:
        oma = connection.execute("SELECT * FROM fact_oma_documented_routes WHERE period_id='2026Q2'").df()
        has_estimate = connection.execute("SELECT count(*) FROM information_schema.tables WHERE table_name='fact_route_carrier_international_estimate'").fetchone()[0]
        seeds = connection.execute("""SELECT carrier_key,period_id,origin_iata,destination_iata,departures_estimated
            FROM fact_route_carrier_international_estimate
            WHERE carrier_key IN ('AEROMEXICO','AEROMEXICO_CONNECT')
              AND period_id IN ('2026M04','2026M05','2026M06')""").df() if has_estimate else pd.DataFrame(columns=[
                  "carrier_key","period_id","origin_iata","destination_iata","departures_estimated"])
    assert oma.loc[oma.dest_iata.eq("MAD"),"scheduled_movements"].isna().all()
    for market in ("CDG<>MTY", "MAD<>MTY"):
        route = by_market[market]
        assert "OMA" in route["coverage_note"]
        components = route.get("flight_components", [])
        if components:
            # A retained frequency is supported by its source cell, not by
            # OMA's release or a manufactured monthly split of that release.
            assert all(cell["kind"] == "estimated" for cell in components)
            assert route["operation_status"].startswith("estimated_")
            assert route["departures"] == sum(cell["departures"] for cell in components)
            assert sum(d["departures"] for d in route["directions"]) == route["departures"]
            seed_counts = seeds.set_index(["carrier_key","period_id","origin_iata","destination_iata"]).departures_estimated.to_dict()
            for cell in components:
                key=tuple(cell[k] for k in ("carrier_key","period_id","origin_iata","destination_iata"))
                assert cell["departures"] == pytest.approx(seed_counts[key])
                assert "OMA" not in cell["source_label"]
        elif market == "CDG<>MTY":
            assert route["operation_status"] == "scheduled_from_dated_release"
            assert route["departures"] == oma.scheduled_movements.sum()
        else:
            assert route["departures"] is None
            assert route["operation_status"] == "documented_operating_route_count_unavailable"
