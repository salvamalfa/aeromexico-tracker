// Vuelos · airline selection (Dashboard v2). Aeroméxico keeps the v1
// sources (SEC quarterly KPIs, SEC monthly segment mix). Industria, Volaris
// and Viva read:
// - KPI cards: each airline's own quarterly report via executive.json's
//   entity records (ASM and RPM converted back from the km values the
//   payload stores; RPM is N/D where the report does not publish it);
// - mix chart: AFAC passengers by airline and segment (market.json), the
//   same source for all of them.
// The route map is still Grupo Aeroméxico's until fase 3.

import type { Data, Layout } from "plotly.js";
import Plotly from "../../lib/plotly";
import { $, deltaDisplay, metricDisplay, priorPeriod, setDelta } from "./dom";
import { entityLabel, entityRecord, entityState } from "../executive/entities";
import { ENTITY_COLORS, type EntityKey } from "../shell/carriers";
import type { MarketPeriod, QuarterRecord } from "../../types/domain";

const KM_PER_MILE = 1.609344;
const KPI_KEYS = ["passengers", "asm_miles", "rpm_miles", "load_factor"] as const;
type KpiKey = (typeof KPI_KEYS)[number];

function kpiValue(entity: EntityKey, periodId: string, key: KpiKey): number | null {
  const record = entityRecord(entity, periodId);
  if (!record) return null;
  if (key === "passengers") return record.passengers;
  if (key === "asm_miles") return record.ask_km / KM_PER_MILE;
  if (key === "rpm_miles") return record.rpk_km == null ? null : record.rpk_km / KM_PER_MILE;
  return record.load_factor;
}

export function renderEntityKpis(entity: EntityKey, periodId: string): void {
  for (const key of KPI_KEYS) {
    const value = kpiValue(entity, periodId, key);
    $(`flight-kpi-${key}`)!.textContent = metricDisplay(key, value);
    const points = key === "load_factor";
    setDelta(`flight-kpi-${key}-qoq`, deltaDisplay(value, kpiValue(entity, priorPeriod(periodId), key), points));
    setDelta(`flight-kpi-${key}-yoy`, deltaDisplay(value, kpiValue(entity, priorPeriod(periodId, 1), key), points));
  }
}

interface SegmentPoint {
  period_id: string;
  label: string;
  date: string;
  domestic: number | null;
  international: number | null;
}

function quarterStartDate(periodId: string): string {
  const month = (Number(periodId.slice(-1)) - 1) * 3 + 1;
  return `${periodId.slice(0, 4)}-${String(month).padStart(2, "0")}-01`;
}

function segmentPoints(entity: EntityKey, periods: MarketPeriod[], monthly: boolean): SegmentPoint[] {
  return periods.map((period) => {
    const pick = (segment: "domestic" | "international") => {
      const block = period.segments[segment];
      const item = entity === "INDUSTRY" ? block.industry : block.carriers[entity];
      return item?.passengers ?? null;
    };
    return {
      period_id: period.period_id,
      label: period.period_label,
      date: monthly ? `${period.period_id.slice(0, 4)}-${period.period_id.slice(5, 7)}-01` : quarterStartDate(period.period_id),
      domestic: pick("domestic"),
      international: pick("international"),
    };
  });
}

// AFAC mix for Industria/Volaris/Viva: for one entity the same stacked
// domestic + international bars as v1; for several, grouped bars per
// entity with the international part stacked on its domestic base.
export function renderEntityMix(entities: EntityKey[], record: QuarterRecord, period: "quarter" | "month"): void {
  const market = entityState.market;
  if (!market) return;
  const periods = period === "quarter" ? market.quarters : market.months;
  const single = entities.length === 1;
  const traces: Data[] = [];
  for (const key of entities) {
    const points = segmentPoints(key, periods, period === "month");
    const x = points.map((point) => point.date);
    const color = single ? null : ENTITY_COLORS[key];
    const name = entityLabel(key);
    traces.push({
      type: "bar", x, y: points.map((p) => p.domestic),
      name: single ? "Nacional" : `${name} · nacional`,
      offsetgroup: key, legendgroup: key, customdata: points.map((p) => p.label),
      marker: { color: color ?? "#003087" },
      hovertemplate: `<b>%{customdata}</b><br>${name} nacional %{y:,.0f}<extra></extra>`,
    } as Data);
    traces.push({
      type: "bar", x, y: points.map((p) => p.international),
      base: points.map((p) => p.domestic ?? 0),
      name: single ? "Internacional" : `${name} · internacional`,
      offsetgroup: key, legendgroup: key, customdata: points.map((p) => p.label),
      marker: { color: color ?? "#c99400", opacity: single ? 1 : 0.5 },
      hovertemplate: `<b>%{customdata}</b><br>${name} internacional %{y:,.0f}<extra></extra>`,
    } as Data);
  }
  const first = periods[0]?.period_id;
  const last = periods[periods.length - 1]?.period_id;
  const start = new Date(`${first && period === "quarter" ? quarterStartDate(first) : `${first?.slice(0, 4)}-${first?.slice(5, 7)}-01`}T00:00:00Z`);
  const end = new Date(`${last && period === "quarter" ? quarterStartDate(last) : `${last?.slice(0, 4)}-${last?.slice(5, 7)}-01`}T00:00:00Z`);
  const padding = period === "quarter" ? 45 : 15;
  start.setUTCDate(start.getUTCDate() - padding);
  end.setUTCDate(end.getUTCDate() + padding);
  const layout: Partial<Layout> = {
    barmode: "group", bargap: 0.22, bargroupgap: 0.05, height: $("mix-chart")!.clientHeight || 430,
    margin: { l: 58, r: 18, t: 46, b: 68 },
    paper_bgcolor: "rgba(0,0,0,0)", plot_bgcolor: "rgba(0,0,0,0)",
    font: { family: 'Inter, "Segoe UI", sans-serif', color: "#182233", size: 10 },
    legend: { orientation: "h", y: 1.17, x: 0 },
    xaxis: { showgrid: false, tickformat: period === "quarter" ? "%Y" : "%b %Y", range: [start.toISOString(), end.toISOString()] },
    yaxis: { rangemode: "tozero", gridcolor: "#e7ebf1", tickformat: ".2s", title: { text: "Pasajeros" } },
    shapes: [{
      type: "rect", xref: "x", yref: "paper", x0: record.metrics.passengers.period_start,
      x1: record.metrics.passengers.period_end, y0: 0, y1: 1,
      fillcolor: "rgba(0,48,135,.06)", line: { color: "rgba(0,48,135,.32)", width: 1, dash: "dot" }, layer: "below",
    }],
    hovermode: "closest",
    hoverlabel: { align: "left", bgcolor: "#ffffff", bordercolor: "#b9c8d9", font: { color: "#182233", size: 11 } },
  };
  void Plotly.react("mix-chart", traces, layout, { displayModeBar: false, responsive: true });
}
