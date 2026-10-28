"""Product boundaries and canonical query settings shared by acquisition adapters."""

import shutil
from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs, urlsplit
from uuid import uuid4

import pandas as pd
import pytest

from src.common.storage import save_bronze
from src.source_updates.build import GRANULAR
from src.source_updates.catalog import ROOT, bronze_aliases, load_catalog
from src.source_updates.checks import check_candidate
from src.source_updates.recipes import catalog_selection


def test_airport_input_accepts_original_sec_aliases_and_excludes_derivatives():
    declared = set(load_catalog()["sec_edgar"]["source_systems"])
    supported = set(GRANULAR["parse.airports"][1])
    originals = {"sec", "sec_edgar", "sec_filing"}
    derivatives = {"asur_visible_reconstruction", "volaris_visible_reconstruction"}
    assert originals | derivatives <= declared
    assert originals <= supported and not derivatives & supported
    for product in ("gap_traffic", "asur_traffic"):
        assert set(bronze_aliases(product)) == originals


@pytest.mark.parametrize(("actual", "claimed"), [("ASUR", "GAP"), ("GAP", "ASUR")])
def test_group_product_cannot_validate_another_groups_airport_rows(actual, claimed):
    work = ROOT / "tmp/source-updates" / ("product-test-" + uuid4().hex)
    try:
        bronze = work / "data/bronze"
        path = save_bronze(
            b"{}",
            "sec_edgar",
            actual,
            "2026M09",
            "json",
            "https://www.sec.gov/Archives/synthetic-fixture",
            "manual",
            bronze_root=bronze,
        )
        import json

        metadata = json.loads(path.with_suffix(path.suffix + ".meta.json").read_text())
        frame = pd.DataFrame(
            [
                {
                    "period_id": "2026M09",
                    "airport_iata": "CUN",
                    "airport_name": "Fixture",
                    "operator_group": actual,
                    "passengers_total": 10,
                    "is_group_total": False,
                    "source_system": "sec_edgar",
                    "source_file": path.relative_to(bronze).as_posix(),
                    "source_hash": metadata["sha256"],
                    "ingested_at": datetime.now(UTC),
                    "parser_version": "synthetic_fixture",
                }
            ]
        )
        (work / "data/silver").mkdir()
        frame.to_parquet(work / "data/silver/airport_traffic.parquet")
        item = {
            "product": claimed.lower() + "_traffic",
            "layer": "silver",
            "table": "airport_traffic",
            "expected_period": "2026M09",
            "value_columns": ["passengers_total"],
        }
        spec = {"as_of": (datetime.now(UTC) + timedelta(minutes=1)).isoformat(), "checks": [item]}
        absent = check_candidate(work, spec)
        assert absent["status"] == "blocked"
        assert "operator_group=" + claimed in absent["checks"][0]["reason"]
        item["filters"] = {"operator_group": claimed}
        assert check_candidate(work, spec)["status"] == "blocked"
        item.update(product=actual.lower() + "_traffic", filters={"operator_group": actual})
        assert check_candidate(work, spec)["status"] == "checks_passed"
    finally:
        shutil.rmtree(work)


def test_gdelt_selection_uses_canonical_complete_query():
    selected = catalog_selection("gdelt")["items"][0]
    assert parse_qs(urlsplit(selected["url"]).query) == {
        "query": ['(Aeromexico OR "Aeroméxico" OR "Viva Aerobus" OR Volaris)'],
        "mode": ["artlist"],
        "maxrecords": ["250"],
        "format": ["json"],
        "sort": ["datedesc"],
    }
