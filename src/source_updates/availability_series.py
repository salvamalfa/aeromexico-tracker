"""Current canonical series responses; completeness of observation calendars remains separate."""

import json
from pathlib import Path

import pandas as pd

from src.ingest.macro.banxico import BANXICO_SERIES
from src.ingest.market.prices import TICKERS
from src.source_updates import availability as physical
from src.source_updates.catalog import bronze_aliases, load_catalog, product_map
from src.source_updates.recipes import macro_round


def role_sets():
    return dict(banxico=set(BANXICO_SERIES), fuel={"workbook"}, equities=set(TICKERS))


def verify(item, result, cutoff):
    product = item["product"]
    binding = item["availability"]
    root = physical.preflight(binding, item["workspace"])
    if set(binding) != physical.SERIES_FIELDS or set(binding["series_items"]) != role_sets()[product]:
        raise ValueError("Series physical roles must match this product, not another series family")
    before = physical.collection_inventory(root)
    receipt_path = root / "receipts" / f"collection-{binding['run_id']}.json"
    receipt_hash = physical.sha(receipt_path)
    receipt = json.loads(receipt_path.read_text())
    expected = dict(
        run_id=binding["run_id"],
        mode="collection",
        status="collected_unvalidated",
        activation="none",
        publication="not_authorized",
    )
    rows = receipt.get("items", [])
    if any(receipt.get(k) != v for k, v in expected.items()) or len(rows) != len(binding["series_items"]):
        raise ValueError("Series availability requires a complete successful canonical collection")
    manifest = [json.loads(line) for line in (root / "data/bronze/_manifest.jsonl").read_text().splitlines()]
    if (
        len(manifest) != len(rows)
        or len({r["source_file"] for r in manifest}) != len(rows)
        or ({r["source_file"] for r in manifest} != {r.get("source_file") for r in rows})
    ):
        raise ValueError("Series collection manifest must identify exactly its unique query captures")
    planned = macro_round(product, item["period"], cutoff)["selection"]["items"]
    targets = {
        "workbook" if product == "fuel" else row["entity"].removesuffix("_chart"): row for row in planned
    }
    source = load_catalog()[product_map()[product]["source_key"]]
    table, column = {
        "fuel": ("fuel_prices", "series_id"),
        "banxico": ("macro_indicators", "series_id"),
        "equities": ("market_prices", "ticker"),
    }[product]
    native = pd.read_parquet(Path(item["workspace"]) / "data/silver" / (table + ".parquet"))
    if not {column, "source_file", "source_hash", "source_system"} <= set(native):
        raise ValueError("Series native table lacks query identity and physical provenance")
    captured = []
    for role, identifier in binding["series_items"].items():
        selected = [r for r in rows if r.get("id") == identifier]
        if len(selected) != 1:
            raise ValueError("Series acquisition item absent or duplicated")
        row = selected[0]
        target = targets[role]
        if (
            row.get("product") != product
            or row.get("status") != "collected_unvalidated"
            or row.get("id") != target["id"]
            or row.get("requested_period") != target["period"]
            or any(row.get(k) != target["url"] for k in ("source_url", "response_url"))
            or product == "banxico"
            and row.get("public_request_form") != target["public_form"]
        ):
            raise ValueError("Series response differs from its canonical product/window/request form")
        path, record = physical.artifact(
            root, row, cutoff, source["allowed_hosts"], receipt, bronze_aliases(product)
        )
        key = f"{target['source_system']}|{target['entity']}|{target['period']}|{target['extension']}"
        expected_role = target["entity"] if product == "fuel" else role
        observed = native.loc[native[column].eq(expected_role)]
        if (
            record["logical_key"] != key
            or observed.empty
            or set(observed.source_file) != {row["source_file"]}
            or set(observed.source_hash) != {row["sha256"]}
            or set(observed.source_system) != {target["source_system"]}
        ):
            raise ValueError("Series native observations do not bind the actual canonical query response")
        captured.append(
            dict(
                role=role,
                source_file=row["source_file"],
                sha256=row["sha256"],
                source_url=row["source_url"],
                captured_at=record["downloaded_at"],
            )
        )
    expected_native = {targets[k]["entity"] if product == "fuel" else k for k in targets}
    if (
        set(native[column]) != expected_native
        or result.get("calendar_completeness_certified") is not False
        or (
            result.get("scope")
            != "all_observations_in_selected_retained_originals_not_verified_publication_calendar"
        )
    ):
        raise ValueError("Series source coverage or unverified publication-calendar limit changed")
    if physical.sha(receipt_path) != receipt_hash or physical.collection_inventory(root) != before:
        raise ValueError("Series physical query collection changed during verification")
    return dict(
        collection_receipt_sha256=receipt_hash,
        physical_collection_files=before,
        responses=captured,
        discovery_contract_product=product,
        review_period=item["period"],
        latest_available_period=None,
        first_publication_date=None,
        round_as_of=cutoff,
        calendar_completeness_certified=False,
        availability_basis="current_canonical_historical_window_responses_not_expected_calendar",
        identity_basis="existing_verified_SEC_original_not_a_fresh_SEC_capture"
        if product == "equities"
        else None,
    )
