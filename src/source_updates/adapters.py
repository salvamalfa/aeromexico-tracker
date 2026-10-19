"""Small offline source adapters, explicitly scoped to candidate data."""


def parse_h10() -> dict:
    from src.ingest.macro.banxico import _publish, parse_h10_file
    from src.ingest.stage4_common import bronze_period, latest_bronze

    path = latest_bronze("federal_reserve_h10", "usd_mxn")
    if path is None:
        raise FileNotFoundError("Missing preserved H.10 usd_mxn CSV")
    cutoff = bronze_period(path).rsplit("_", maxsplit=1)[-1]
    frame = parse_h10_file(path, cutoff)
    if frame.empty:
        raise ValueError("No H.10 observations in the requested window")
    result = _publish(frame)
    return {
        **result,
        "source": "federal_reserve_h10",
        "fallback_only": True,
        "missing_banxico_indicators": ["inpc", "policy_rate"],
        "complete_macro_coverage": False,
    }
