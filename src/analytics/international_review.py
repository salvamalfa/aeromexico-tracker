"""A separate, private page on which a person reviews an international fit.

Nothing here feeds the dashboard.  It turns the outputs of
``python -m src.analytics.international_route_carrier --capture`` into one
self-contained HTML page whose job is to put every compromise of the fit in
front of a reviewer before any number is shown to anyone else: routes seen in
one direction only, routes with a single operator in the seed, carriers
capped at the capacity the seed can see, passengers left unallocated, pooled
families, and the cells where the fit misses T-100 the most.

The page is written wherever ``--out`` says; the project keeps it in the
private data repository next to the derived capture, not in this public one.
"""

from __future__ import annotations

import argparse
from html import escape
import json
from pathlib import Path

import pandas as pd

from src.analytics.international_route_carrier import reverse_route_key

GROUP = "AEROMEXICO_GROUP"
OWN = ("AEROMEXICO", "AEROMEXICO_CONNECT")
UNALLOCATED = "SIN_ASIGNAR"
# The unallocated column is seeded on every route, so it always holds a
# sliver; only a share that moves the route is worth a reviewer's look.
UNALLOCATED_FLAG_SHARE = 0.01


def route_review(
    estimate: pd.DataFrame,
    backtest: pd.DataFrame,
    route_totals: pd.DataFrame,
    diagnostics: pd.DataFrame,
    *,
    period_id: str,
) -> pd.DataFrame:
    """One row per directed route Grupo Aeroméxico serves, with its review flags."""

    period = estimate[estimate["period_id"] == period_id]
    fitted = period[period["carrier_key"] != GROUP]
    group = period[period["carrier_key"] == GROUP].set_index("route_key")["passengers_estimated"]
    if group.empty:
        return pd.DataFrame()

    by_carrier = fitted.pivot_table(
        index="route_key", columns="carrier_key", values="passengers_estimated",
        aggfunc="sum", fill_value=0.0,
    )
    operators = (fitted[fitted["carrier_key"] != UNALLOCATED]
                 .groupby("route_key")["carrier_key"].nunique())
    single = fitted["is_single_operator_seed"].eq(True).groupby(fitted["route_key"]).any()
    totals = (route_totals[route_totals["period_id"] == period_id]
              .groupby("route_key")["passengers"].sum())
    capped_keys: set[str] = set()
    if not diagnostics.empty:
        text = str(diagnostics.loc[diagnostics["period_id"] == period_id, "capped_carriers"].iloc[0] or "")
        capped_keys = {part.rsplit(" ", 1)[0] for part in text.split(", ") if part}
    capped_routes = set(fitted.loc[fitted["carrier_key"].isin(capped_keys), "route_key"])
    pooled_routes = set(fitted.loc[fitted["is_pooled_family"].eq(True), "route_key"])

    observed = pd.Series(dtype=float)
    if not backtest.empty:
        own = backtest[(backtest["period_id"] == period_id) & backtest["carrier_key"].isin(OWN)]
        observed = own.groupby("route_key")["passengers_observed"].sum()

    seed_routes = set(fitted["route_key"])
    rows = []
    for route_key, group_estimate in group.sort_values(ascending=False).items():
        reverse = reverse_route_key(route_key, set(totals[totals > 0].index))
        one_way = bool(reverse and reverse not in seed_routes)
        flags = []
        if bool(single.get(route_key, False)):
            flags.append("un solo operador en la semilla")
        if one_way:
            flags.append("sentido opuesto sin semilla")
        if route_key in capped_routes:
            flags.append("aerolinea topada en la ruta")
        unallocated = float(by_carrier[UNALLOCATED].get(route_key, 0.0)) if UNALLOCATED in by_carrier else 0.0
        route_total = float(totals.get(route_key, 0.0))
        if route_total and unallocated / route_total >= UNALLOCATED_FLAG_SHARE:
            flags.append("pasajeros sin asignar")
        if route_key in pooled_routes:
            flags.append("compite con una familia agrupada")
        afac = float(totals.get(route_key, 0.0))
        t100 = float(observed.get(route_key, float("nan")))
        rows.append(
            {
                "route_key": route_key,
                "afac_route_passengers": afac,
                "group_estimate": float(group_estimate),
                "aerovias": float(by_carrier["AEROMEXICO"].get(route_key, 0.0)) if "AEROMEXICO" in by_carrier else 0.0,
                "connect": float(by_carrier["AEROMEXICO_CONNECT"].get(route_key, 0.0)) if "AEROMEXICO_CONNECT" in by_carrier else 0.0,
                "group_share": float(group_estimate) / afac if afac else float("nan"),
                "operators": int(operators.get(route_key, 0)),
                "unallocated": unallocated,
                "t100_observed": t100,
                "t100_gap": (float(group_estimate) - t100) / t100 if t100 == t100 and t100 > 0 else float("nan"),
                "display_source": "observado T-100" if t100 == t100 else "estimado",
                "flags": flags,
            }
        )
    return pd.DataFrame(rows)


def one_way_routes(seed: pd.DataFrame, route_totals: pd.DataFrame, *, period_id: str) -> pd.DataFrame:
    """Routes AFAC publishes in both directions that the seed saw in one only."""

    totals = route_totals[route_totals["period_id"] == period_id].set_index("route_key")["passengers"]
    seen = set(seed.loc[seed["period_id"] == period_id, "route_key"])
    rows = []
    published = set(totals[totals > 0].index)
    for route_key in sorted(seen):
        reverse = reverse_route_key(route_key, published)
        if reverse and reverse not in seen:
            rows.append({"seen": route_key, "missing": reverse, "missing_passengers": float(totals[reverse])})
    return pd.DataFrame(rows, columns=["seen", "missing", "missing_passengers"]).sort_values(
        "missing_passengers", ascending=False, ignore_index=True
    )


# --------------------------------------------------------------------------
# Presentation
# --------------------------------------------------------------------------

_STYLE = """
:root{--bg:#f7f7f5;--card:#fff;--ink:#1d1d1b;--muted:#6b6b66;--line:#e2e1dc;
--accent:#0b4f8a;--warn:#9a5b00;--warn-bg:#fdf3e1;--bad:#a1261b;--ok:#1f6b3a}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){--bg:#141413;--card:#1f1f1d;
--ink:#ecebe6;--muted:#a3a29b;--line:#34332f;--accent:#7fb3e6;--warn:#f0b45a;--warn-bg:#3a2d15;
--bad:#f08a7e;--ok:#79c795}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);
font:15px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif}
main{max-width:1180px;margin:0 auto;padding:24px 16px 64px}
h1{font-size:1.5rem;margin:0 0 4px}h2{font-size:1.1rem;margin:32px 0 8px}
.muted{color:var(--muted)}.card{background:var(--card);border:1px solid var(--line);
border-radius:10px;padding:16px;margin:12px 0}
.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:10px}
.kpi{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:12px}
.kpi b{display:block;font-size:1.25rem;font-variant-numeric:tabular-nums}
.banner{background:var(--warn-bg);color:var(--warn);border-radius:10px;padding:12px 14px;margin:14px 0;font-weight:600}
.scroll{overflow-x:auto}table{border-collapse:collapse;width:100%;font-size:13px}
th,td{padding:6px 8px;border-bottom:1px solid var(--line);text-align:left;vertical-align:top}
th{position:sticky;top:0;background:var(--card);font-weight:600}
td.n{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}
.flag{display:inline-block;background:var(--warn-bg);color:var(--warn);border-radius:6px;
padding:1px 6px;margin:1px 2px 1px 0;font-size:12px;white-space:nowrap}
.sev-reject{color:var(--bad);font-weight:600}.sev-review{color:var(--warn);font-weight:600}
.sev-note{color:var(--muted)}ul.check{list-style:none;padding-left:0}
ul.check li:before{content:"\\2610  ";color:var(--accent)}
"""


def _n(value: float, digits: int = 0) -> str:
    if value != value:
        return "—"
    return f"{value:,.{digits}f}"


def _pct(value: float) -> str:
    return "—" if value != value else f"{value:.1%}"


def render(
    *,
    period_id: str,
    summary: dict,
    routes: pd.DataFrame,
    one_way: pd.DataFrame,
    backtest: pd.DataFrame,
    families: pd.DataFrame,
) -> str:
    """The whole review page as one self-contained HTML string."""

    acceptance = summary["acceptance"][period_id]
    fit = next(row for row in summary["fit"] if row["period_id"] == period_id)
    own_backtest = summary.get("t100_backtest_aeromexico") or {}
    all_backtest = summary.get("t100_backtest") or {}

    kpis = [
        ("Veredicto de la puerta", escape(acceptance["verdict"])),
        ("Cobertura rutas / aerolineas", f"{acceptance['route_passenger_coverage']:.2%} / {acceptance['carrier_passenger_coverage']:.2%}"),
        ("Ajuste", "convergio" if fit["converged"] else "NO convergio"),
        ("Grupo Aeromexico estimado", _n(routes["group_estimate"].sum()) if not routes.empty else "—"),
        ("Error vs T-100 (todas)", _pct(all_backtest.get("weighted_abs_error", float("nan")))),
        ("Error vs T-100 (Aerovias+Connect)", _pct(own_backtest.get("weighted_abs_error", float("nan")))),
        ("Topados por capacidad", _n(fit["passengers_capped"])),
        ("Sin asignar", _n(fit["passengers_unallocated"])),
    ]
    parts = [
        "<!doctype html><html lang='es'><head><meta charset='utf-8'>",
        "<meta name='viewport' content='width=device-width,initial-scale=1'>",
        f"<title>Revision internacional {escape(period_id)}</title><style>{_STYLE}</style></head><body><main>",
        f"<h1>Revision humana · estimacion internacional {escape(period_id)}</h1>",
        f"<p class='muted'>{escape(acceptance['acceptance_version'])} · "
        f"{escape(str(fit.get('reason') or 'ajuste internacional con familias, topes y SIN_ASIGNAR'))}</p>",
        "<div class='banner'>Vista privada de revision. Nada de esta pagina esta publicado ni "
        "integrado al dashboard; requiere aprobacion explicita.</div>",
        "<div class='kpis'>",
        *(f"<div class='kpi'><span class='muted'>{escape(label)}</span><b>{value}</b></div>" for label, value in kpis),
        "</div>",
    ]

    parts.append("<h2>Hallazgos de la puerta</h2><div class='card'><ul>")
    for finding in acceptance["findings"]:
        parts.append(
            f"<li><span class='sev-{escape(finding['severity'])}'>{escape(finding['severity'].upper())}</span> "
            f"<code>{escape(finding['code'])}</code> — {escape(finding['detail'])}</li>"
        )
    parts.append("</ul></div>")

    parts.append(
        "<h2>Grupo Aeromexico por ruta dirigida</h2><p class='muted'>Ordenado por pasajeros "
        "estimados. <em>Fuente a mostrar</em>: donde T-100 observa la celda se mostraria la "
        "observacion; el estimado queda como diagnostico.</p><div class='card scroll'><table><thead><tr>"
        "<th>Ruta</th><th>AFAC ruta</th><th>Grupo AM</th><th>Aerovias</th><th>Connect</th>"
        "<th>Participacion</th><th>Operadores</th><th>T-100 AM</th><th>Brecha</th><th>Fuente</th>"
        "<th>Revisar</th></tr></thead><tbody>"
    )
    for row in routes.itertuples(index=False):
        flags = "".join(f"<span class='flag'>{escape(flag)}</span>" for flag in row.flags)
        parts.append(
            f"<tr><td>{escape(row.route_key)}</td><td class='n'>{_n(row.afac_route_passengers)}</td>"
            f"<td class='n'>{_n(row.group_estimate)}</td><td class='n'>{_n(row.aerovias)}</td>"
            f"<td class='n'>{_n(row.connect)}</td><td class='n'>{_pct(row.group_share)}</td>"
            f"<td class='n'>{row.operators}</td><td class='n'>{_n(row.t100_observed)}</td>"
            f"<td class='n'>{_pct(row.t100_gap)}</td><td>{escape(row.display_source)}</td><td>{flags}</td></tr>"
        )
    parts.append("</tbody></table></div>")

    parts.append(
        "<h2>Rutas vistas en un solo sentido</h2><p class='muted'>AFAC publica ambos sentidos; la "
        "semilla solo uno. El sentido faltante no recibe estimacion.</p><div class='card scroll'>"
        "<table><thead><tr><th>Visto</th><th>Faltante</th><th>Pasajeros AFAC del faltante</th></tr></thead><tbody>"
    )
    for row in one_way.itertuples(index=False):
        parts.append(
            f"<tr><td>{escape(row.seen)}</td><td>{escape(row.missing)}</td>"
            f"<td class='n'>{_n(row.missing_passengers)}</td></tr>"
        )
    parts.append("</tbody></table></div>")

    parts.append(
        "<h2>Aerolineas topadas por capacidad visible</h2><div class='card'>"
        f"<p>{escape(str(fit.get('capped_carriers') or 'ninguna'))}</p><p class='muted'>El excedente no "
        "se reparte entre otras aerolineas: queda reportado. Suele indicar vuelos que el proveedor no ve.</p></div>"
    )

    parts.append("<h2>Familias ajustadas como una columna</h2><div class='card scroll'><table><thead>"
                 "<tr><th>Aerolinea</th><th>Familia</th><th>Motivo</th></tr></thead><tbody>")
    for row in families.itertuples(index=False):
        parts.append(
            f"<tr><td>{escape(row.carrier_key)}</td><td>{escape(row.fit_label)}</td><td>{escape(row.reason)}</td></tr>"
        )
    parts.append("</tbody></table></div>")

    worst = pd.DataFrame()
    if not backtest.empty:
        own = backtest[backtest["carrier_key"].isin(OWN)].copy()
        own["abs_error"] = own["error"].abs()
        worst = own.sort_values("abs_error", ascending=False).head(15)
    parts.append("<h2>Celdas de Aerovias/Connect que mas fallan contra T-100</h2><div class='card scroll'>"
                 "<table><thead><tr><th>Ruta</th><th>Aerolinea</th><th>T-100</th><th>Estimado</th>"
                 "<th>Error</th></tr></thead><tbody>")
    for row in worst.itertuples(index=False):
        relative = row.error / row.passengers_observed if row.passengers_observed else float("nan")
        parts.append(
            f"<tr><td>{escape(row.route_key)}</td><td>{escape(row.carrier_key)}</td>"
            f"<td class='n'>{_n(row.passengers_observed)}</td><td class='n'>{_n(row.passengers_estimated)}</td>"
            f"<td class='n'>{_pct(relative)}</td></tr>"
        )
    parts.append("</tbody></table></div>")

    parts.append(
        "<h2>Antes de aprobar</h2><div class='card'><ul class='check'>"
        "<li>Las rutas con un solo operador en la semilla son plausibles (sin competidor omitido).</li>"
        "<li>Los sentidos faltantes se explican (vuelos triangulares, estacionales o fuera de la muestra).</li>"
        "<li>Las familias agrupadas son aceptables para mostrarse como familia.</li>"
        "<li>Los topes (sobre todo TUI) se muestran como brecha y no como pasajeros de otras aerolineas.</li>"
        "<li>La brecha contra T-100 de Aerovias/Connect es aceptable para publicar estimados fuera de EE. UU.</li>"
        "<li>Se decide si basta un mes o se esperan mayo-julio antes de integrar al dashboard.</li>"
        "</ul></div></main></body></html>"
    )
    return "".join(parts)


def main(argv: list[str] | None = None) -> int:  # pragma: no cover - manual entry
    from src.analytics.international_route_carrier import FAMILY_FILE, build_international_margins
    from src.config import PATHS
    from src.ingest.afac.international_crosswalks import (
        CARRIER_CROSSWALK_FILE, CARRIER_MARGIN_FILE, ROUTE_MARGIN_FILE,
    )

    parser = argparse.ArgumentParser(prog="python -m src.analytics.international_review")
    parser.add_argument("period_id")
    parser.add_argument("--input", type=Path, default=PATHS.silver / "international_route_carrier")
    parser.add_argument("--out", type=Path, required=True, help="where to write the private HTML page")
    args = parser.parse_args(argv)

    reference = PATHS.data / "reference"
    routes_margin = pd.read_csv(reference / ROUTE_MARGIN_FILE)
    carriers = pd.read_csv(reference / CARRIER_CROSSWALK_FILE).fillna("")
    route_totals, _ = build_international_margins(
        routes_margin, pd.read_csv(reference / CARRIER_MARGIN_FILE), carriers
    )

    def frame(name: str) -> pd.DataFrame:
        path = args.input / f"{name}_{args.period_id}.parquet"
        return pd.read_parquet(path) if path.exists() else pd.DataFrame()

    estimate, backtest, diagnostics, seed = (frame(n) for n in ("estimate", "t100_backtest", "diagnostics", "seed"))
    summary = json.loads((args.input / f"summary_{args.period_id}.json").read_text())
    routes = route_review(estimate, backtest, route_totals, diagnostics, period_id=args.period_id)
    page = render(
        period_id=args.period_id,
        summary=summary,
        routes=routes,
        one_way=one_way_routes(seed, route_totals, period_id=args.period_id),
        backtest=backtest[backtest["period_id"] == args.period_id] if not backtest.empty else backtest,
        families=pd.read_csv(reference / FAMILY_FILE),
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(page, encoding="utf-8")
    flagged = int(routes["flags"].map(bool).sum()) if not routes.empty else 0
    print(f"{len(routes)} rutas de Grupo Aeromexico, {flagged} con banderas de revision -> {args.out}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
