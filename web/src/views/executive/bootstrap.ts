// Mounts the reading + economy tabs together, since both render off the
// same executive.json payload — port of the bottom of
// src/dashboard/assets/executive_summary.js (render(), movePeriod(),
// the period-prev/next listeners and the unit-range/resize listeners).
//
// Order matters for parity: this attaches its #period-prev/#period-next
// listeners before views/flights/bootstrap.ts does, exactly like the
// published page loads executive_summary.js before
// src/dashboard/assets/flights.js — see web/README.md.

import { $ } from "../flights/dom";
import { currentView, loadExecutive, state } from "./state";
import { renderNarrative } from "./narrative";
import { updateKpis } from "../economy/kpis";
import { renderLoadMonetization, renderUnitEconomics, renderVolumeMonetization } from "../economy/charts";
import { renderQuarterTable } from "../economy/table";

async function render(periodId: string): Promise<void> {
  const view = state.views[periodId];
  if (!view) return;
  updateKpis(view);
  await renderNarrative(view);
  const range = $("unit-range") as HTMLSelectElement;
  const inRange = range.value === "all" || state.records.slice(-Number(range.value)).some((r) => r.period_id === periodId);
  if (!inRange) {
    range.value = "all";
    renderUnitEconomics();
  }
  renderVolumeMonetization();
  renderLoadMonetization(periodId);
  $("period-display")!.textContent = view.period_label;
  ($("period-prev") as HTMLButtonElement).disabled = state.periodIndex === 0;
  ($("period-next") as HTMLButtonElement).disabled = state.periodIndex === state.records.length - 1;
  $("live-status")!.textContent = `Vista actualizada a ${view.period_label}.`;
}

function movePeriod(offset: number): Promise<void> | undefined {
  const nextIndex = state.periodIndex + offset;
  if (nextIndex < 0 || nextIndex >= state.records.length) return undefined;
  state.periodIndex = nextIndex;
  const view = currentView();
  return view ? render(view.period_id) : undefined;
}

export async function mountExecutive(dataRoot = "data/v1"): Promise<void> {
  await loadExecutive(dataRoot);
  $("period-prev")!.addEventListener("click", () => movePeriod(-1));
  $("period-next")!.addEventListener("click", () => movePeriod(1));
  $("unit-range")!.addEventListener("change", renderUnitEconomics);
  window.addEventListener("resize", renderUnitEconomics);
  renderQuarterTable();
  renderUnitEconomics();
  const view = currentView();
  if (view) await render(view.period_id);
}
