// Mounts the Vuelos view, lazily (see src/main.ts — this module is only
// ever import()ed once the Vuelos tab is first opened, so its data
// fetches — quarters.json, world geometry, network files — never load
// for a reader who stays on the reading/economy tabs, see web/README.md
// "Carga inicial de Vuelos"). Wires its own controls, and subscribes to
// the shared quarter store (../../state/period.ts) instead of attaching
// its own #period-prev/#period-next listeners — currentPeriodId() picks
// up whatever quarter was already selected on the reading tab before
// Vuelos ever mounted. Reacts to 'reader-tab-visible' the same way
// src/dashboard/assets/flights.js does: resize its Plotly graphs and
// realign the route detail column once panel-flights becomes visible.

import Plotly from "../../lib/plotly";
import { $ } from "./dom";
import { currentPeriodId, subscribe } from "../../state/period";
import { loadQuarters, state } from "./state";
import { renderQuarter } from "./quarter";
import { renderMix } from "./mix";
import { mountOfficialMap, redrawOfficialMap } from "./official-map";
import { mountPicker } from "../shell/carriers";
import { state as executiveState } from "../executive/state";
import { selectedFlightQuarter } from "./selected-period";

function syncPeriodIndex(periodId: string): boolean {
  const index = state.quarters.findIndex((quarter) => quarter.period_id === periodId);
  state.periodIndex = index;
  return index >= 0;
}

// Dashboard v2: KPI cards (one airline) and the segment mix (one or more).
// Only when executive.json carries the entity block; otherwise v1 as-is.
function mountFlightPickers(): void {
  if (!executiveState.entities) return;
  const kpiHost = $("pick-flight-kpis") as HTMLElement | null;
  if (kpiHost) {
    mountPicker(kpiHost, { card: "flight-kpis", multi: false, defaults: ["INDUSTRY"] }, () => void renderQuarter());
  }
  const mixHost = $("pick-mix") as HTMLElement | null;
  if (mixHost) {
    mountPicker(mixHost, { card: "mix", multi: true, defaults: ["INDUSTRY"] }, () => renderMix(selectedFlightQuarter()));
  }
}

function wireControls(): void {
  mountFlightPickers();
  mountOfficialMap();
  subscribe((periodId) => {
    syncPeriodIndex(periodId);
    state.mapPeriodId = null;
    void renderQuarter();
  });
  $("passenger-basis")?.addEventListener("change", (event) => {
    state.passengerBasis = (event.target as HTMLSelectElement).value === "corporate" ? "corporate" : "afac";
    if (state.passengerBasis === "corporate") state.passengerPeriod = "month";
    const period = $("passenger-period") as HTMLSelectElement;
    period.value = state.passengerPeriod;
    renderMix(selectedFlightQuarter());
  });
  $("passenger-period")!.addEventListener("change", (event) => {
    state.passengerPeriod = (event.target as HTMLSelectElement).value as "quarter" | "month";
    renderMix(selectedFlightQuarter());
  });
  // El recorte del mapa (fitViewToCanvas) depende del aspecto del lienzo:
  // si cambia el ancho o el alto hay que recalcularlo, no solo realinear el
  // detalle (el alto cambia solo, p. ej., en el corte de 420px con el ancho
  // fijo en su mínimo).
  let resizeQueued = false;
  window.addEventListener("resize", () => {
    if (resizeQueued) return;
    resizeQueued = true;
    window.requestAnimationFrame(() => {
      resizeQueued = false;
      const panel = $("panel-flights");
      const width = $("route-flow-map")?.clientWidth ?? 0;
      if (panel && !panel.hidden && width) void redrawOfficialMap();
    });
  });
  window.addEventListener("reader-tab-visible", () => {
    const panel = $("panel-flights");
    if (!panel || panel.hidden) return;
    window.requestAnimationFrame(() => {
      void redrawOfficialMap();
      for (const id of ["route-flow-map", "mix-chart"]) {
        const graph = $(id);
        if (graph?.classList.contains("js-plotly-plot")) Plotly.Plots.resize(graph);
      }
    });
  });
}

export async function mountFlights(dataRoot = "data/v1"): Promise<void> {
  await loadQuarters(dataRoot);
  wireControls();
  const periodId = currentPeriodId();
  if (periodId) syncPeriodIndex(periodId);
  await renderQuarter();
  const panel = $("panel-flights");
  if (!panel || !panel.hidden) window.requestAnimationFrame(() => void redrawOfficialMap());
}
