"""Current monthly traffic index and separately attributed official IR6-K99.4."""

import json
from pathlib import Path

import pandas as pd

from src.source_updates import availability as physical
from src.source_updates.am_traffic import ENTRY, latest
from src.source_updates.am_traffic_html import DAY, KEY, PERIOD, URL, parse
from src.source_updates.calendar import local_time


def verify(item, result, cutoff):
    if (item["product"], item["adapter"], item["period"]) != ("am_traffic_ir", "am_traffic_ir", PERIOD):
        raise ValueError("HTML monthly traffic availability supports only reviewed September2026")
    binding = item["availability"]
    root = physical.preflight(binding, item["workspace"])
    if set(binding) != physical.FIELDS or binding["run_id"] != item["receipt_id"]:
        raise ValueError("Traffic HTML requires its exact paired physical collection binding")
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
        raise ValueError("Traffic HTML needs one complete index-and-native collection")
    selected = []
    for field, status in (("catalog_item", "collected_catalog"), ("artifact_item", "collected_unvalidated")):
        rows = [r for r in receipt["items"] if r.get("id") == binding[field]]
        if len(rows) != 1 or rows[0].get("product") != "am_traffic_ir" or rows[0].get("status") != status:
            raise ValueError("Traffic paired acquisition role/product/status changed")
        selected.append(rows[0])
    index, data = selected
    index_path, index_row = physical.artifact(
        root, index, cutoff, ["ir.aeromexico.com"], receipt, {"aeromexico_ir"}
    )
    data_path, data_row = physical.artifact(
        root, data, cutoff, ["ir.aeromexico.com"], receipt, {"aeromexico_ir"}
    )
    if (
        any(index.get(k) != ENTRY for k in ("source_url", "response_url"))
        or index.get("requested_period") != "current"
        or index_row.get("logical_key") != "aeromexico_ir|am_traffic_ir_catalog|current|html"
        or data.get("requested_period") != PERIOD
        or any(data.get(k) != URL for k in ("source_url", "response_url"))
        or data_row.get("logical_key") != KEY
        or local_time(index_row["downloaded_at"]) > local_time(data_row["downloaded_at"])
        or result.get("collection_receipt_sha256") != receipt_sha
    ):
        raise ValueError("Traffic HTML index/native identity or actual chronology differs")
    period, announced_pdf = latest(index_path)
    if period != PERIOD:
        raise ValueError("September native report is not the current official indexed traffic month")
    frame, _ = parse(data_path.read_bytes(), PERIOD, data_row)
    candidate_receipt = Path(item["workspace"]) / "receipts" / f"collection-{item['receipt_id']}.json"
    if physical.sha(candidate_receipt) != receipt_sha:
        raise ValueError("Traffic candidate does not preserve its original paired collection receipt")
    native = pd.read_parquet(Path(item["workspace"]) / "data/silver/aeromexico_ir_monthly_metrics.parquet")
    if len(native) != 24 or not set(frame.columns) <= set(native):
        raise ValueError("Traffic HTML requires exactly24 native monthly/comparative observations")
    try:
        pd.testing.assert_frame_equal(native[list(frame.columns)], frame, check_exact=True)
    except AssertionError as exc:
        raise ValueError("Traffic HTML observations differ from exact physical99.4 replay") from exc
    if (
        result.get("complete_month_certified") is not True
        or result.get("source_format") != "official_IR_HTML_6K_Ex99.4"
        or result.get("source_report_date_as_reported") != DAY
        or result.get("source_preliminary_status") != "not_stated"
        or result.get("source_preliminary", "missing") is not None
    ):
        raise ValueError(
            "Traffic HTML evidence must preserve monthly completeness and unknown preliminary status"
        )
    if physical.sha(receipt_path) != receipt_sha or physical.collection_inventory(root) != before:
        raise ValueError("Traffic official source collection changed during verification")
    return dict(
        discovery_contract_product="am_traffic_ir",
        collection_receipt_sha256=receipt_sha,
        discovery_url=ENTRY,
        official_index_sha256=index["sha256"],
        source_artifact_sha256=data["sha256"],
        source_artifact_url=URL,
        announced_pdf_url=announced_pdf,
        latest_available_period=PERIOD,
        source_availability_observed_at=data_row["downloaded_at"],
        round_as_of=cutoff,
        source_report_date_as_reported=DAY,
        financial_cover_date_used_as_traffic_date=False,
        availability_basis="current_official_traffic_index_month_and_attributed_official_IR_6K_Ex99.4",
        direct_index_link_to_native_artifact=False,
        PDF_byte_equivalence_claimed=False,
        first_publication_date=None,
        publication_time=None,
        release_lag_days=None,
        physical_collection_files=before,
    )
