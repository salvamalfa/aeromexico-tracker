// Global quarter selection: KPI cards, delta chips, and the two blocks
// that depend on the selected quarter (mix chart, network). Ported from
// src/dashboard/assets/flights.js::renderQuarter.

import { $, deltaDisplay, metricDisplay, priorPeriod, setDelta } from "./dom.js";
import { monthsInQuarter, state } from "./state.js";
import { renderMix } from "./mix.js";
import { renderNetworkPeriod } from "./network.js";

export async function renderQuarter() {
  const record = state.quarters[state.periodIndex];
  if (record.period_id !== state.domesticMonthsQuarterId) {
    // Cambio de trimestre global: descarta cualquier selección manual de
    // meses y vuelve a seleccionar automáticamente los meses del nuevo
    // trimestre (puede ser un subconjunto si el trimestre está incompleto).
    state.selectedDomesticMonths = new Set(monthsInQuarter(record.period_id));
    state.domesticMonthsQuarterId = record.period_id;
  }
  $("period-display").textContent = record.period_label;
  $("period-prev").disabled = state.periodIndex === 0;
  $("period-next").disabled = state.periodIndex === state.quarters.length - 1;
  const qoq = state.byPeriod.get(priorPeriod(record.period_id));
  const yoy = state.byPeriod.get(priorPeriod(record.period_id, 1));
  for (const key of ["passengers", "asm_miles", "rpm_miles", "load_factor"]) {
    const metric = record.metrics[key];
    $(`flight-kpi-${key}`).textContent = metricDisplay(key, metric.value);
    setDelta(`flight-kpi-${key}-qoq`, deltaDisplay(metric.value, qoq?.metrics[key]?.value, key === "load_factor"));
    setDelta(`flight-kpi-${key}-yoy`, deltaDisplay(metric.value, yoy?.metrics[key]?.value, key === "load_factor"));
  }
  renderMix(record);
  await renderNetworkPeriod(record.period_id);
  $("live-status").textContent = `Trimestre actualizado a ${record.period_label}. La red usa los meses disponibles por fuente del trimestre.`;
}
