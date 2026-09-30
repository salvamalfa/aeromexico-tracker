// The three panel-economy Plotly charts (unit economics, volume vs. RASK,
// load factor vs. RASK). Direct port of src/dashboard/assets/
// executive_summary.js's renderUnitEconomics/renderVolumeMonetization/
// renderLoadMonetization for one airline; the multi-airline modes of
// Dashboard v2 live in ./compare.ts and the shared helpers in ./chart-common.ts.

import type { Data } from "plotly.js";
import Plotly from "../../lib/plotly";
import { $ } from "../flights/dom";
import { entityLabel, entityRecords } from "../executive/entities";
import type { EntityKey } from "../shell/carriers";
import {
  UNIT_SUBTITLE, bindDefaultHover, colors, commonLayout, horizontalQuarterTicks, marginLegend,
  plotConfig, selectedHover, setSubtitle, signedTwoDecimals, visibleUnitRecords,
} from "./chart-common";
import { renderIndustryVolume, renderLoadComparison, renderUnitComparison, renderVolumeComparison } from "./compare";

const VOLUME_SUBTITLE = "Las barras indican el número de pasajeros; la línea, el RASK.";

window.addEventListener("reader-tab-visible", () => {
  selectedHover("unit-chart");
  selectedHover("volume-chart");
  marginLegend();
});

let unitEntities: EntityKey[] = ["AEROMEXICO"];

export function setUnitEntities(entities: EntityKey[]): void {
  unitEntities = entities;
}

export function renderUnitEconomics(): void {
  const rangeValue = ($("unit-range") as HTMLSelectElement).value;
  const metricControl = $("unit-metric-control");
  if (metricControl) metricControl.hidden = unitEntities.length < 2;
  if (unitEntities.length > 1) {
    renderUnitComparison(unitEntities, rangeValue);
    return;
  }
  const entity = unitEntities[0]!;
  setSubtitle("unit-title", entity === "AEROMEXICO" ? "RASK vs. CASK + Margen unitario" : `RASK vs. CASK + Margen unitario · ${entityLabel(entity)}`);
  setSubtitle("unit-subtitle", UNIT_SUBTITLE);
  const visibleRecords = visibleUnitRecords(rangeValue, entityRecords(entity));
  const visibleLabels = visibleRecords.map((record) => record.period_label);
  const tickRecords = horizontalQuarterTicks(visibleRecords);
  const marginColors = visibleRecords.map((record) =>
    record.unit_margin_cents_per_km >= 0 ? "rgba(8,127,101,0.36)" : "rgba(227,28,35,0.28)"
  );
  const traces: Data[] = [
    {
      x: visibleLabels,
      y: visibleRecords.map((record) => record.unit_margin_cents_per_km),
      name: "Margen unitario",
      type: "bar",
      yaxis: "y2",
      opacity: 0.72,
      textposition: "none",
      marker: {
        color: marginColors,
        line: { color: visibleRecords.map((r) => (r.unit_margin_cents_per_km >= 0 ? colors.green : colors.red)), width: 1 },
      },
    },
    {
      x: visibleLabels,
      y: visibleRecords.map((record) => record.rask_cents_per_km),
      name: "RASK",
      type: "scatter",
      mode: "lines+markers",
      xaxis: "x",
      yaxis: "y",
      line: { color: colors.blue, width: 3 },
      marker: { color: "#ffffff", line: { color: colors.blue, width: 2 }, size: 7 },
    },
    {
      x: visibleLabels,
      y: visibleRecords.map((record) => record.cask_cents_per_km),
      name: "CASK",
      type: "scatter",
      mode: "lines+markers",
      xaxis: "x",
      yaxis: "y",
      line: { color: colors.red, width: 2.4, dash: "dash" },
      marker: { color: "#ffffff", line: { color: colors.red, width: 2 }, size: 6 },
    },
  ];
  for (const trace of traces) {
    (trace as Record<string, unknown>).customdata = visibleRecords.map((r) => [
      r.rask_cents_per_km, r.cask_cents_per_km, signedTwoDecimals(r.unit_margin_cents_per_km),
    ]);
    (trace as Record<string, unknown>).hovertemplate =
      "<b>%{x}</b><br>RASK %{customdata[0]:.2f}<br>CASK %{customdata[1]:.2f}<br>Margen unitario %{customdata[2]}<br>¢ USD por asiento-kilómetro<extra></extra>";
  }
  const layout = commonLayout(365);
  Object.assign(layout, {
    hovermode: "closest",
    bargap: 0.34,
    barmode: "overlay",
    xaxis: {
      categoryorder: "array", categoryarray: visibleLabels, tickmode: "array",
      tickvals: tickRecords.map((r) => r.period_label), ticktext: tickRecords.map((r) => r.period_label),
      tickangle: 0, tickfont: { size: 8 }, showgrid: false,
    },
    yaxis: { title: { text: "¢ USD por ASK-km", font: { size: 10 } }, gridcolor: colors.grid, zeroline: false, tickformat: ".1f" },
    yaxis2: {
      title: { text: "Margen (¢ USD por ASK-km)", font: { size: 10 } }, overlaying: "y", side: "right",
      showgrid: false, zeroline: true, zerolinecolor: colors.ink, zerolinewidth: 1, tickformat: "+.1f", hoverformat: "+.2f",
    },
  });
  Plotly.react("unit-chart", traces, layout, plotConfig).then(() => {
    bindDefaultHover("unit-chart");
    marginLegend();
    selectedHover("unit-chart");
  });
}

let volumeEntities: EntityKey[] = ["AEROMEXICO"];

export function setVolumeEntities(entities: EntityKey[]): void {
  volumeEntities = entities;
}

export function renderVolumeMonetization(): void {
  if (volumeEntities.length > 1) {
    renderVolumeComparison(volumeEntities);
    return;
  }
  if (volumeEntities[0] === "INDUSTRY") {
    renderIndustryVolume();
    return;
  }
  setSubtitle("volume-subtitle", VOLUME_SUBTITLE);
  const records = entityRecords(volumeEntities[0]!);
  const labels = records.map((record) => record.period_label);
  const traces: Data[] = [
    {
      x: labels,
      y: records.map((record) => record.passengers / 1_000_000),
      name: "Pasajeros",
      type: "bar",
      marker: { color: "rgba(185,103,0,0.34)", line: { color: colors.amber, width: 1 } },
    },
    {
      x: labels,
      y: records.map((record) => record.rask_cents_per_km),
      name: "RASK",
      type: "scatter",
      mode: "lines+markers",
      yaxis: "y2",
      line: { color: colors.blue, width: 2.6 },
      marker: { color: "#ffffff", line: { color: colors.blue, width: 2 }, size: 6 },
    },
  ];
  for (const trace of traces) {
    (trace as Record<string, unknown>).customdata = records.map((r) => [r.passengers / 1e6, r.rask_cents_per_km]);
    (trace as Record<string, unknown>).hovertemplate =
      "<b>%{x}</b><br>Pasajeros %{customdata[0]:.2f} M<br>RASK %{customdata[1]:.2f} ¢ USD por asiento-kilómetro<extra></extra>";
  }
  const layout = commonLayout(315);
  Object.assign(layout, {
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

const YEAR_COLORS: Record<string, string> = {
  "2021": "#e31c23", "2022": "#d66a00", "2023": "#087f65", "2024": "#003087", "2025": "#6d3cc7", "2026": "#2894c7",
};

let loadEntities: EntityKey[] = ["AEROMEXICO"];

export function setLoadEntities(entities: EntityKey[]): void {
  loadEntities = entities;
}

export function renderLoadMonetization(periodId: string): void {
  if (loadEntities.length > 1) {
    renderLoadComparison(periodId, loadEntities);
    return;
  }
  setSubtitle("load-subtitle", "Cada punto es un trimestre; los colores identifican el año.");
  const records = entityRecords(loadEntities[0]!);
  const current = records.find((record) => record.period_id === periodId);
  const years = [...new Set(records.map((record) => record.period_id.slice(0, 4)))];
  const traces: Data[] = years.map((year) => {
    const yearRecords = records.filter((record) => record.period_id.startsWith(year));
    return {
      x: yearRecords.map((record) => record.load_factor_reported * 100),
      y: yearRecords.map((record) => record.rask_cents_per_km),
      text: yearRecords.map((record) => record.period_label),
      customdata: yearRecords.map((record) => [
        (record.ask_km / 1_000_000_000).toFixed(2),
        signedTwoDecimals(record.unit_margin_cents_per_km),
        (record.passengers / 1_000_000).toFixed(2),
      ]),
      name: year,
      type: "scatter",
      mode: "text+markers",
      textposition: "top center",
      textfont: { size: 8, color: colors.muted },
      marker: { size: 13, color: YEAR_COLORS[year], line: { color: "#ffffff", width: 1.2 } },
      hovertemplate:
        "%{text}<br>Ocupación %{x:.1f}%<br>RASK %{y:.2f} ¢ USD por ASK-km<br>ASK %{customdata[0]} mil M<br>Margen %{customdata[1]} ¢ USD por ASK-km<br>Pasajeros %{customdata[2]} M<extra></extra>",
    } as Data;
  });
  const selectedTrace: Data = {
    x: current ? [current.load_factor_reported * 100] : [],
    y: current ? [current.rask_cents_per_km] : [],
    name: `Seleccionado: ${current?.period_label ?? ""}`,
    showlegend: false,
    type: "scatter",
    mode: "markers",
    marker: { symbol: "circle-open", size: 27, color: colors.red, line: { color: colors.red, width: 3 } },
    hoverinfo: "skip",
  };
  const layout = commonLayout(315);
  Object.assign(layout, {
    hovermode: "closest",
    legend: { orientation: "h", x: 0, y: 1.12, font: { size: 9 } },
    xaxis: { title: { text: "Factor de ocupación (%)", font: { size: 10 } }, gridcolor: colors.grid, ticksuffix: "%" },
    yaxis: { title: { text: "RASK (¢ USD por ASK-km)", font: { size: 10 } }, gridcolor: colors.grid, tickformat: ".1f", hoverformat: ".2f" },
  });
  Plotly.react("load-chart", [...traces, selectedTrace], layout, plotConfig);
}
