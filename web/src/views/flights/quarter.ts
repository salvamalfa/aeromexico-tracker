// Global quarter selection: KPI cards, delta chips, and the two blocks
// that depend on the selected quarter (mix chart, network). Ported from
// src/dashboard/assets/flights.js::renderQuarter.

import { $, deltaDisplay, metricDisplay, priorPeriod, setDelta } from "./dom";
import { currentIndex, currentPeriodId, periodCount } from "../../state/period";
import { monthsInQuarter, state } from "./state";
import { renderMix } from "./mix";
import { renderOfficialMap } from "./official-map";
import { renderFlightKpiSources } from "./kpi-sources";
import { renderEntityKpis } from "./carriers";
import { selection } from "../shell/carriers";
import { selectedFlightQuarter } from "./selected-period";
import { state as executiveState } from "../executive/state";

const KPI_KEYS = ["passengers", "asm_miles", "rpm_miles", "load_factor"] as const;
let quarterRequest = 0;

export async function renderQuarter(): Promise<void> {
  const request = ++quarterRequest;
  const record = selectedFlightQuarter();
  if (record.period_id !== state.domesticMonthsQuarterId) {
    // Cambio de trimestre global: descarta cualquier selección manual de
    // meses y vuelve a seleccionar automáticamente los meses del nuevo
    // trimestre (puede ser un subconjunto si el trimestre está incompleto).
    state.selectedDomesticMonths = new Set(monthsInQuarter(record.period_id));
    state.domesticMonthsQuarterId = record.period_id;
  }
  const selected = currentPeriodId();
  const available = !selected || selected === record.period_id;
  if (available) $("period-display")!.textContent = record.period_label;
  const kpiEntity = selection("flight-kpis")[0] ?? "AEROMEXICO";
  ($("period-prev") as HTMLButtonElement).disabled = currentIndex() === 0;
  ($("period-next") as HTMLButtonElement).disabled = currentIndex() === periodCount() - 1;
  const qoq = state.byPeriod.get(priorPeriod(record.period_id));
  const yoy = state.byPeriod.get(priorPeriod(record.period_id, 1));
  if (executiveState.entities) renderEntityKpis(kpiEntity, record.period_id);
  else for (const key of KPI_KEYS) {
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
  if (!executiveState.entities) renderFlightKpiSources(kpiEntity, record.period_id, record);
  renderMix(record);
  await renderOfficialMap(record.period_id);
  if (request !== quarterRequest || (currentPeriodId() && currentPeriodId() !== record.period_id)) return;
  $("live-status")!.textContent = `Selección: ${record.period_label}. Cada bloque de Vuelos declara su periodo y cobertura; un mes disponible no completa un trimestre.`;
}
