"""Daily U.S. Gulf Coast jet-fuel ingestion from FRED with EIA validation."""

from __future__ import annotations

from io import BytesIO

import pandas as pd

from src.config import PATHS
from src.ingest.stage4_common import (
    bronze_period,
    fetch_bronze,
    latest_bronze,
    lineage,
    write_parquet_atomic,
)
from src.common.http import SourceHttpClient


START_DATE = "2015-01-01"
EIA_SERIES_ID = "EER_EPJK_PF4_RGC_DPG"
EIA_XLS_URL = "https://www.eia.gov/dnav/pet/hist_xls/EER_EPJK_PF4_RGC_DPGd.xls"


def build_from_bronze(end_date: str | None = None) -> dict[str, object]:
    """Rebuild the fuel silver table solely from the latest EIA bronze file."""

    eia_path = latest_bronze("eia", EIA_SERIES_ID)
    if eia_path is None:
        raise FileNotFoundError("Missing EIA jet-fuel bronze artifact")
    raw = pd.read_excel(BytesIO(eia_path.read_bytes()), sheet_name="Data 1", header=2)
    frame = raw.iloc[:, :2].copy()
    frame.columns = ["date", "price_usd_per_gallon"]
    frame["date"] = pd.to_datetime(frame["date"])
    frame["price_usd_per_gallon"] = pd.to_numeric(
        frame["price_usd_per_gallon"], errors="coerce"
    )
    frame = frame.dropna(subset=["date", "price_usd_per_gallon"])
    frame = frame.loc[frame["date"] >= pd.Timestamp(START_DATE)]
    cutoff = end_date or bronze_period(eia_path).rsplit("_", maxsplit=1)[-1]
    frame = frame.loc[frame["date"] <= pd.Timestamp(cutoff)]
    frame["series_id"] = EIA_SERIES_ID
    frame["source"] = "eia"
    frame["source_system"] = "eia"
    for key, value in lineage(eia_path).items():
        frame[key] = value
    frame = frame[
        [
            "date", "series_id", "price_usd_per_gallon", "source", "source_system", "source_file",
            "source_hash", "ingested_at", "parser_version",
        ]
    ].sort_values("date")
    write_parquet_atomic(frame, PATHS.silver / "fuel_prices.parquet")

    return {"rows": len(frame), "source": "official_eia_xls"}


def run(end_date: str | None = None) -> dict[str, object]:
    end = end_date or pd.Timestamp.now(tz="America/Mexico_City").date().isoformat()
    with SourceHttpClient("eia") as client:
        fetch_bronze(
            client,
            EIA_XLS_URL,
            source_system="eia",
            entity=EIA_SERIES_ID,
            period=f"{START_DATE}_{end}",
            ext="xls",
            relative_dir="eia",
            notes="Official EIA daily U.S. Gulf Coast jet-fuel historical workbook.",
        )
    return build_from_bronze(end)


def main() -> int:
    print(run())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
