"""Report whether manual-source data needs a human refresh."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

import pandas as pd

from src.dashboard.data import query_df


def check(source: str = "afac", max_age_days: int = 62) -> dict[str, object]:
    frame = query_df(
        "SELECT source_system, last_date, last_ingested_at, age_days "
        "FROM v_dashboard_source_freshness WHERE source_system=?",
        (source,),
    )
    if frame.empty:
        return {
            "source": source,
            "is_stale": True,
            "reason": "source_missing",
            "last_date": None,
            "age_days": None,
            "max_age_days": max_age_days,
        }
    row = frame.iloc[0]
    age_days = int(row["age_days"])
    return {
        "source": source,
        "is_stale": age_days > max_age_days,
        "reason": "age_exceeded" if age_days > max_age_days else "current",
        "last_date": pd.Timestamp(row["last_date"]).date().isoformat(),
        "age_days": age_days,
        "max_age_days": max_age_days,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", default="afac")
    parser.add_argument("--max-age-days", type=int, default=62)
    args = parser.parse_args()
    result = check(args.source, args.max_age_days)
    print(json.dumps(result, ensure_ascii=False))
    output = os.getenv("GITHUB_OUTPUT")
    if output:
        with Path(output).open("a", encoding="utf-8") as handle:
            handle.write(f"is_stale={str(result['is_stale']).lower()}\n")
            handle.write(f"last_date={result['last_date'] or 'missing'}\n")
            handle.write(f"age_days={result['age_days'] if result['age_days'] is not None else 'unknown'}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
