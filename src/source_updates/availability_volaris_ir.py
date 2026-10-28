"""Availability of the exact authorized issuer PDF, not a dynamic-index crawl."""

import json
from pathlib import Path

import pandas as pd
from bs4 import BeautifulSoup

from src.source_updates import availability as physical
from src.source_updates.availability_oma_newsroom import latest_closed_month
from src.source_updates.calendar import local_time
from src.source_updates.volaris_traffic import ENTRY, PDF, PERIOD, PRODUCT, TABLE, parse
from src.transform.stage9_lineage import add_record_ids


def verify(item, result, cutoff):
    if (item["product"], item["adapter"], item["period"]) != (PRODUCT, "retained", PERIOD):
        raise ValueError("Volaris IR availability supports only its authorized September2026 report")
    binding = item["availability"]
    root = physical.preflight(binding, item["workspace"])
    if set(binding) != physical.FIELDS or binding["catalog_item"] == binding["artifact_item"]:
        raise ValueError("Volaris IR needs distinct exact page/PDF collection roles")
    before = physical.collection_inventory(root)
    receipt_path = root / "receipts" / f"collection-{binding['run_id']}.json"
    receipt_sha = physical.sha(receipt_path)
    receipt = json.loads(receipt_path.read_text())
    expected = dict(
        run_id=binding["run_id"],
        mode="collection",
        status="collected_unvalidated",
        activation="none",
        publication="not_authorized",
    )
    if any(receipt.get(k) != v for k, v in expected.items()) or len(receipt.get("items", [])) != 2:
        raise ValueError("Volaris IR requires its complete two-original collection")
    selected = []
    for field, status in (("catalog_item", "collected_catalog"), ("artifact_item", "collected_unvalidated")):
        rows = [r for r in receipt["items"] if r.get("id") == binding[field]]
        if len(rows) != 1 or rows[0].get("product") != PRODUCT or rows[0].get("status") != status:
            raise ValueError("Volaris IR physical acquisition role/product/status differs")
        selected.append(rows[0])
    index, data = selected
    index_path, index_record = physical.artifact(
        root, index, cutoff, ["ir.volaris.com"], receipt, {"volaris_ir"}
    )
    data_path, data_record = physical.artifact(
        root, data, cutoff, ["filemanager-cdn.mziq.com"], receipt, {"volaris_ir"}
    )
    if (
        any(index.get(k) != ENTRY for k in ("source_url", "response_url"))
        or any(data.get(k) != PDF for k in ("source_url", "response_url"))
        or index.get("requested_period") != "current"
        or data.get("requested_period") != PERIOD
        or latest_closed_month(cutoff) != PERIOD
        or local_time(index_record["downloaded_at"]) > local_time(data_record["downloaded_at"])
    ):
        raise ValueError("Volaris IR requires exact approved origins and latest closed target month")
    soup = BeautifulSoup(index_path.read_bytes(), "html.parser")
    if (
        not soup.title
        or soup.title.get_text(strip=True) != "Reportes de tráfico - Volaris RI"
        or soup.find("base", href=True)
        or "ea52c1bb-e8e2-457e-820a-98ca17753a37" not in index_path.read_text()
    ):
        raise ValueError("Volaris official issuer page identity changed")
    frame, details = parse({"pdf": (data_path.read_bytes(), data_record)}, PERIOD)
    frame = add_record_ids(
        frame,
        table_name=TABLE,
        natural_key_columns=["source_hash", "source_locator", "parser_version", "period_id", "metric_key"],
    )
    native = pd.read_parquet(Path(item["workspace"]) / f"data/silver/source_products/{PRODUCT}.parquet")
    if set(frame) != set(native):
        raise ValueError("Volaris IR native schema differs from complete authorized PDF replay")
    try:
        pd.testing.assert_frame_equal(native[list(frame)], frame, check_exact=True)
    except AssertionError as exc:
        raise ValueError("Volaris IR native observations differ from exact physical PDF replay") from exc
    if (
        result.get("complete_month_certified") is not True
        or result.get("source_report_date_as_reported") != details["source_report_date_as_reported"]
        or physical.collection_inventory(root) != before
    ):
        raise ValueError("Volaris IR completeness, report date or immutable source collection differs")
    return dict(
        discovery_contract_product=PRODUCT,
        collection_receipt_sha256=receipt_sha,
        official_index_sha256=index["sha256"],
        source_artifact_sha256=data["sha256"],
        source_artifact_url=PDF,
        discovery_url=ENTRY,
        latest_available_period=PERIOD,
        source_availability_observed_at=data_record["downloaded_at"],
        round_as_of=cutoff,
        source_report_date_as_reported=details["source_report_date_as_reported"],
        availability_basis="exact_explicitly_authorized_official_issuer_report_for_latest_closed_month",
        dynamic_index_link_to_document_verified=False,
        automatic_new_document_discovery=False,
        all_sites_latest_revision_census=False,
        first_publication_date=None,
        publication_time=None,
        release_lag_days=None,
        physical_collection_files=before,
    )
