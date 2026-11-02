import { seriesMixTooltip, scheduleMixTooltip } from "./mix-tooltip";
import { renderMixChartSource } from "./chart-sources";
// The stacked domestic/international passenger bar chart with a total
// line. Ported from src/dashboard/assets/flights.js::renderMix.

import { renderPassengerCoverage } from "./passenger-coverage";
import type { Data, Layout } from "plotly.js";
import Plotly from "../../lib/plotly";
import { $, dateLabel } from "./dom";
import { state } from "./state";
import type { MonthlyPassengerPoint, QuarterRecord } from "../../types/domain";
import { renderEntityMix } from "./carriers";
import { selection } from "../shell/carriers";
import { entityState } from "../executive/entities";

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
  // The current AFAC dataset is shared by every airline, including Grupo
  // Aeroméxico. The retained legacy series is only a fallback without market data.
  const entities = selection("mix");
  const source = $("mix-source-inline");
  const amOnly = !entities.length || (entities.length === 1 && entities[0] === "AEROMEXICO");
  const single = entities.length === 1 ? entities[0] : null;
  const corporateSeries = amOnly ? state.corporateMonthlyPassengers
    : single === "VIVA_AEROBUS" || single === "VOLARIS" ? state.corporatePeerMonthlyPassengers[single] : null;
  const corporateAvailable = !!corporateSeries?.records.length;
  const basisControl = $("passenger-basis-control");
  if (basisControl) basisControl.hidden = !corporateAvailable;
  const corporate = corporateAvailable && state.passengerBasis === "corporate";
  renderMixChartSource(corporate ? corporateSeries! : undefined);
  const periodControl = $("passenger-period") as HTMLSelectElement | null;
  if (periodControl) {
    const quarter = periodControl.querySelector<HTMLOptionElement>('option[value="quarter"]');
    if (quarter) quarter.disabled = corporate;
  }
  if (corporate) {
    state.passengerPeriod = "month";
    if (periodControl) periodControl.value = "month";
  }
  if (!corporate && (entityState.market || (entities.length && !amOnly))) {
    if (source) source.textContent = "AFAC · pasajeros por aerolínea (regular y fletamento)";
    renderEntityMix(entities.length ? entities : ["AEROMEXICO"], record, state.passengerPeriod);
    return;
  }
  const booked = corporate && corporateSeries && "reporting_status" in corporateSeries;
  if (source) {
    const company = corporateSeries?.entity === "VOLARIS" ? "Volaris" : corporateSeries?.entity === "VIVA_AEROBUS" ? "Viva (marca)" : "Aeroméxico IR";
    const reporting = corporateSeries && "reporting_status" in corporateSeries ? {
      preliminary: "preliminar", preliminary_unaudited: "preliminar, no auditado", unaudited: "no auditado",
    }[corporateSeries.reporting_status] ?? corporateSeries.reporting_status : "";
    const attribution = corporateSeries?.entity === "VIVA_AEROBUS"
      ? "El reporte identifica la marca Viva; no establece un operador legal."
      : corporateSeries?.entity === "VOLARIS" ? "Universo reportado por Volaris; no censo de operadores." : "";
    source.textContent = corporate
      ? `${company} · ${booked ? "reservaciones de tramos, no pasajeros transportados" : "pasajeros del reporte corporativo no auditado"}; mes y comparativo anual reportados en la misma edición; incluye fletamento. ${booked ? reporting + ". " : ""}Documento ${corporateSeries!.documentary_date}; captura ${corporateSeries!.captured_at.slice(0, 10)}. No equivale a AFAC.${booked ? " " + attribution : ""}`
      : "AFAC · pasajeros transportados; serie histórica y ediciones verificadas";
    if (corporate) {
      const link = document.createElement("a");
      link.href = corporateSeries!.source_url;
      link.textContent = " Reporte fuente";
      link.target = "_blank";
      link.rel = "noopener noreferrer";
      source.append(link);
    }
  }
  const series = corporate ? corporateSeries! : state.monthlyPassengers!;
  const monthlyPoints = series.records.map((point) => ({ ...point, period_label: dateLabel(point.date) }));
  const quarterGroups = new Map<string, QuarterPoint>();
  const quarterMonths = new Map<string, string[]>();
  const incompleteQuarters = new Set<string>();
  monthlyPoints.forEach((point) => {
    const periodId = quarterForDate(point.date);
    if (![point.domestic, point.international, point.total_segment_sum].every(Number.isFinite)) {
      incompleteQuarters.add(periodId);
    }
    quarterMonths.set(periodId, [...(quarterMonths.get(periodId) ?? []), point.date.slice(0, 7)]);
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
    state.passengerPeriod === "quarter" ? [...quarterGroups.values()].filter((quarter) => {
      const months = quarterMonths.get(quarter.period_id)!;
      const first = (Number(quarter.period_id.slice(-1)) - 1) * 3 + 1;
      const expected = [0, 1, 2].map((offset) => `${quarter.period_id.slice(0, 4)}-${String(first + offset).padStart(2, "0")}`);
      return !incompleteQuarters.has(quarter.period_id) && months.length === 3 && new Set(months).size === 3 && expected.every((m) => months.includes(m));
    }) : monthlyPoints;
  renderPassengerCoverage(record.period_id, state.passengerPeriod,
    points.map(point => state.passengerPeriod === "quarter" ? (point as QuarterPoint).period_id : point.date.slice(0,7).replace("-", "M")), corporate ? "Reporte corporativo" : "AFAC",
    monthlyPoints.filter(point => [point.domestic, point.international, point.total_segment_sum].every(Number.isFinite))
      .map(point => point.date.slice(0,7).replace("-", "M")));
  if (!points.length) {
    scheduleMixTooltip(Plotly.react("mix-chart", [], { annotations: [{ text: "No hay un trimestre con sus tres meses completos.", showarrow: false }] }, { displayModeBar: false, responsive: true }),[],()=>null);
    return;
  }
  const narrow = window.matchMedia("(max-width: 736px)").matches;
  const veryNarrow = window.matchMedia("(max-width: 420px)").matches;
  const rangeStart = new Date(`${points[0]!.date}T00:00:00Z`);
  const rangeEnd = new Date(`${points[points.length - 1]!.date}T00:00:00Z`);
  if (record.metrics.passengers.period_start < rangeStart.toISOString().slice(0,10)) rangeStart.setTime(Date.parse(record.metrics.passengers.period_start));
  if (record.metrics.passengers.period_end > rangeEnd.toISOString().slice(0,10)) rangeEnd.setTime(Date.parse(record.metrics.passengers.period_end));
  const paddingDays = state.passengerPeriod === "quarter" ? 45 : 15;
  rangeStart.setUTCDate(rangeStart.getUTCDate() - paddingDays);
  rangeEnd.setUTCDate(rangeEnd.getUTCDate() + paddingDays);
  const traces: Data[] = [
    {
      type: "bar", x: points.map((point) => point.date), y: points.map((point) => point.domestic),
      name: "Nacional", marker: { color: "#003087" },
      hoverinfo: "none",
    },
    {
      type: "bar", x: points.map((point) => point.date), y: points.map((point) => point.international),
      name: "Internacional", marker: { color: "#c99400" },
      hoverinfo: "none",
    },
    {
      type: "scatter", mode: corporate ? "markers" : "lines+markers", x: points.map((point) => point.date),
      y: points.map((point) => corporate && "reported_total" in point ? Number(point.reported_total) : point.total_segment_sum),
      name: corporate ? "Total reportado" : "Total",
      connectgaps: false, line: { color: "#182233", width: 2.5 },
      marker: { color: "#fff", line: { color: "#182233", width: 1.5 }, size: 6 },
      hoverinfo: "none",
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
    yaxis: { rangemode: "tozero", gridcolor: "#e7ebf1", tickformat: ".2s", title: { text: booked ? "Tramos de pasajero reservados" : "Pasajeros" } },
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
  const grain=state.passengerPeriod;
  scheduleMixTooltip(Plotly.react("mix-chart", traces, layout, { displayModeBar: false, responsive: true }),points.map(point=>point.date),(_key,index)=>{
    const date=points[index]!.date;
    const id=grain==="month"?date.slice(0,7).replace("-","M"):quarterForDate(date);
    return seriesMixTooltip(points,id,grain,!!booked);
  });
}
