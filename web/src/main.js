// Entry point for the standalone Vuelos view. Fetches web/public/data/v1/
// (produced by `uv run python -m src.web_export --out web/public/data/v1`),
// wires the same controls the integrated dashboard exposes, and renders.
// See web/README.md and REPO_MAP.md.

import { $ } from "./views/flights/dom.js";
import { domesticAvailableForQuarter, loadQuarters, state } from "./views/flights/state.js";
import { renderQuarter } from "./views/flights/quarter.js";
import { renderMix } from "./views/flights/mix.js";
import { renderNetworkPeriod } from "./views/flights/network.js";
import { alignRouteDetailToGeo, renderFlowMap } from "./views/flights/map.js";

function wireControls() {
  $("period-prev").addEventListener("click", async () => {
    if (state.periodIndex > 0) { state.periodIndex -= 1; await renderQuarter(); }
  });
  $("period-next").addEventListener("click", async () => {
    if (state.periodIndex < state.quarters.length - 1) { state.periodIndex += 1; await renderQuarter(); }
  });
  $("network-mode-domestic").addEventListener("click", async () => {
    if (domesticAvailableForQuarter(state.quarters[state.periodIndex].period_id)) {
      state.networkMode = "domestic";
      await renderNetworkPeriod(state.quarters[state.periodIndex].period_id);
    }
  });
  $("network-mode-international").addEventListener("click", async () => {
    state.networkMode = "international";
    await renderNetworkPeriod(state.quarters[state.periodIndex].period_id);
  });
  $("passenger-period").addEventListener("change", (event) => {
    state.passengerPeriod = event.target.value;
    renderMix(state.quarters[state.periodIndex]);
  });
  window.addEventListener("resize", () => window.requestAnimationFrame(alignRouteDetailToGeo));
}

export async function mount(dataRoot = "public/data/v1") {
  await loadQuarters(dataRoot);
  wireControls();
  await renderQuarter();
  window.requestAnimationFrame(renderFlowMap);
}

if (typeof window !== "undefined" && !window.__flightsViewNoAutoMount) {
  mount().catch((error) => {
    console.error(error);
    const status = $("live-status");
    if (status) status.textContent = `No se pudo cargar Vuelos: ${error.message}`;
  });
}
