// Shared helpers for the panel-economy Plotly charts (./charts.ts and
// ./compare.ts): palette, layout, the "selected quarter" hover and the
// airline-line styles of Dashboard v2.

import type { Layout } from "plotly.js";
import Plotly, { type PlotlyHTMLElement } from "../../lib/plotly";
import { $ } from "../flights/dom";
import { state } from "../executive/state";
import { ENTITY_COLORS, type EntityKey } from "../shell/carriers";
import type { ExecutiveRecord } from "../../types/domain";

export const colors = {
  blue: "#003087", blueDark: "#001f5b", red: "#e31c23", gold: "#c99400",
  amber: "#b96700", violet: "#6d3cc7", green: "#087f65", grid: "#e8edf4",
  muted: "#657188", ink: "#182233",
};
export const plotConfig = { displayModeBar: false, responsive: true, scrollZoom: false, staticPlot: false };
export const signedTwoDecimals = (value: number): string => `${value >= 0 ? "+" : ""}${Number(value).toFixed(2)}`;

export function selectedHover(id: string): void {
  const graph = $(id) as PlotlyHTMLElement | null;
  if (!graph || !graph.data || !graph.getBoundingClientRect().width) return;
  const record = state.records[state.periodIndex];
  if (!record) return;
  const label = record.period_label;
  const firstTrace = graph.data[0] as { x?: unknown[] } | undefined;
  const point = (firstTrace?.x ?? []).indexOf(label);
  if (point < 0) {
    Plotly.Fx.unhover(graph);
    return;
  }
  Plotly.Fx.hover(graph, [{ curveNumber: 1, pointNumber: point }]);
}

export function marginLegend(): void {
  const graph = $("unit-chart");
  const svg = graph?.querySelector("svg.main-svg");
  if (!svg) return;
  let gradient = svg.querySelector("#margin-legend-gradient");
  if (!gradient) {
    const ns = "http://www.w3.org/2000/svg";
    gradient = document.createElementNS(ns, "linearGradient");
    gradient.setAttribute("id", "margin-legend-gradient");
    for (const [offset, color] of [["0%", colors.green], ["50%", colors.green], ["50%", colors.red], ["100%", colors.red]]) {
      const stop = document.createElementNS(ns, "stop");
      stop.setAttribute("offset", offset!);
      stop.setAttribute("stop-color", color!);
      gradient.appendChild(stop);
    }
    svg.querySelector("defs")!.appendChild(gradient);
  }
  graph!.querySelectorAll(".legend .traces").forEach((row) => {
    if (row.querySelector(".legendtext")?.textContent !== "Margen unitario") return;
    row.querySelectorAll<HTMLElement>(".legendpoints path").forEach((path) => {
      path.style.fill = "url(#margin-legend-gradient)";
      path.style.fillOpacity = "1";
    });
  });
}

export function bindDefaultHover(id: string): void {
  const graph = $(id) as PlotlyHTMLElement;
  if (graph.dataset.defaultHover) return;
  graph.dataset.defaultHover = "true";
  graph.addEventListener("mouseleave", () => selectedHover(id));
  if (id === "unit-chart") graph.on("plotly_afterplot", marginLegend);
}

export function commonLayout(height: number): Partial<Layout> {
  return {
    height,
    paper_bgcolor: "rgba(0,0,0,0)",
    plot_bgcolor: "rgba(0,0,0,0)",
    font: { family: 'Inter, "Segoe UI", system-ui, sans-serif', color: colors.ink, size: 10 },
    hoverlabel: { bgcolor: "#ffffff", bordercolor: "#cbd5e1", font: { color: colors.ink, size: 11 } },
    legend: { orientation: "h", x: 0, y: 1.08, font: { size: 10 } },
    margin: { l: 52, r: 24, t: 30, b: 42 },
    hovermode: "x unified",
  };
}

export function visibleUnitRecords(rangeValue: string, records: ExecutiveRecord[] = state.records) {
  if (rangeValue === "all") return records;
  // The range counts quarters of the page's timeline (Aeroméxico's, the
  // longest), so every entity shows the same calendar window.
  const window = new Set(state.records.slice(-Number(rangeValue)).map((record) => record.period_id));
  return records.filter((record) => window.has(record.period_id));
}

export function setSubtitle(id: string, text: string): void {
  const node = document.getElementById(id);
  if (node) node.textContent = text;
}

export const UNIT_SUBTITLE =
  "Cuando RASK supera CASK, la operación genera utilidad por cada asiento-kilómetro. Las barras muestran el margen unitario en ¢ USD por ASK-km para cada trimestre.";
export const METRIC_LABELS: Record<string, string> = {
  rask_cents_per_km: "RASK",
  cask_cents_per_km: "CASK",
  cask_ex_fuel_cents_per_km: "CASK ex-fuel",
  unit_margin_cents_per_km: "Margen unitario",
};

export function entityLine(key: EntityKey): Record<string, unknown> {
  const color = ENTITY_COLORS[key];
  return key === "INDUSTRY"
    ? { line: { color, width: 2.4, dash: "dash" }, marker: { color: "#ffffff", line: { color, width: 2 }, size: 6 } }
    : { line: { color, width: 2.6 }, marker: { color: "#ffffff", line: { color, width: 2 }, size: 6 } };
}

export function horizontalQuarterTicks<T>(visibleRecords: T[]): T[] {
  const compact = window.innerWidth <= 700;
  const stride = compact && visibleRecords.length > 12 ? 4 : compact && visibleRecords.length > 8 ? 2 : 1;
  return visibleRecords.filter((_, index) => index % stride === 0 || index === visibleRecords.length - 1);
}
