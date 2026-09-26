// Mounts the reading + economy tabs together, since both render off the
// same executive.json payload — port of the bottom of
// src/dashboard/assets/executive_summary.js (render(), movePeriod(),
// the period-prev/next listeners and the unit-range/resize listeners).
//
// Order matters for parity: this attaches its #period-prev/#period-next
// listeners before views/flights/bootstrap.js does, exactly like the
// published page loads executive_summary.js before
// src/dashboard/assets/flights.js — see web/README.md.

import { $ } from "../flights/dom.js";
import { currentView, loadExecutive, state } from "./state.js";
import { renderNarrative } from "./narrative.js";
import { updateKpis } from "../economy/kpis.js";
import { renderLoadMonetization, renderUnitEconomics, renderVolumeMonetization } from "../economy/charts.js";
import { renderQuarterTable } from "../economy/table.js";

async function render(periodId) {
  const view = state.views[periodId];
  if (!view) return;
  updateKpis(view);
  await renderNarrative(view);
  const range = $("unit-range");
  const inRange = range.value === "all" || state.records.slice(-Number(range.value)).some((r) => r.period_id === periodId);
  if (!inRange) { range.value = "all"; renderUnitEconomics(); }
  renderVolumeMonetization();
  renderLoadMonetization(periodId);
  $("period-display").textContent = view.period_label;
  $("period-prev").disabled = state.periodIndex === 0;
  $("period-next").disabled = state.periodIndex === state.records.length - 1;
  $("live-status").textContent = `Vista actualizada a ${view.period_label}.`;
}

function movePeriod(offset) {
  const nextIndex = state.periodIndex + offset;
  if (nextIndex < 0 || nextIndex >= state.records.length) return;
  state.periodIndex = nextIndex;
  return render(currentView().period_id);
}

export async function mountExecutive(dataRoot = "public/data/v1") {
  await loadExecutive(dataRoot);
  $("period-prev").addEventListener("click", () => movePeriod(-1));
  $("period-next").addEventListener("click", () => movePeriod(1));
  $("unit-range").addEventListener("change", renderUnitEconomics);
  window.addEventListener("resize", renderUnitEconomics);
  renderQuarterTable();
  renderUnitEconomics();
  await render(currentView().period_id);
}
