// The stacked domestic/international passenger bar chart with a total
// line. Ported from src/dashboard/assets/flights.js::renderMix.

import type { Data, Layout } from "plotly.js";
import Plotly from "../../lib/plotly";
import { $, dateLabel } from "./dom";
import { state } from "./state";
import type { MonthlyPassengerPoint, QuarterRecord } from "../../types/domain";

function quarterForDate(iso: string): string {
  const year = iso.slice(0, 4);
  const month = Number(iso.slice(5, 7));
  return `${year}Q${Math.floor((month - 1) / 3) + 1}`;
}

interface QuarterPoint {
  period_id: string;
  period_label: string;
  date: string;
  domestic: number;
  international: number;
  total_segment_sum: number;
}

export function renderMix(record: QuarterRecord): void {
  const series = state.monthlyPassengers!;
  const monthlyPoints = series.records.map((point) => ({ ...point, period_label: dateLabel(point.date) }));
  const quarterGroups = new Map<string, QuarterPoint>();
  monthlyPoints.forEach((point) => {
    const periodId = quarterForDate(point.date);
    let quarter = quarterGroups.get(periodId);
    if (!quarter) {
      const startMonth = (Number(periodId.slice(-1)) - 1) * 3 + 1;
      quarter = {
        period_id: periodId,
        period_label: `${periodId.slice(-1)}T${periodId.slice(2, 4)}`,
        date: `${periodId.slice(0, 4)}-${String(startMonth).padStart(2, "0")}-01`,
        domestic: 0, international: 0, total_segment_sum: 0,
      };
      quarterGroups.set(periodId, quarter);
    }
    quarter.domestic += point.domestic;
    quarter.international += point.international;
    quarter.total_segment_sum += point.total_segment_sum;
  });
  const points: Array<MonthlyPassengerPoint & { period_label: string }> | QuarterPoint[] =
    state.passengerPeriod === "quarter" ? [...quarterGroups.values()] : monthlyPoints;
  const narrow = window.matchMedia("(max-width: 736px)").matches;
  const veryNarrow = window.matchMedia("(max-width: 420px)").matches;
  const rangeStart = new Date(`${points[0]!.date}T00:00:00Z`);
  const rangeEnd = new Date(`${points[points.length - 1]!.date}T00:00:00Z`);
  const paddingDays = state.passengerPeriod === "quarter" ? 45 : 15;
  rangeStart.setUTCDate(rangeStart.getUTCDate() - paddingDays);
  rangeEnd.setUTCDate(rangeEnd.getUTCDate() + paddingDays);
  const hoverData = points.map((point) => {
    const heading =
      state.passengerPeriod === "quarter"
        ? (point as QuarterPoint).period_label
        : new Intl.DateTimeFormat("es-MX", { month: "long", year: "numeric", timeZone: "UTC" }).format(
            new Date(`${point.date}T00:00:00Z`)
          );
    const total = point.total_segment_sum;
    return [heading, total, point.domestic, point.international, total ? point.domestic / total : 0, total ? point.international / total : 0];
  });
  const hoverTemplate = [
    "<b>%{customdata[0]}</b>",
    "<span style='color:#182233'>■</span> <b>Total</b> %{customdata[1]:,.0f}",
    "<span style='color:#003087'>■</span> Nacional %{customdata[2]:,.0f} (%{customdata[4]:.1%})",
    "<span style='color:#c99400'>■</span> Internacional %{customdata[3]:,.0f} (%{customdata[5]:.1%})",
    "<extra></extra>",
  ].join("<br>");
  const traces: Data[] = [
    {
      type: "bar", x: points.map((point) => point.date), y: points.map((point) => point.domestic),
      name: "Nacional", marker: { color: "#003087" },
      customdata: hoverData, hovertemplate: hoverTemplate,
    },
    {
      type: "bar", x: points.map((point) => point.date), y: points.map((point) => point.international),
      name: "Internacional", marker: { color: "#c99400" },
      customdata: hoverData, hovertemplate: hoverTemplate,
    },
    {
      type: "scatter", mode: "lines+markers", x: points.map((point) => point.date),
      y: points.map((point) => point.total_segment_sum), name: "Total",
      connectgaps: false, line: { color: "#182233", width: 2.5 },
      marker: { color: "#fff", line: { color: "#182233", width: 1.5 }, size: 6 },
      customdata: hoverData, hovertemplate: hoverTemplate,
    } as Data,
  ];
  const layout: Partial<Layout> = {
    barmode: "stack", bargap: 0.22, height: $("mix-chart")!.clientHeight || 430,
    margin: { l: 58, r: 18, t: 46, b: 68 },
    paper_bgcolor: "rgba(0,0,0,0)", plot_bgcolor: "rgba(0,0,0,0)",
    font: { family: 'Inter, "Segoe UI", sans-serif', color: "#182233", size: 10 },
    legend: { orientation: "h", y: 1.17, x: 0 },
    xaxis: {
      showgrid: false, tickformat: state.passengerPeriod === "quarter" ? "%Y" : "%b %Y",
      dtick: state.passengerPeriod === "quarter" ? (veryNarrow ? "M24" : "M12") : (veryNarrow ? "M24" : narrow ? "M12" : "M6"), tickangle: 0,
      range: [rangeStart.toISOString(), rangeEnd.toISOString()], tickfont: { size: narrow ? 8 : 10 },
    },
    yaxis: { rangemode: "tozero", gridcolor: "#e7ebf1", tickformat: ".2s", title: { text: "Pasajeros" } },
    shapes: [{
      type: "rect", xref: "x", yref: "paper", x0: record.metrics.passengers.period_start,
      x1: record.metrics.passengers.period_end, y0: 0, y1: 1,
      fillcolor: "rgba(0,48,135,.06)", line: { color: "rgba(0,48,135,.32)", width: 1, dash: "dot" }, layer: "below",
    }],
    annotations: [{
      x: record.metrics.passengers.period_start, y: 1, xref: "x", yref: "paper", xanchor: "left", yanchor: "bottom",
      text: record.period_label, showarrow: false, font: { size: 9, color: "#003087" },
    }],
    hovermode: "closest",
    hoverlabel: { align: "left", bgcolor: "#ffffff", bordercolor: "#b9c8d9", font: { color: "#182233", size: 11 } },
  };
  void Plotly.react("mix-chart", traces, layout, { displayModeBar: false, responsive: true });
}
