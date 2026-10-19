"""Offline complementary rebuild that consumes complete raw chart selections when present."""


def run() -> dict:
    from src.ingest.airports.groups import build_from_bronze as airports
    from src.ingest.airports.reference import build_from_bronze as reference
    from src.ingest.macro.banxico import build_from_bronze as macro
    from src.ingest.macro.fuel import build_from_bronze as fuel
    from src.ingest.market.prices import TICKERS
    from src.ingest.market.prices import build_from_bronze as legacy_market
    from src.ingest.stage4_common import latest_bronze
    from src.source_updates.market import build_from_charts
    from src.source_updates.news import build_from_bronze as news

    raw_charts_selected = any(
        latest_bronze("yahoo_finance", ticker + "_chart") is not None for ticker in TICKERS
    )
    return {
        "macro": macro(),
        "fuel": fuel(),
        "market": build_from_charts() if raw_charts_selected else legacy_market(),
        "airport_reference": reference(),
        "airport_traffic": airports(),
        "news": news(),
        "market_mode": "raw_json" if raw_charts_selected else "preserved_legacy_csv",
        "activation": "none",
    }
