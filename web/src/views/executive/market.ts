// Mercado: complete observed monthly share history, with the selected
// quarter highlighted and quarterly comparisons over all Mexican
// carriers, from market.json (src/dashboard/market.py). Industria is the
// sum of the three and is drawn dashed; a month AFAC does not publish for a
// carrier is a gap, never zero.

import type { Data, Layout } from "plotly.js";
import Plotly from "../../lib/plotly";
import { $ } from "../flights/dom";
import { entityState, entityLabel } from "./entities";
import { ENTITY_COLORS, type EntityKey } from "../shell/carriers";
import { currentPeriodId } from "../../state/period";
import type { MarketSegmentKey } from "../../types/domain";
import { bindSourceInfo, setAfacSource } from "../market/source-info";
import { bindUnifiedTooltip } from "../../lib/unified-tooltip";
import { marketPointDetail } from "../market/point-detail";

const marketEntities: EntityKey[] = ["AEROMEXICO", "VOLARIS", "VIVA_AEROBUS"];

function monthDate(periodId: string): string {
  return `${periodId.slice(0, 4)}-${periodId.slice(5, 7)}-01`;
}

function quarterBounds(periodId: string): [string, string] {
  const year = periodId.slice(0, 4);
  const quarter = Number(periodId.slice(-1));
  const start = (quarter - 1) * 3 + 1;
  return [`${year}-${String(start).padStart(2, "0")}-01`, new Date(Date.UTC(Number(year), start + 2, 1)).toISOString().slice(0,10)];
}

function monthLabel(id: string): string {
  return new Intl.DateTimeFormat("es-MX", { month: "long", year: "numeric", timeZone: "UTC" })
    .format(new Date(monthDate(id)));
}

export function renderMarket(periodId: string | undefined): void {
  const market = entityState.market;
  const host = $("market-chart");
  if (!host) return;
  if (!market) {
    host.innerHTML = '<p class="analysis-placeholder">Participación AFAC no disponible en este build.</p>';
    return;
  }
  const segment = (($("market-segment") as HTMLSelectElement | null)?.value ?? "total") as MarketSegmentKey;
  const selected = periodId ?? currentPeriodId() ?? market.metadata.default_quarter;
  const card = document.getElementById("market-card");
  if (card) card.dataset.comparisonPeriod = selected;
  // The global quarter controls the band and comparisons, not the history.
  // Retain internal gaps, bounded by the segment's first and last real month.
  const firstAvailable = market.months.findIndex(row => row.segments[segment].mexican_carriers_passengers != null);
  const lastAvailable = market.months.reduce((last,row,index) => row.segments[segment].mexican_carriers_passengers != null ? index : last, -1);
  const months = firstAvailable < 0 ? [] : market.months.slice(firstAvailable, lastAvailable + 1);
  host.setAttribute("aria-label", `Participación mensual de pasajeros por aerolínea; historia hasta ${months.at(-1)?.period_id ?? "sin observaciones"}; trimestre seleccionado ${selected}`);
  const source = document.getElementById("market-source");
  if (source) {
    const note = `Fuente: Agencia Federal de Aviación Civil (AFAC). Participación calculada con los pasajeros reportados por aerolíneas mexicanas en vuelos regulares y de fletamento. Aeroméxico incluye Connect. Último mes disponible en esta gráfica: ${months.length ? monthLabel(months.at(-1)!.period_id) : "sin observaciones"}.`;
    source.removeAttribute("title");
    source.setAttribute("aria-label", "Fuente y alcance del mercado");
    const detail = document.getElementById("market-source-note");
    if (detail) {
      setAfacSource(detail, note.replace("Fuente: Agencia Federal de Aviación Civil (AFAC). ", ""));
      bindSourceInfo(source, detail);
    }
  }
  // Draw each reported observation once. Provenance metadata must not inject
  // artificial missing observations into the monthly AFAC series.
  const x = months.map(month => monthDate(month.period_id));
  const traces: Data[] = marketEntities.map((key) => {
    const color = ENTITY_COLORS[key];
    return {
      x,
      y: months.map((month) => {
        const block = month.segments[segment];
        const item = key === "INDUSTRY" ? block.industry : block.carriers[key];
        return item?.share == null ? null : item.share * 100;
      }),
      name: entityLabel(key),
      type: "scatter",
      mode: "lines",
      connectgaps: false,
      line: key === "INDUSTRY" ? { color, width: 2.2, dash: "dash" } : { color, width: 2.4 },
      hoverinfo: "none",
    } as Data;
  });
  const shapes: Layout["shapes"] = [];
  const shares = months.flatMap(month => marketEntities.flatMap(key => {
    const share = month.segments[segment].carriers[key]?.share;
    return share == null || !Number.isFinite(share) ? [] : [share * 100];
  }));
  // Total and domestic start at 15%; expand for international observations
  // below 15% rather than cutting off Viva's historical market share.
  const minimumShare = shares.length ? Math.min(...shares) : 15;
  const lower = minimumShare < 15 ? Math.max(0, Math.floor(minimumShare)) : 15;
  const upper = shares.length ? Math.max(lower + 5, Math.ceil(Math.max(...shares) / 5) * 5) : 100;
  if (selected) {
    const [x0, x1] = quarterBounds(selected);
    shapes.push({
      type: "rect", xref: "x", yref: "paper", x0, x1, y0: 0, y1: 1,
      fillcolor: "rgba(0,48,135,.06)", line: { color: "rgba(0,48,135,.32)", width: 1, dash: "dot" }, layer: "below",
    });
  }
  const layout: Partial<Layout> = {
    height: 480,
    paper_bgcolor: "rgba(0,0,0,0)",
    plot_bgcolor: "rgba(0,0,0,0)",
    font: { family: 'Inter, "Segoe UI", system-ui, sans-serif', color: "#182233", size: 10 },
    hoverlabel: { bgcolor: "#ffffff", bordercolor: "#cbd5e1", font: { color: "#182233", size: 11 } },
    legend: { orientation: "h", x: 0, y: 1.1, font: { size: 10 } },
    margin: { l: 48, r: 18, t: 30, b: 36 },
    hovermode: "x unified",
    xaxis: { type: "date", range: x.length ? [x[0]!, x.at(-1)!] : undefined, autorange: false, showgrid: false, tickformat: "%Y", ticks: "outside", ticklen: 8, automargin: true },
    yaxis: { ticksuffix: "%", range: [lower, upper], gridcolor: "#e8edf4", tickformat: ".0f", ticks: "outside", ticklen: 8, automargin: true },
    shapes,
  };
  void Promise.resolve(Plotly.react("market-chart", traces, layout, { displayModeBar: false, responsive: true })).then(()=>{
    bindUnifiedTooltip("market-chart",x,(_key,index)=>marketPointDetail(market,segment,months[index]!.period_id));
  });
}

export function mountMarketControls(): void {
  document.getElementById("market-segment")?.addEventListener("change", () => renderMarket(undefined));
}
