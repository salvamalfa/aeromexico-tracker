"""Project a certified ANAC edition through the existing Vuelos generators.

Uses the existing normalizer, lineage validator, flight-cell resolver and web
export validators on a pinned baseline. Does not fit models,
change historical eligibility, install a preview, or write active Gold/site/.
"""

import argparse
import hashlib
import json
import re
from copy import deepcopy
from pathlib import Path

import duckdb
import pandas as pd

from src.dashboard.flight_cells import international_cells, resolve_cells
from src.dashboard.map_periods import period_label, period_months
from src.dashboard.route_entities import AEROMEXICO_ROUTES, INDUSTRY_ROUTES
from src.ingest.stage4_common import write_parquet_atomic
from src.source_updates.authorities import json_objects
from src.source_updates.collection import safe_workspace
from src.source_updates.retained import run
from src.transform.international_routes import TABLE, normalize, validate
from src.transform.stage9_lineage import (
    LineageSpec,
    add_record_ids,
    build_bridge_record_lineage,
    build_dim_source_artifact,
)
from src.transform.validate_stage9 import validate_lineage_frames
from src.web_export.flights import _validate
from src.web_export.observed_refresh import refresh_observed_network
from src.web_export.privacy import check_privacy, load_privacy_rules
from src.web_export.schemas import NETWORK_FILE_SCHEMA, QUARTERS_FILE_SCHEMA
from src.web_export.writer import write_json


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def checked_months(quarter, period):
    if not re.fullmatch(r"\d{4}Q[1-4]", quarter):
        raise ValueError("Select an explicit quarter")
    months = period_months(quarter)
    if quarter[:4] != period[:4] or months[-1] > period:
        raise ValueError("Quarter must be fully within the certified source year and availability")
    return months


def resolve_revision(network, current):
    existing = [
        cell
        for route in network["routes"]
        for cell in route.get("flight_components", [])
        if cell.get("source_label") != "Brasil · ANAC"
    ]
    resolved = resolve_cells([*existing, *current])
    # The generic updater changes only markets present in its input. Reject
    # removals needing an explicit missing-value review instead of retaining a
    # stale market total or manufacturing a zero observation.
    old_markets = {
        (cell["origin_iata"], cell["destination_iata"])
        for route in network["routes"]
        for cell in route.get("flight_components", [])
        if cell.get("source_label") == "Brasil · ANAC"
    }
    resolved_markets = {(cell["origin_iata"], cell["destination_iata"]) for cell in resolved}
    if old_markets - resolved_markets:
        raise ValueError("ANAC revision removes a market; explicit missing-value review required")
    return resolved


def build(candidate, baseline_data, out, quarter):
    candidate, out = safe_workspace(candidate), safe_workspace(out)
    receipts = list((candidate / "receipts").glob("certified-anac-*.json"))
    if len(receipts) != 1:
        raise ValueError("Select one certified ANAC candidate and one explicit quarter")
    receipt = json.loads(receipts[0].read_bytes())
    period = receipt["requested_period"]
    months = checked_months(quarter, period)
    run(candidate, "anac", period, receipt["effective_as_of"], receipt["retention_run_id"], check=True)
    if out.exists() and any(out.iterdir()):
        raise ValueError("Use a new isolated review directory")
    out.mkdir(parents=True, exist_ok=True)
    dimension_path = Path("data/gold/dim_airport.parquet")
    original = json.loads(next((candidate / "receipts").glob("retained-*.json")).read_bytes())["originals"][
        "json"
    ]
    raw = candidate / "data/bronze" / original["source_file"]
    if sha(raw) != original["sha256"]:
        raise ValueError("Certified ANAC original changed")
    with duckdb.connect() as connection:
        connection.execute("CREATE TABLE dim_airport AS SELECT * FROM read_parquet(?)", [str(dimension_path)])
        airports = {
            row["airport_icao"]: row
            for row in connection.execute("SELECT * FROM dim_airport").df().to_dict("records")
            if row["airport_icao"]
        }
        artifact = dict(
            file=original["source_file"],
            sha256=original["sha256"],
            url=original["source_url"],
            downloaded_at=original["downloaded_at"],
        )
        rows = normalize("anac", [row for _, row in json_objects(raw.read_bytes())], artifact, airports)
        frame = pd.DataFrame(rows)
        frame = frame[frame.period_id.str.startswith(period[:4])].copy()
        for key in ("passengers", "seats", "departures", "operations", "load_factor"):
            frame[key] = pd.to_numeric(frame[key], errors="raise").astype(float)
        validate(frame)
        record_grain = ["source_hash", "source_locator", "parser_version"]
        frame = add_record_ids(
            frame.drop(columns="record_id"), table_name=TABLE, natural_key_columns=record_grain
        )
        native = pd.read_parquet(candidate / "data/gold/fact_anac_retained_observations.parquet")
        for metric, field in (
            ("paid_passengers", "passengers"),
            ("seats_as_reported", "seats"),
            ("departures_as_reported", "departures"),
        ):
            left = (
                native[native.metric_key.eq(metric)]
                .set_index(["period_id", "airport_base_as_reported", "counterpart_as_reported"])["value"]
                .sort_index()
                .astype(float)
            )
            right = frame.set_index(["period_id", "origin_icao", "dest_icao"])[field].sort_index()
            if list(left.index) != list(right.index) or not (left.to_numpy() == right.to_numpy()).all():
                raise ValueError("Dashboard normalization differs from the fully certified native ANAC cells")
        silver = out / "data/silver/international_routes/observations.parquet"
        write_parquet_atomic(frame, silver)
        gold = pd.read_parquet(silver)
        validate(gold)
        artifacts = build_dim_source_artifact(candidate / "data/bronze/_manifest.jsonl", verify_files=True)
        bridge = build_bridge_record_lineage(
            [
                LineageSpec(
                    record_id=row.record_id,
                    table_name=TABLE,
                    lineage_type="direct_artifact",
                    artifact_ids=(row.artifact_id,),
                )
                for row in gold.itertuples(index=False)
            ],
            artifacts,
        )
        lineage = validate_lineage_frames(
            tables={TABLE: gold},
            artifacts=artifacts,
            bridge=bridge,
            contracts={"tables": {TABLE: {"grain": record_grain}}},
        )
        if lineage["status"] != "passed":
            raise ValueError("Dashboard ANAC lineage failed")
        write_parquet_atomic(gold, out / f"data/gold/{TABLE}.parquet")
        write_parquet_atomic(bridge, out / "data/gold/bridge_international_route_lineage.parquet")
        write_parquet_atomic(artifacts, out / "data/gold/dim_source_artifact.parquet")
        connection.register("anac_review_rows", gold)
        connection.execute(f"CREATE TABLE {TABLE} AS SELECT * FROM anac_review_rows")

        def endpoint(code):
            item = next(row for row in airports.values() if row["airport_iata"] == code)
            return dict(
                iata=code,
                name=item["name"],
                city=item["city"],
                country=item["country"],
                lat=float(item["latitude"]),
                lon=float(item["longitude"]),
            )

        paths = []
        coverage = {}
        inputs = {}
        generated_periods = {}
        for entity, prefix in (
            (AEROMEXICO_ROUTES, "flights"),
            (INDUSTRY_ROUTES, "flights/entities/INDUSTRY"),
        ):
            generated_periods[entity.key] = set()
            quarter_path = baseline_data / prefix / "international" / (quarter + ".json")
            template = json.loads(quarter_path.read_bytes())
            inputs[str(quarter_path)] = sha(quarter_path)
            for selected in [quarter, *months]:
                source_path = baseline_data / prefix / "international" / (selected + ".json")
                if source_path.is_file():
                    network = json.loads(source_path.read_bytes())
                    inputs[str(source_path)] = sha(source_path)
                else:
                    network = deepcopy(template)
                    network.update(
                        routes=[],
                        airports=[],
                        observed_months=[],
                        coverage_by_source={},
                        aena_airport_activity=[],
                        represented_movements=None,
                        represented_passengers=None,
                    )
                selected_months = period_months(selected)
                network.update(expected_months=selected_months, period_label=period_label(selected))
                current = international_cells(
                    connection, selected_months, entity, pd.DataFrame(), endpoint, authorities=gold
                )
                if not current:
                    continue
                previous_path = source_path.with_name(f"{int(selected[:4]) - 1}{selected[4:]}.json")
                previous = None
                if previous_path.is_file():
                    previous = json.loads(previous_path.read_bytes())
                    inputs[str(previous_path)] = sha(previous_path)
                endpoints = {
                    point["iata"]: point
                    for route in network["routes"]
                    for point in (route["origin"], route["destination"])
                }
                for cell in current:
                    for key in ("origin_iata", "destination_iata"):
                        endpoints[cell[key]] = endpoint(cell[key])
                network = refresh_observed_network(
                    network, current, selected_months, "Brasil · ANAC", endpoints, selected, previous
                )
                _validate(NETWORK_FILE_SCHEMA, network, what="ANAC source review")
                check_privacy(network, load_privacy_rules())
                paths.append(
                    write_json(out / "data/v1" / prefix / "international" / (selected + ".json"), network)
                )
                generated_periods[entity.key].add(selected)
                if selected == quarter:
                    coverage[entity.key] = network["coverage_by_source"]
        manifest_path = baseline_data / "flights/quarters.json"
        manifest = json.loads(manifest_path.read_bytes())
        inputs[str(manifest_path)] = sha(manifest_path)
        for entity_key, block in (
            (AEROMEXICO_ROUTES.key, manifest["available_periods"]),
            (INDUSTRY_ROUTES.key, manifest["available_periods"]["entities"]["INDUSTRY"]),
        ):
            block["international"] = sorted(set(block["international"]) | generated_periods[entity_key])
        _validate(QUARTERS_FILE_SCHEMA, manifest, what="ANAC source review manifest")
        paths.append(write_json(out / "data/v1/flights/quarters.json", manifest))
    if any(sha(Path(path)) != expected for path, expected in inputs.items()):
        raise ValueError("Baseline payload changed during source review")
    result = dict(
        status="local_review_generated_not_activated",
        product="anac",
        period=period,
        original_capture=original["downloaded_at"],
        source_receipt_sha256=sha(receipts[0]),
        baseline_data=inputs,
        airport_dimension_sha256=sha(dimension_path),
        normalized_rows=len(gold),
        lineage=lineage,
        outputs={str(path.relative_to(out)): sha(path) for path in paths},
        quarterly_coverage=coverage,
        quarter=quarter,
        code_files={
            str(path): sha(path)
            for path in (
                Path(__file__).relative_to(Path.cwd()),
                Path("src/dashboard/entity_routes.py"),
                Path("src/dashboard/flight_cells.py"),
                Path("src/dashboard/flights_html.py"),
                Path("src/dashboard/map_periods.py"),
                Path("src/transform/international_routes.py"),
                Path("src/web_export/flights.py"),
            )
        },
        activation="none",
        approval="not_created",
        publication="not_authorized",
    )
    (out / "receipt.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--baseline-data", type=Path, required=True)
    parser.add_argument("--quarter", required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    result = build(args.candidate, args.baseline_data, args.out, args.quarter)
    print(json.dumps({key: value for key, value in result.items() if key != "outputs"}, ensure_ascii=False))
