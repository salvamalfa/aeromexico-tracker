"""One explicit entry point for all Stage 4 network ingestion and transforms."""

from __future__ import annotations

import json


def run() -> dict[str, object]:
    from src.ingest.airports.groups import run as run_airport_groups
    from src.ingest.airports.reference import run as run_airport_reference
    from src.ingest.macro.banxico import run as run_macro
    from src.ingest.macro.fuel import run as run_fuel
    from src.ingest.market.prices import run as run_market
    from src.ingest.news.rss_gdelt import run as run_news
    from src.ingest.regulatory.faa import run as run_faa
    from src.transform.stage4 import run as run_transform
    from src.transform.validate_stage4 import run as run_validation

    return {
        "macro": run_macro(),
        "fuel": run_fuel(),
        "market": run_market(),
        "airport_reference": run_airport_reference(),
        "airport_groups": run_airport_groups(),
        "news": run_news(),
        "faa": run_faa(),
        "quality": run_transform(),
        "validation": run_validation().to_dict(orient="records"),
    }


def main() -> int:
    print(json.dumps(run(), indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
