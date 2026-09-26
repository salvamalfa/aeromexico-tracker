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
import { domesticAvailableForQuarter, loadQuarters, state } from "./state";
import { renderQuarter } from "./quarter";
import { renderMix } from "./mix";
import { renderNetworkPeriod } from "./network";
import { alignRouteDetailToGeo, renderFlowMap } from "./map";

function syncPeriodIndex(periodId: string): boolean {
  const index = state.quarters.findIndex((quarter) => quarter.period_id === periodId);
  if (index < 0) return false;
  state.periodIndex = index;
  return true;
}

function wireControls(): void {
  subscribe((periodId) => {
    if (syncPeriodIndex(periodId)) void renderQuarter();
  });
  $("network-mode-domestic")!.addEventListener("click", async () => {
    if (domesticAvailableForQuarter(state.quarters[state.periodIndex]!.period_id)) {
      state.networkMode = "domestic";
      await renderNetworkPeriod(state.quarters[state.periodIndex]!.period_id);
    }
  });
  $("network-mode-international")!.addEventListener("click", async () => {
    state.networkMode = "international";
    await renderNetworkPeriod(state.quarters[state.periodIndex]!.period_id);
  });
  $("passenger-period")!.addEventListener("change", (event) => {
    state.passengerPeriod = (event.target as HTMLSelectElement).value as "quarter" | "month";
    renderMix(state.quarters[state.periodIndex]!);
  });
  window.addEventListener("resize", () => window.requestAnimationFrame(alignRouteDetailToGeo));
  window.addEventListener("reader-tab-visible", () => {
    const panel = $("panel-flights");
    if (!panel || panel.hidden) return;
    window.requestAnimationFrame(() => {
      renderFlowMap();
      for (const id of ["route-flow-map", "mix-chart"]) {
        const graph = $(id);
        if (graph?.classList.contains("js-plotly-plot")) Plotly.Plots.resize(graph);
      }
      alignRouteDetailToGeo();
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
  if (!panel || !panel.hidden) window.requestAnimationFrame(renderFlowMap);
}
