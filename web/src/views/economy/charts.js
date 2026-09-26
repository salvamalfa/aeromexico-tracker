// The three panel-economy Plotly charts (unit economics, volume vs. RASK,
// load factor vs. RASK). Direct port of src/dashboard/assets/
// executive_summary.js's renderUnitEconomics/renderVolumeMonetization/
// renderLoadMonetization, kept in one module since the published page
// shares their color palette, layout helper and hover/legend behavior.

import { $ } from "../flights/dom.js";
import { state } from "../executive/state.js";

const colors = {
  blue: "#003087", blueDark: "#001f5b", red: "#e31c23", gold: "#c99400",
  amber: "#b96700", violet: "#6d3cc7", green: "#087f65", grid: "#e8edf4",
  muted: "#657188", ink: "#182233",
};
const plotConfig = { displayModeBar: false, responsive: true, scrollZoom: false, staticPlot: false };
const signedTwoDecimals = (value) => `${value >= 0 ? "+" : ""}${Number(value).toFixed(2)}`;

function selectedHover(id) {
  const graph = $(id);
  if (!graph || !graph.data || !graph.getBoundingClientRect().width) return;
  const record = state.records[state.periodIndex];
  const label = record.period_label;
  const point = graph.data[0].x.indexOf(label);
  if (point < 0) { window.Plotly.Fx.unhover(graph); return; }
  window.Plotly.Fx.hover(graph, [{ curveNumber: 1, pointNumber: point }]);
}

function marginLegend() {
  const graph = $("unit-chart");
  const svg = graph?.querySelector("svg.main-svg");
  if (!svg) return;
  let gradient = svg.querySelector("#margin-legend-gradient");
  if (!gradient) {
    const ns = "http://www.w3.org/2000/svg";
    gradient = document.createElementNS(ns, "linearGradient");
    gradient.id = "margin-legend-gradient";
    for (const [offset, color] of [["0%", colors.green], ["50%", colors.green], ["50%", colors.red], ["100%", colors.red]]) {
      const stop = document.createElementNS(ns, "stop");
      stop.setAttribute("offset", offset);
      stop.setAttribute("stop-color", color);
      gradient.appendChild(stop);
    }
    svg.querySelector("defs").appendChild(gradient);
  }
  graph.querySelectorAll(".legend .traces").forEach((row) => {
    if (row.querySelector(".legendtext")?.textContent !== "Margen unitario") return;
    row.querySelectorAll(".legendpoints path").forEach((path) => {
      path.style.fill = "url(#margin-legend-gradient)";
      path.style.fillOpacity = "1";
    });
  });
}

function bindDefaultHover(id) {
  const graph = $(id);
  if (graph.dataset.defaultHover) return;
  graph.dataset.defaultHover = "true";
  graph.addEventListener("mouseleave", () => selectedHover(id));
  if (id === "unit-chart") graph.on("plotly_afterplot", marginLegend);
}

window.addEventListener("reader-tab-visible", () => {
  selectedHover("unit-chart");
  selectedHover("volume-chart");
  marginLegend();
});

function commonLayout(height) {
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

function visibleUnitRecords(rangeValue) {
  if (rangeValue === "all") return state.records;
  return state.records.slice(-Number(rangeValue));
}

function horizontalQuarterTicks(visibleRecords) {
  const compact = window.innerWidth <= 700;
  const stride = compact && visibleRecords.length > 12 ? 4 : compact && visibleRecords.length > 8 ? 2 : 1;
  return visibleRecords.filter((_, index) => index % stride === 0 || index === visibleRecords.length - 1);
}

export function renderUnitEconomics() {
  const rangeValue = $("unit-range").value;
  const visibleRecords = visibleUnitRecords(rangeValue);
  const visibleLabels = visibleRecords.map((record) => record.period_label);
  const tickRecords = horizontalQuarterTicks(visibleRecords);
  const marginColors = visibleRecords.map((record) =>
    record.unit_margin_cents_per_km >= 0 ? "rgba(8,127,101,0.36)" : "rgba(227,28,35,0.28)"
  );
  const traces = [
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
    trace.customdata = visibleRecords.map((r) => [r.rask_cents_per_km, r.cask_cents_per_km, signedTwoDecimals(r.unit_margin_cents_per_km)]);
    trace.hovertemplate = "<b>%{x}</b><br>RASK %{customdata[0]:.2f}<br>CASK %{customdata[1]:.2f}<br>Margen unitario %{customdata[2]}<br>¢ USD por asiento-kilómetro<extra></extra>";
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
  window.Plotly.react("unit-chart", traces, layout, plotConfig).then(() => {
    bindDefaultHover("unit-chart");
    marginLegend();
    selectedHover("unit-chart");
  });
}

export function renderVolumeMonetization() {
  const labels = state.records.map((record) => record.period_label);
  const traces = [
    {
      x: labels,
      y: state.records.map((record) => record.passengers / 1_000_000),
      name: "Pasajeros",
      type: "bar",
      marker: { color: "rgba(185,103,0,0.34)", line: { color: colors.amber, width: 1 } },
    },
    {
      x: labels,
      y: state.records.map((record) => record.rask_cents_per_km),
      name: "RASK",
      type: "scatter",
      mode: "lines+markers",
      yaxis: "y2",
      line: { color: colors.blue, width: 2.6 },
      marker: { color: "#ffffff", line: { color: colors.blue, width: 2 }, size: 6 },
    },
  ];
  for (const trace of traces) {
    trace.customdata = state.records.map((r) => [r.passengers / 1e6, r.rask_cents_per_km]);
    trace.hovertemplate = "<b>%{x}</b><br>Pasajeros %{customdata[0]:.2f} M<br>RASK %{customdata[1]:.2f} ¢ USD por asiento-kilómetro<extra></extra>";
  }
  const layout = commonLayout(315);
  Object.assign(layout, {
    bargap: 0.42,
    hovermode: "closest",
    xaxis: { categoryorder: "array", categoryarray: labels, tickangle: -45, tickfont: { size: 8 }, showgrid: false },
    yaxis: { title: { text: "Pasajeros (M)", font: { size: 10 } }, rangemode: "tozero", gridcolor: colors.grid, tickformat: ".1f" },
    yaxis2: { title: { text: "RASK (¢ USD)", font: { size: 10 } }, overlaying: "y", side: "right", showgrid: false, tickformat: ".1f" },
  });
  window.Plotly.react("volume-chart", traces, layout, plotConfig).then(() => {
    bindDefaultHover("volume-chart");
    selectedHover("volume-chart");
  });
}

export function renderLoadMonetization(periodId) {
  const current = state.records[state.periodIndex];
  const yearColors = { 2021: "#e31c23", 2022: "#d66a00", 2023: "#087f65", 2024: "#003087", 2025: "#6d3cc7", 2026: "#2894c7" };
  const years = [...new Set(state.records.map((record) => record.period_id.slice(0, 4)))];
  const traces = years.map((year) => {
    const yearRecords = state.records.filter((record) => record.period_id.startsWith(year));
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
      mode: "markers+text",
      textposition: "top center",
      textfont: { size: 8, color: colors.muted },
      marker: { size: 13, color: yearColors[year], line: { color: "#ffffff", width: 1.2 } },
      hovertemplate: "%{text}<br>Ocupación %{x:.1f}%<br>RASK %{y:.2f} ¢ USD por ASK-km<br>ASK %{customdata[0]} mil M<br>Margen %{customdata[1]} ¢ USD por ASK-km<br>Pasajeros %{customdata[2]} M<extra></extra>",
    };
  });
  const selectedTrace = {
    x: [current.load_factor_reported * 100],
    y: [current.rask_cents_per_km],
    name: `Seleccionado: ${current.period_label}`,
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
  window.Plotly.react("load-chart", [...traces, selectedTrace], layout, plotConfig);
}
