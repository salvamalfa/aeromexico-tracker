"""Offline bronze-to-silver rebuild for Stage 4 complementary sources."""

from __future__ import annotations

import json


def run() -> dict[str, object]:
    from src.ingest.airports.groups import build_from_bronze as build_airport_traffic
    from src.ingest.airports.reference import build_from_bronze as build_airports
    from src.ingest.macro.banxico import build_from_bronze as build_macro
    from src.ingest.macro.fuel import build_from_bronze as build_fuel
    from src.ingest.market.prices import build_from_bronze as build_market
    from src.ingest.news.rss_gdelt import build_from_bronze as build_news

    return {
        "macro": build_macro(),
        "fuel": build_fuel(),
        "market": build_market(),
        "airport_reference": build_airports(),
        "airport_traffic": build_airport_traffic(),
        "news": build_news(),
    }


def main() -> int:
    print(json.dumps(run(), indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
