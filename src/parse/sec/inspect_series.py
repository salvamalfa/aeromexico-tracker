"""Print the requested quarterly SEC metric series for visual inspection."""

from __future__ import annotations

import polars as pl

from src.config import PATHS


def build_series() -> pl.DataFrame:
    frame = pl.read_parquet(PATHS.silver / "sec_operating_metrics.parquet").filter(
        (pl.col("period_type") == "quarter")
        & pl.col("metric_key").is_in(
            ["load_factor_total", "trasm", "casm_ex_fuel"]
        )
    )
    return (
        frame.select("period_id", "metric_key", "value_raw")
        .pivot(on="metric_key", index="period_id", values="value_raw")
        .sort("period_id")
        .rename(
            {
                "load_factor_total": "load_factor_pct",
                "trasm": "trasm_usd_cents",
                "casm_ex_fuel": "casm_ex_fuel_usd_cents",
            }
        )
    )


def format_series(frame: pl.DataFrame) -> str:
    """Render an ASCII-only table that is portable across Windows consoles."""
    return frame.write_csv().rstrip()


def main() -> int:
    print(format_series(build_series()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
