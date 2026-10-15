// "Participación de pasajeros (AFAC)" card under the executive reading
// (Dashboard v2): monthly share of each selected airline over all Mexican
// carriers, from market.json (src/dashboard/market.py). Industria is the
// sum of the three and is drawn dashed; a month AFAC does not publish for a
// carrier is a gap, never zero.

import type { Data, Layout } from "plotly.js";
import Plotly from "../../lib/plotly";
import { $ } from "../flights/dom";
import { entityState, entityLabel } from "./entities";
import { ENTITY_COLORS, type EntityKey } from "../shell/carriers";
import { marketSnapshot, formatMarketNumber } from "../market/calculations";
import { mountDemand } from "../market/demand";
import type { MarketSegmentKey } from "../../types/domain";

const SEGMENT_LABELS: Record<MarketSegmentKey, string> = {
  total: "total",
  domestic: "nacional",
  international: "internacional",
};

let marketEntities: EntityKey[] = ["AEROMEXICO", "VOLARIS", "VIVA_AEROBUS"];

export function setMarketEntities(entities: EntityKey[]): void {
  marketEntities = entities;
}

function monthDate(periodId: string): string {
  return `${periodId.slice(0, 4)}-${periodId.slice(5, 7)}-01`;
}

function quarterBounds(periodId: string): [string, string] {
  const year = periodId.slice(0, 4);
  const quarter = Number(periodId.slice(-1));
  const start = (quarter - 1) * 3 + 1;
  return [`${year}-${String(start).padStart(2, "0")}-01`, new Date(Date.UTC(Number(year), start + 2, 1)).toISOString().slice(0,10)];
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
  const grain = (document.getElementById("market-grain") as HTMLSelectElement | null)?.value ?? "quarter";
  const periods = grain === "month" ? market.months : market.quarters;
  const picker = document.getElementById("market-period") as HTMLSelectElement | null;
  if (picker && (picker.dataset.grain !== grain || !picker.options.length)) {
    picker.replaceChildren(...periods.map(row => new Option(row.period_label, row.period_id)));
    picker.value = periods.at(-1)?.period_id ?? "";
    picker.dataset.grain = grain;
  }
  if (picker && periodId) {
    const matching = grain === "quarter" ? periodId : market.months.filter(row => {
      const q = Math.ceil(Number(row.period_id.slice(5)) / 3);
      return `${row.period_id.slice(0,4)}Q${q}` === periodId;
    }).at(-1)?.period_id;
    if (matching && periods.some(row => row.period_id === matching)) picker.value = matching;
  }
  const selected = picker?.value ?? periodId ?? market.metadata.default_quarter;
  const snapshot = marketSnapshot(periods, selected, segment);
  renderComparison(snapshot);
  const cut = document.getElementById("market-cut");
  if (cut) cut.textContent = `Corte seleccionado: ${selected} · última observación AFAC: ${market.metadata.last_period} · captura: ${market.metadata.data_as_of ?? "N/D"}.`;
  const method = document.getElementById("market-method");
  if (method) method.textContent = market.metadata.method_note;
  const firstAvailable = market.months.findIndex(row => row.segments[segment].mexican_carriers_passengers != null);
  const months = firstAvailable < 0 ? market.months : market.months.slice(firstAvailable);
  const x = months.map((month) => monthDate(month.period_id));
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
      hovertemplate: `${entityLabel(key)} %{y:.1f}%<extra>%{x|%b %Y}</extra>`,
    } as Data;
  });
  const subtitle = $("market-subtitle");
  if (subtitle) {
    subtitle.textContent =
      `Pasajeros de cada aerolínea entre los de todas las aerolíneas mexicanas, por mes (segmento ${SEGMENT_LABELS[segment]}). ` +
      "Aeroméxico incluye a Aeroméxico Connect; las aerolíneas extranjeras no se incluyen porque AFAC no las publica por aerolínea.";
  }
  const shapes: Layout["shapes"] = [];
  if (selected) {
    const [x0, x1] = selected.includes("Q") ? quarterBounds(selected) : [monthDate(selected), new Date(Date.UTC(Number(selected.slice(0,4)), Number(selected.slice(5)), 1)).toISOString().slice(0,10)];
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
    xaxis: { type: "date", showgrid: false, tickformat: "%Y" },
    yaxis: { ticksuffix: "%", rangemode: "tozero", gridcolor: "#e8edf4", tickformat: ".0f" },
    shapes,
  };
  void Plotly.react("market-chart", traces, layout, { displayModeBar: false, responsive: true });
}

function renderComparison(snapshot: ReturnType<typeof marketSnapshot>): void {
  const host = document.getElementById("market-comparison");
  const kpis = document.getElementById("market-kpis");
  const fmt = formatMarketNumber;
  if (!host || !kpis) return;
  host.replaceChildren(...snapshot.rows.map(row => {
    const tr = document.createElement("tr");
    for (const text of [row.label, fmt(row.passengers), fmt(row.growth, "%"), fmt(row.share, "%"), fmt(row.shareChange, " pp"), fmt(row.contribution, " pp")]) {
      const td = document.createElement("td"); td.textContent = text; tr.append(td);
    }
    return tr;
  }));
  kpis.replaceChildren(...[["Pasajeros · aerolíneas mexicanas", fmt(snapshot.total)], ["Crecimiento interanual", fmt(snapshot.growth, "%")], ["Cambio de pasajeros vs. año anterior", fmt(snapshot.delta)]].map(([label, value]) => {
    const item = document.createElement("div"); const title = document.createElement("p"); title.textContent = label!;
    const strong = document.createElement("strong"); strong.textContent = value!; item.append(title,strong); return item;
  }));
}

export function mountMarketControls(dataRoot: string): void {
  for (const id of ["market-period", "market-grain", "market-segment"]) document.getElementById(id)?.addEventListener("change", () => renderMarket(undefined));
  window.addEventListener("reader-tab-visible", event => {
    if ((event as CustomEvent).detail?.panelId === "panel-market") void mountDemand(dataRoot);
  });
}
