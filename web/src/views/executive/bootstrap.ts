// Mounts the reading + economy tabs together, since both render off the
// same executive.json payload — port of the bottom of
// src/dashboard/assets/executive_summary.js (render(), movePeriod(),
// the period-prev/next listeners and the unit-range/resize listeners).
//
// The executive view always mounts first (see src/main.ts), so it is the
// one that wires the shared #period-prev/#period-next listeners
// (../../state/period.ts::wireStepper) — views/flights/bootstrap.ts
// (mounted lazily, only once its tab is first opened) subscribes to the
// same store instead of attaching its own listeners; see web/README.md
// "Estado de trimestre compartido".

import { $ } from "../flights/dom";
import { currentIndex, currentPeriodId, periodCount, subscribe, wireStepper } from "../../state/period";
import { loadExecutive, state } from "./state";
import { renderNarrative } from "./narrative";
import { updateKpis } from "../economy/kpis";
import { renderLoadMonetization, renderUnitEconomics, renderVolumeMonetization } from "../economy/charts";
import { renderQuarterTable } from "../economy/table";

async function render(periodId: string): Promise<void> {
  const view = state.views[periodId];
  if (!view) return;
  state.periodIndex = state.records.findIndex((record) => record.period_id === periodId);
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
  ($("period-prev") as HTMLButtonElement).disabled = currentIndex() === 0;
  ($("period-next") as HTMLButtonElement).disabled = currentIndex() === periodCount() - 1;
  $("live-status")!.textContent = `Vista actualizada a ${view.period_label}.`;
}

export async function mountExecutive(dataRoot = "data/v1"): Promise<void> {
  await loadExecutive(dataRoot);
  wireStepper();
  subscribe((periodId) => void render(periodId));
  $("unit-range")!.addEventListener("change", renderUnitEconomics);
  window.addEventListener("resize", renderUnitEconomics);
  renderQuarterTable();
  renderUnitEconomics();
  const periodId = currentPeriodId();
  if (periodId) await render(periodId);
}
