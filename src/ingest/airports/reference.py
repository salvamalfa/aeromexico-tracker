"""Official airport reference ingestion and operator-group enrichment."""

from __future__ import annotations

from io import BytesIO

import pandas as pd

from src.common.http import SourceHttpClient
from src.common.storage import find_bronze_by_source_url
from src.config import PATHS
from src.ingest.stage4_common import fetch_bronze, latest_bronze, lineage, write_parquet_atomic


OURAIRPORTS_URL = "https://davidmegginson.github.io/ourairports-data/airports.csv"
OPERATOR_AIRPORTS = {
    "ASUR": {"CUN", "CZM", "HUX", "MID", "MTT", "OAX", "TAP", "VER", "VSA"},
    "GAP": {"GDL", "TIJ", "SJD", "PVR", "BJX", "HMO", "MLM", "LAP", "MXL", "AGU", "LMM", "ZLO", "MBJ", "KIN"},
    "OMA": {"MTY", "ACA", "CJS", "CUL", "CUU", "DGO", "MZT", "ZIH", "SLW", "SLP", "TAM", "TRC", "REX", "ZCL"},
    "GOVERNMENT": {"MEX", "NLU"},
}


def operator_group(iata: object) -> str | None:
    code = str(iata).strip().upper()
    for group, codes in OPERATOR_AIRPORTS.items():
        if code in codes:
            return group
    return None


def build_from_bronze() -> dict[str, object]:
    """Rebuild the airport dimension from the latest OurAirports snapshot."""

    airports_path = latest_bronze("ourairports", "airports")
    if airports_path is None:
        raise FileNotFoundError("Missing OurAirports bronze artifact")
    # OpenFlights is optional and frozen; the maintained crosswalk is authoritative.
    openflights_path = latest_bronze("openflights", "airlines")
    raw = pd.read_csv(BytesIO(airports_path.read_bytes()), low_memory=False)
    dim = raw.loc[raw["iata_code"].notna() & raw["iata_code"].ne("")].copy()
    dim["airport_iata"] = dim["iata_code"].str.upper()
    dim["airport_icao"] = dim["ident"].where(dim["ident"].str.len().eq(4))
    dim["city"] = dim["municipality"]
    dim["country"] = dim["iso_country"]
    dim["latitude"] = pd.to_numeric(dim["latitude_deg"], errors="raise")
    dim["longitude"] = pd.to_numeric(dim["longitude_deg"], errors="raise")
    dim["elevation"] = pd.to_numeric(dim["elevation_ft"], errors="coerce")
    dim["operator_group"] = dim["airport_iata"].map(operator_group)
    dim["source_system"] = "ourairports"
    for key, value in lineage(airports_path).items():
        dim[key] = value
    dim = dim[
        [
            "airport_iata", "airport_icao", "name", "city", "country", "latitude",
            "longitude", "elevation", "type", "operator_group", "source_system", "source_file",
            "source_hash", "ingested_at", "parser_version",
        ]
    ].drop_duplicates("airport_iata", keep="first").sort_values("airport_iata")
    write_parquet_atomic(dim, PATHS.gold / "dim_airport.parquet")

    # The existing crosswalk remains authoritative. OpenFlights is frozen and
    # therefore only fills exact-name historical mappings; it never overwrites.
    crosswalk_path = PATHS.data / "reference" / "carrier_crosswalk.csv"
    crosswalk = pd.read_csv(crosswalk_path, dtype=str).fillna("")
    openflights_columns = [
        "id", "name", "alias", "iata", "icao", "callsign", "country", "active"
    ]
    openflights = (
        pd.read_csv(
            BytesIO(openflights_path.read_bytes()),
            header=None,
            names=openflights_columns,
            dtype=str,
            na_values=["\\N"],
        ).fillna("")
        if openflights_path is not None
        else pd.DataFrame(columns=openflights_columns)
    )
    canonical = {
        "RYANAIR": "Ryanair",
        "DELTA": "Delta Air Lines",
        "IAG": "International Airlines Group",
    }
    additions: list[dict[str, str]] = []
    for carrier_key, name in canonical.items():
        match = openflights.loc[openflights["name"].str.casefold().eq(name.casefold())]
        if match.empty:
            continue
        item = match.iloc[0]
        additions.append(
            {
                "source_system": "openflights",
                "source_carrier_name": item["name"],
                "carrier_key": carrier_key,
                "iata": item["iata"],
                "icao": item["icao"],
                "valid_from": "",
                "valid_to": "",
                "notes": "Code mapping only; OpenFlights routes are not used.",
            }
        )
    if additions:
        crosswalk = pd.concat([crosswalk, pd.DataFrame(additions)], ignore_index=True)
        crosswalk = crosswalk.drop_duplicates(
            ["source_system", "source_carrier_name", "carrier_key"], keep="last"
        )
    crosswalk.to_csv(crosswalk_path, index=False, encoding="utf-8")
    required = set().union(*OPERATOR_AIRPORTS.values())
    missing = sorted(required - set(dim["airport_iata"]))
    return {
        "airport_rows": len(dim),
        "required_codes": len(required),
        "missing_codes": missing,
        "crosswalk_rows": len(crosswalk),
    }


def run() -> dict[str, object]:
    cached = find_bronze_by_source_url(OURAIRPORTS_URL)
    if cached is None:
        with SourceHttpClient("reference", timeout_seconds=20, max_attempts=1) as client:
            fetch_bronze(
                client,
                OURAIRPORTS_URL,
                source_system="ourairports",
                entity="airports",
                period="current",
                ext="csv",
                relative_dir="reference",
                notes="Official OurAirports public-data export.",
            )
    return build_from_bronze()


def main() -> int:
    print(run())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
