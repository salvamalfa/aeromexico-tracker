// Mounts the Vuelos view: wires its controls to the shared #period-prev/
// #period-next (added after views/executive's own listeners on the same
// buttons — same DOM/script order as the published page, where
// executive_summary.js runs before src/dashboard/assets/flights.js; see
// web/README.md) and reacts to 'reader-tab-visible' the same way
// src/dashboard/assets/flights.js does: resize its Plotly graphs and
// realign the route detail column once panel-flights becomes visible.

import Plotly from "../../lib/plotly";
import { $ } from "./dom";
import { domesticAvailableForQuarter, loadQuarters, state } from "./state";
import { renderQuarter } from "./quarter";
import { renderMix } from "./mix";
import { renderNetworkPeriod } from "./network";
import { alignRouteDetailToGeo, renderFlowMap } from "./map";

function wireControls(): void {
  $("period-prev")!.addEventListener("click", async () => {
    if (state.periodIndex > 0) {
      state.periodIndex -= 1;
      await renderQuarter();
    }
  });
  $("period-next")!.addEventListener("click", async () => {
    if (state.periodIndex < state.quarters.length - 1) {
      state.periodIndex += 1;
      await renderQuarter();
    }
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
  await renderQuarter();
  const panel = $("panel-flights");
  if (!panel || !panel.hidden) window.requestAnimationFrame(renderFlowMap);
}
