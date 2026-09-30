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
import { renderNetworkPeriod, renderRouteMode } from "./network";
import { alignRouteDetailToGeo, canvasSize, mapFittedCanvasSize, renderFlowMap } from "./map";
import { mountPicker } from "../shell/carriers";
import { setMapEntity } from "./state";
import { state as executiveState } from "../executive/state";

function syncPeriodIndex(periodId: string): boolean {
  const index = state.quarters.findIndex((quarter) => quarter.period_id === periodId);
  if (index < 0) return false;
  state.periodIndex = index;
  return true;
}

// Dashboard v2: KPI cards (one airline) and the segment mix (one or more).
// Only when executive.json carries the entity block; otherwise v1 as-is.
function mountFlightPickers(): void {
  if (!executiveState.entities) return;
  const kpiHost = $("pick-flight-kpis") as HTMLElement | null;
  if (kpiHost) {
    mountPicker(kpiHost, { card: "flight-kpis", multi: false, defaults: ["INDUSTRY"] }, () => void renderQuarter());
  }
  // Route map (fase 3): one entity at a time, Industria by default.
  const mapHost = $("pick-map") as HTMLElement | null;
  if (mapHost && state.availablePeriods.entities) {
    const [initial] = mountPicker(mapHost, { card: "map", multi: false, defaults: ["INDUSTRY"] }, async ([key]) => {
      if (!key || !setMapEntity(key)) return;
      state.pinnedAirport = null;
      state.selectedMarket = null;
      await renderNetworkPeriod(state.quarters[state.periodIndex]!.period_id);
      renderFlowMap();
    });
    if (initial) setMapEntity(initial);
  }
  const mixHost = $("pick-mix") as HTMLElement | null;
  if (mixHost) {
    mountPicker(mixHost, { card: "mix", multi: true, defaults: ["INDUSTRY"] }, () => renderMix(state.quarters[state.periodIndex]!));
  }
}

function wireControls(): void {
  mountFlightPickers();
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
  for (const [id, view] of [["map-routes-featured", "volume"], ["map-routes-change", "change"], ["map-routes-all", "all"]] as const) {
    $(id)!.addEventListener("click", () => {
      state.routeView = view;
      state.pinnedAirport = null;
      state.selectedMarket = null;
      renderRouteMode();
      renderFlowMap();
    });
  }
  window.addEventListener("flight-route-overview", () => renderFlowMap());
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
      if (state.network && panel && !panel.hidden && width && canvasSize() !== mapFittedCanvasSize()) {
        renderFlowMap();
      }
      alignRouteDetailToGeo();
    });
  });
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
