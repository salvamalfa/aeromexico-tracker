"""Parse bounded BTS T-100 ZIP archives into typed silver data."""

from __future__ import annotations

from datetime import datetime
import io
import json
from pathlib import Path
import re
import zipfile

import polars as pl

from src.config import CARRIERS, PATHS
from src.parse.sec.common import read_bronze_verified, write_parquet_atomic


PARSER_VERSION = "bts_t100_v1.0.0"
NUMERIC_COLUMNS = (
    "departures_scheduled",
    "departures_performed",
    "seats",
    "passengers",
    "freight",
    "mail",
    "distance",
    "ramp_to_ramp",
    "air_time",
)


def _manifest_records() -> list[dict[str, object]]:
    path = PATHS.bronze / "_manifest.jsonl"
    records = [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    selected: dict[str, dict[str, object]] = {}
    for record in records:
        if record.get("source_system") != "bts_t100":
            continue
        match = re.search(r"requested_year=(\d{4})", str(record.get("source_url", "")))
        if match and (PATHS.bronze / str(record["source_file"])).is_file():
            selected[match.group(1)] = record
    if not selected:
        raise FileNotFoundError("No BTS T-100 archives found in bronze")
    return [selected[year] for year in sorted(selected)]


def _csv_bytes(content: bytes) -> bytes:
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        names = [
            name
            for name in archive.namelist()
            if name.lower().endswith(".csv") and "documentation" not in name.lower()
        ]
        if len(names) != 1:
            raise ValueError(f"Expected one T-100 data CSV, found {names}")
        return archive.read(names[0])


def _generic_carrier_key(identity: str, name: str) -> str:
    safe_identity = re.sub(r"[^A-Z0-9]+", "_", identity.upper()).strip("_")
    return f"BTS_{safe_identity}"


def _map_carrier(identity: str, name: str) -> str:
    upper = name.upper()
    if "AEROMEXICO" in upper or "AERO MEXICO" in upper:
        return "AEROMEXICO"
    if "DELTA AIR LINES" in upper:
        return "DELTA"
    if "VOLARIS" in upper or "CONTROLADORA VUELA" in upper:
        return "VOLARIS"
    if "VIVA AEROBUS" in upper or "AEROENLACES" in upper:
        return "VIVA_AEROBUS"
    return _generic_carrier_key(identity, name)


def build_t100() -> tuple[pl.DataFrame, pl.DataFrame]:
    frames: list[pl.DataFrame] = []
    for record in _manifest_records():
        source_file = str(record["source_file"])
        content = read_bronze_verified(source_file, str(record["sha256"]))
        frame = pl.read_csv(io.BytesIO(_csv_bytes(content)), infer_schema_length=20_000)
        frame = frame.rename({column: column.casefold() for column in frame.columns})
        frame = frame.filter(
            ((pl.col("origin_country") == "MX") & (pl.col("dest_country") == "US"))
            | ((pl.col("origin_country") == "US") & (pl.col("dest_country") == "MX"))
        ).with_columns(
            pl.lit(source_file).alias("source_file"),
            pl.lit(str(record["sha256"])).alias("source_hash"),
            pl.lit(datetime.fromisoformat(str(record["downloaded_at"]))).alias(
                "ingested_at"
            ),
        )
        frames.append(frame)
    combined = pl.concat(frames, how="vertical_relaxed").with_columns(
        [pl.col(column).cast(pl.Float64, strict=False) for column in NUMERIC_COLUMNS]
        + [
            pl.col("airline_id").cast(pl.Int64),
            pl.col("year").cast(pl.Int16),
            pl.col("quarter").cast(pl.Int8),
            pl.col("month").cast(pl.Int8),
            pl.col("aircraft_type").cast(pl.Int32),
            pl.col("aircraft_config").cast(pl.Int8),
        ]
    )
    combined = combined.with_columns(
        pl.when(pl.col("airline_id").is_not_null())
        .then(pl.concat_str([pl.lit("AIRLINE_ID_"), pl.col("airline_id").cast(pl.String)]))
        .otherwise(
            pl.concat_str(
                [
                    pl.lit("ENTITY_"),
                    pl.coalesce(
                        [
                            pl.col("unique_carrier_entity").cast(pl.String),
                            pl.col("unique_carrier").cast(pl.String),
                            pl.col("carrier").cast(pl.String),
                        ]
                    ),
                ]
            )
        )
        .alias("carrier_identity")
    )
    identities = combined.select(
        "carrier_identity",
        "airline_id",
        "unique_carrier",
        "unique_carrier_name",
        "unique_carrier_entity",
        "carrier",
        "carrier_name",
    ).unique()
    mapping = [
        {
            **row,
            "carrier_key": _map_carrier(
                str(row["carrier_identity"]), str(row["unique_carrier_name"])
            ),
        }
        for row in identities.iter_rows(named=True)
    ]
    crosswalk = pl.DataFrame(mapping).sort(["carrier_key", "airline_id"])
    duplicates = crosswalk.group_by(
        ["carrier_identity"]
    ).agg(pl.col("carrier_key").n_unique().alias("keys")).filter(pl.col("keys") != 1)
    if duplicates.height:
        raise ValueError("T-100 crosswalk has ambiguous carrier identities")
    identity_mapping = crosswalk.select("carrier_identity", "carrier_key").unique(
        subset=["carrier_identity"]
    )

    combined = combined.join(
        identity_mapping,
        on=["carrier_identity"],
        how="left",
        validate="m:1",
    )
    if combined["carrier_key"].null_count():
        raise ValueError("T-100 contains unmapped carriers")
    known_codes = {
        key: (value.get("iata"), value.get("icao")) for key, value in CARRIERS.items()
    }
    code_rows = [
        {
            "carrier_key": key,
            "iata_code": codes[0],
            "icao_code": codes[1],
        }
        for key, codes in known_codes.items()
    ]
    combined = combined.join(pl.DataFrame(code_rows), on="carrier_key", how="left")
    combined = combined.with_columns(
        pl.col("carrier_name").alias("source_carrier_name"),
        (pl.col("seats") * pl.col("distance")).alias("asm_miles"),
        (pl.col("passengers") * pl.col("distance")).alias("rpm_miles"),
        pl.when(pl.col("seats") > 0)
        .then(pl.col("passengers") / pl.col("seats"))
        .otherwise(None)
        .alias("load_factor"),
        pl.lit(True).alias("is_derived"),
        pl.lit("bts_t100").alias("source_system"),
        pl.lit(PARSER_VERSION).alias("parser_version"),
    ).sort(["year", "month", "carrier_key", "origin", "dest", "aircraft_type"])

    output = PATHS.silver / "bts_t100_segment.parquet"
    write_parquet_atomic(combined, output)
    crosswalk_path = PATHS.root / "config" / "carrier_crosswalk.csv"
    crosswalk_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = crosswalk_path.with_suffix(".csv.tmp")
    crosswalk.write_csv(temporary)
    temporary.replace(crosswalk_path)
    return combined, crosswalk


def main() -> int:
    frame, crosswalk = build_t100()
    print(
        json.dumps(
            {
                "rows": frame.height,
                "years": [int(frame["year"].min()), int(frame["year"].max())],
                "carriers": crosswalk.height,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
