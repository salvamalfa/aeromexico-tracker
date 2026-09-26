// Global quarter selection: KPI cards, delta chips, and the two blocks
// that depend on the selected quarter (mix chart, network). Ported from
// src/dashboard/assets/flights.js::renderQuarter.

import { $, deltaDisplay, metricDisplay, priorPeriod, setDelta } from "./dom";
import { currentIndex, periodCount } from "../../state/period";
import { monthsInQuarter, state } from "./state";
import { renderMix } from "./mix";
import { renderNetworkPeriod } from "./network";

const KPI_KEYS = ["passengers", "asm_miles", "rpm_miles", "load_factor"] as const;

export async function renderQuarter(): Promise<void> {
  const record = state.quarters[state.periodIndex]!;
  if (record.period_id !== state.domesticMonthsQuarterId) {
    // Cambio de trimestre global: descarta cualquier selección manual de
    // meses y vuelve a seleccionar automáticamente los meses del nuevo
    // trimestre (puede ser un subconjunto si el trimestre está incompleto).
    state.selectedDomesticMonths = new Set(monthsInQuarter(record.period_id));
    state.domesticMonthsQuarterId = record.period_id;
  }
  $("period-display")!.textContent = record.period_label;
  ($("period-prev") as HTMLButtonElement).disabled = currentIndex() === 0;
  ($("period-next") as HTMLButtonElement).disabled = currentIndex() === periodCount() - 1;
  const qoq = state.byPeriod.get(priorPeriod(record.period_id));
  const yoy = state.byPeriod.get(priorPeriod(record.period_id, 1));
  for (const key of KPI_KEYS) {
    const metric = record.metrics[key] as { value: number | null };
    $(`flight-kpi-${key}`)!.textContent = metricDisplay(key, metric.value);
    setDelta(
      `flight-kpi-${key}-qoq`,
      deltaDisplay(metric.value, (qoq?.metrics[key] as { value: number | null } | undefined)?.value, key === "load_factor")
    );
    setDelta(
      `flight-kpi-${key}-yoy`,
      deltaDisplay(metric.value, (yoy?.metrics[key] as { value: number | null } | undefined)?.value, key === "load_factor")
    );
  }
  renderMix(record);
  await renderNetworkPeriod(record.period_id);
  $("live-status")!.textContent =
    `Trimestre actualizado a ${record.period_label}. La red usa los meses disponibles por fuente del trimestre.`;
}
