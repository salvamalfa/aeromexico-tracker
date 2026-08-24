"""Measure route and airport concentration in the transborder network."""

from __future__ import annotations

from src.analytics.common import warehouse_query


def run() -> tuple[dict[str, object], dict[str, object]]:
    frame = warehouse_query(
        """
        SELECT f.period_id, r.market_key, r.origin_iata, r.dest_iata, SUM(f.asm_miles) AS asm_miles,
               SUM(f.departures_performed) AS departures
        FROM fact_route_traffic f JOIN dim_route r USING (route_key)
        WHERE f.carrier_key='AEROMEXICO'
        GROUP BY ALL ORDER BY period_id
        """
    )
    latest = sorted(frame["period_id"].unique())[-12:]
    window = frame[frame["period_id"].isin(latest)]
    market = window.groupby("market_key")["asm_miles"].sum()
    shares = market / market.sum()
    hhi = float((shares**2).sum())
    mex_departures = float(window.loc[window["origin_iata"].eq("MEX") | window["dest_iata"].eq("MEX"), "departures"].sum())
    mex_share = mex_departures / float(window["departures"].sum())
    finding = f"En los últimos 12 meses T-100, el HHI por mercado fue {hhi:.3f} y {mex_share:.1%} de las salidas observadas tocaron MEX."
    return {
        "study_key": "network_concentration", "title_es": "Concentración de la red",
        "finding_es": finding, "estimate": hhi, "unit": "hhi_0_1",
        "period_id": f"{latest[0]}-{latest[-1]}", "comparison": "transborder route ASM shares",
        "confidence": "alta", "caveat": "T-100 cubre segmentos México-Estados Unidos; la dependencia de MEX en la red global puede ser distinta.",
        "source_tables": "fact_route_traffic|dim_route",
    }, {"hhi": hhi, "mex_departure_share": mex_share, "top_markets": shares.nlargest(10).to_dict()}
