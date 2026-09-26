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
    paris = by_market["CDG<>MTY"]
    assert paris["departures"] == 68
    assert paris["operation_status"] == "scheduled_from_dated_release"
    assert {direction["departures"] for direction in paris["directions"]} == {34}
    madrid = by_market["MAD<>MTY"]
    assert madrid["departures"] is None
    assert madrid["operation_status"] == "documented_operating_route_count_unavailable"
