"""Aeromexico versus Volaris network-versus-ULCC comparison."""

from __future__ import annotations

from src.analytics.common import warehouse_query


def run() -> tuple[dict[str, object], dict[str, object]]:
    share = warehouse_query(
        """
        SELECT carrier_key, period_id, market_share
        FROM v_market_share_mx
        WHERE carrier_key IN ('AEROMEXICO','VOLARIS') AND segment='total'
        QUALIFY period_id=MAX(period_id) OVER ()
        ORDER BY carrier_key
        """
    )
    unit = warehouse_query(
        """
        SELECT carrier_key, period_id, unit_margin, load_factor
        FROM v_unit_economics
        WHERE carrier_key IN ('AEROMEXICO','VOLARIS')
        QUALIFY period_id=MAX(period_id) OVER (PARTITION BY carrier_key)
        ORDER BY carrier_key
        """
    )
    shares = dict(zip(share["carrier_key"], share["market_share"], strict=True))
    latest = str(share["period_id"].max())
    gap = float(shares["AEROMEXICO"] - shares["VOLARIS"])
    finding = f"En {latest}, Aeroméxico tuvo {shares['AEROMEXICO']:.1%} del mercado AFAC total frente a {shares['VOLARIS']:.1%} de Volaris, una brecha de {gap:+.1%}."
    return {
        "study_key": "aeromexico_vs_volaris", "title_es": "Aeroméxico frente a Volaris",
        "finding_es": finding, "estimate": gap, "unit": "market_share_gap",
        "period_id": latest, "comparison": "AEROMEXICO minus VOLARIS",
        "confidence": "alta", "caveat": "La participación usa pasajeros AFAC totales; las métricas unitarias conservan la definición reportada de cada aerolínea y no están ajustadas por etapa.",
        "source_tables": "v_market_share_mx|v_unit_economics",
    }, {"market_share": shares, "latest_unit_metrics": unit.to_dict("records")}
