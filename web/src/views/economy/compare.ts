// Dashboard v2 · comparison modes of the panel-economy charts: several
// airlines at once (one line or grouped bar per airline) and the Industria
// stacked-volume view. ./charts.ts dispatches here; with a single airline
// the v1 charts render unchanged.

import type { Data } from "plotly.js";
import Plotly from "../../lib/plotly";
import { $ } from "../flights/dom";
import { state } from "../executive/state";
import { entityLabel, entityRecords } from "../executive/entities";
import { CARRIER_KEYS, ENTITY_COLORS, type EntityKey } from "../shell/carriers";
import {
  METRIC_LABELS, bindDefaultHover, colors, commonLayout, entityLine, horizontalQuarterTicks,
  plotConfig, selectedHover, setSubtitle, visibleUnitRecords,
} from "./chart-common";


// Several entities: one line per entity for the chosen metric (Industria dashed).
export function renderUnitComparison(entities: EntityKey[], rangeValue: string): void {
  const metric = ($("unit-metric") as HTMLSelectElement).value;
  const label = METRIC_LABELS[metric] ?? metric;
  const timeline = visibleUnitRecords(rangeValue);
  const labels = timeline.map((record) => record.period_label);
  const tickRecords = horizontalQuarterTicks(timeline);
  const traces: Data[] = entities.map((key) => {
    const byPeriod = new Map(entityRecords(key).map((record) => [record.period_id, record]));
    return {
      x: labels,
      y: timeline.map((record) => {
        const value = byPeriod.get(record.period_id)?.[metric];
        return typeof value === "number" ? value : null;
      }),
      name: entityLabel(key),
      type: "scatter",
      mode: "lines+markers",
      connectgaps: false,
      ...entityLine(key),
      hovertemplate: `<b>%{x}</b><br>${entityLabel(key)} · ${label} %{y:.2f} ¢ USD por ASK-km<extra></extra>`,
    } as Data;
  });
  setSubtitle("unit-title", `${label} por aerolínea`);
  setSubtitle(
    "unit-subtitle",
    `${label} en ¢ USD por ASK-km. Industria (línea punteada) pondera a las tres aerolíneas por su ASK; una aerolínea sin dato en un trimestre queda en blanco.`
  );
  const layout = commonLayout(365);
  Object.assign(layout, {
    hovermode: "closest",
    xaxis: {
      categoryorder: "array", categoryarray: labels, tickmode: "array",
      tickvals: tickRecords.map((r) => r.period_label), ticktext: tickRecords.map((r) => r.period_label),
      tickangle: 0, tickfont: { size: 8 }, showgrid: false,
    },
    yaxis: {
      title: { text: "¢ USD por ASK-km", font: { size: 10 } }, gridcolor: colors.grid, tickformat: ".1f",
      zeroline: metric === "unit_margin_cents_per_km", zerolinecolor: colors.ink,
    },
  });
  Plotly.react("unit-chart", traces, layout, plotConfig).then(() => {
    bindDefaultHover("unit-chart");
    selectedHover("unit-chart");
  });
}

// Industria alone: one stacked bar per carrier (the total and who makes it
// up) plus the industry RASK line.
export function renderIndustryVolume(): void {
  const industry = entityRecords("INDUSTRY");
  const labels = industry.map((record) => record.period_label);
  const traces: Data[] = CARRIER_KEYS.map((key) => {
    const byPeriod = new Map(entityRecords(key).map((record) => [record.period_id, record]));
    return {
      x: labels,
      y: industry.map((record) => (byPeriod.get(record.period_id)?.passengers ?? 0) / 1_000_000),
      name: entityLabel(key),
      type: "bar",
      marker: { color: ENTITY_COLORS[key], opacity: 0.78, line: { color: "#ffffff", width: 1 } },
      hovertemplate: `<b>%{x}</b><br>${entityLabel(key)} %{y:.2f} M pasajeros<extra></extra>`,
    } as Data;
  });
  traces.push({
    x: labels,
    y: industry.map((record) => record.rask_cents_per_km),
    name: "RASK industria",
    type: "scatter",
    mode: "lines+markers",
    yaxis: "y2",
    ...entityLine("INDUSTRY"),
    hovertemplate: "<b>%{x}</b><br>RASK industria %{y:.2f} ¢ USD por ASK-km<extra></extra>",
  } as Data);
  setSubtitle("volume-subtitle", "Industria: las barras apilan los pasajeros de cada aerolínea; la línea, el RASK ponderado de la industria.");
  const layout = commonLayout(315);
  Object.assign(layout, {
    barmode: "stack",
    bargap: 0.42,
    hovermode: "closest",
    xaxis: { categoryorder: "array", categoryarray: labels, tickangle: -45, tickfont: { size: 8 }, showgrid: false },
    yaxis: { title: { text: "Pasajeros (M)", font: { size: 10 } }, rangemode: "tozero", gridcolor: colors.grid, tickformat: ".1f" },
    yaxis2: { title: { text: "RASK (¢ USD)", font: { size: 10 } }, overlaying: "y", side: "right", showgrid: false, tickformat: ".1f" },
  });
  Plotly.react("volume-chart", traces, layout, plotConfig).then(() => {
    bindDefaultHover("volume-chart");
    selectedHover("volume-chart");
  });
}

// Several entities: grouped bars side by side (never overlapped).
export function renderVolumeComparison(entities: EntityKey[]): void {
  const periods = [...new Set(entities.flatMap((key) => entityRecords(key).map((record) => record.period_id)))].sort();
  const labelByPeriod = new Map(state.records.map((record) => [record.period_id, record.period_label]));
  const labels = periods.map((id) => labelByPeriod.get(id) ?? id);
  const traces: Data[] = entities.map((key) => {
    const byPeriod = new Map(entityRecords(key).map((record) => [record.period_id, record]));
    return {
      x: labels,
      y: periods.map((id) => {
        const record = byPeriod.get(id);
        return record ? record.passengers / 1_000_000 : null;
      }),
      name: entityLabel(key),
      type: "bar",
      marker: { color: ENTITY_COLORS[key], opacity: key === "INDUSTRY" ? 0.45 : 0.82, line: { color: "#ffffff", width: 1 } },
      hovertemplate: `<b>%{x}</b><br>${entityLabel(key)} %{y:.2f} M pasajeros<extra></extra>`,
    } as Data;
  });
  setSubtitle("volume-subtitle", "Pasajeros por trimestre de cada selección, en barras lado a lado.");
  const layout = commonLayout(315);
  Object.assign(layout, {
    barmode: "group",
    bargap: 0.3,
    hovermode: "closest",
    xaxis: { categoryorder: "array", categoryarray: labels, tickangle: -45, tickfont: { size: 8 }, showgrid: false },
    yaxis: { title: { text: "Pasajeros (M)", font: { size: 10 } }, rangemode: "tozero", gridcolor: colors.grid, tickformat: ".1f" },
  });
  Plotly.react("volume-chart", traces, layout, plotConfig).then(() => bindDefaultHover("volume-chart"));
}


// Several entities: one color per entity; the selected quarter is ringed.
export function renderLoadComparison(periodId: string, loadEntities: EntityKey[]): void {
  const traces: Data[] = [];
  for (const key of loadEntities) {
    const records = entityRecords(key);
    traces.push({
      x: records.map((record) => record.load_factor_reported * 100),
      y: records.map((record) => record.rask_cents_per_km),
      text: records.map((record) => record.period_label),
      name: entityLabel(key),
      type: "scatter",
      mode: "markers",
      marker: {
        size: 11, color: ENTITY_COLORS[key], symbol: key === "INDUSTRY" ? "diamond" : "circle",
        opacity: records.map((record) => (record.period_id === periodId ? 1 : 0.55)),
        line: { color: "#ffffff", width: 1.2 },
      },
      hovertemplate: `${entityLabel(key)} %{text}<br>Ocupación %{x:.1f}%<br>RASK %{y:.2f} ¢ USD por ASK-km<extra></extra>`,
    } as Data);
    const current = records.find((record) => record.period_id === periodId);
    if (current) {
      traces.push({
        x: [current.load_factor_reported * 100], y: [current.rask_cents_per_km],
        showlegend: false, type: "scatter", mode: "markers", hoverinfo: "skip",
        marker: { symbol: "circle-open", size: 22, color: ENTITY_COLORS[key], line: { color: ENTITY_COLORS[key], width: 2.5 } },
      } as Data);
    }
  }
  setSubtitle("load-subtitle", "Cada punto es un trimestre; los colores identifican la aerolínea y el círculo, el trimestre analizado.");
  const layout = commonLayout(315);
  Object.assign(layout, {
    hovermode: "closest",
    legend: { orientation: "h", x: 0, y: 1.12, font: { size: 9 } },
    xaxis: { title: { text: "Factor de ocupación (%)", font: { size: 10 } }, gridcolor: colors.grid, ticksuffix: "%" },
    yaxis: { title: { text: "RASK (¢ USD por ASK-km)", font: { size: 10 } }, gridcolor: colors.grid, tickformat: ".1f", hoverformat: ".2f" },
  });
  Plotly.react("load-chart", traces, layout, plotConfig);
}
