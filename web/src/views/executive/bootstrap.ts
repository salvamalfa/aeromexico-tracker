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
//
// Dashboard v2: each card carries its own airline selector
// (../shell/carriers.ts). Aeroméxico renders exactly the v1 content.

import { $ } from "../flights/dom";
import { currentIndex, currentPeriodId, periodCount, subscribe, wireStepper } from "../../state/period";
import { loadExecutive, state } from "./state";
import { renderNarrative } from "./narrative";
import { entityLabel, entityState, loadMarket } from "./entities";
import { renderMarket, setMarketEntities, mountMarketControls } from "./market";
import { updateKpis } from "../economy/kpis";
import {
  renderLoadMonetization,
  renderUnitEconomics,
  renderVolumeMonetization,
  setLoadEntities,
  setUnitEntities,
  setVolumeEntities,
} from "../economy/charts";
import { renderQuarterTable } from "../economy/table";
import { mountPicker, selection, type EntityKey } from "../shell/carriers";
import { loadReadingPeriods, selectedReading, selectReadingPeriod } from "./reading-periods";

const ECONOMY_SOURCE: Record<EntityKey, string> = {
  AEROMEXICO: "Fuente: v_aeromexico_quarterly",
  VOLARIS: "Fuente: reportes trimestrales de Volaris (6-K, SEC)",
  VIVA_AEROBUS: "Fuente: reportes trimestrales de Viva Aerobus",
  INDUSTRY: "Fuente: reportes trimestrales de Aeroméxico, Volaris y Viva · Industria ponderada por ASK",
};

function renderKpisAndTable(periodId: string): void {
  const entity = selection("kpis")[0] ?? (state.entities ? "INDUSTRY" : "AEROMEXICO");
  updateKpis(entity, periodId);
  renderQuarterTable(entity);
  const source = $("economy-source-inline");
  if (source) source.textContent = ECONOMY_SOURCE[entity];
}

let readingCatalogState: "loading" | "ready" | "unavailable" = "loading";

async function renderReading(): Promise<void> {
  const entity = selection("reading")[0] ?? "AEROMEXICO";
  if (readingCatalogState !== "ready") {
    const selector = $("reading-period") as HTMLSelectElement | null;
    if (selector) { selector.replaceChildren(); selector.disabled = true; }
    const copy = $("narrative-copy");
    if (copy) {
      copy.textContent = readingCatalogState === "loading" ? "Cargando lectura…" : "No se pudo verificar el catálogo de lecturas publicadas.";
      delete copy.dataset.period;
      copy.dataset.entity = entity;
    }
    const period = $("narrative-period");
    if (period) period.textContent = "—";
    const name = $("narrative-entity");
    if (name) name.textContent = entityLabel(entity);
    return;
  }
  const view = selectedReading(entity);
  if (view) await renderNarrative(view, entity, entityLabel(entity));
}

async function render(periodId: string): Promise<void> {
  const view = state.views[periodId];
  if (!view) return;
  state.periodIndex = state.records.findIndex((record) => record.period_id === periodId);
  renderKpisAndTable(periodId);
  if (periodId !== currentPeriodId()) return;
  renderMarket(periodId);
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

function mountPickers(): void {
  const host = (id: string) => $(id) as HTMLElement | null;
  const periodId = () => currentPeriodId() ?? "";
  const reading = host("pick-reading");
  if (reading) mountPicker(reading, { card: "reading", multi: false, defaults: ["AEROMEXICO"] }, () => void renderReading());
  const market = host("pick-market");
  if (market) {
    setMarketEntities(
      mountPicker(market, { card: "market", multi: true, defaults: ["AEROMEXICO", "VOLARIS", "VIVA_AEROBUS"] }, (keys) => {
        setMarketEntities(keys);
        renderMarket(undefined);
      })
    );
  }
  const kpis = host("pick-kpis");
  if (kpis) mountPicker(kpis, { card: "kpis", multi: false, defaults: ["INDUSTRY"] }, () => renderKpisAndTable(periodId()));
  const unit = host("pick-unit");
  if (unit) {
    setUnitEntities(
      mountPicker(unit, { card: "unit", multi: true, defaults: ["INDUSTRY"] }, (keys) => {
        setUnitEntities(keys);
        renderUnitEconomics();
      })
    );
  }
  const volume = host("pick-volume");
  if (volume) {
    setVolumeEntities(
      mountPicker(volume, { card: "volume", multi: true, defaults: ["INDUSTRY"] }, (keys) => {
        setVolumeEntities(keys);
        renderVolumeMonetization();
      })
    );
  }
  const load = host("pick-load");
  if (load) {
    setLoadEntities(
      mountPicker(load, { card: "load", multi: true, defaults: ["INDUSTRY"] }, (keys) => {
        setLoadEntities(keys);
        renderLoadMonetization(periodId());
      })
    );
  }
}

export async function mountExecutive(dataRoot = "data/v1"): Promise<void> {
  await loadExecutive(dataRoot);
  readingCatalogState = "loading";
  await loadMarket(state.dataRoot);
  const note = $("industry-note");
  if (note && entityState.market) note.textContent = entityState.market.metadata.industry_note;
  // Without the v2 entity block (an older export) every picker would have
  // nothing to show: keep the v1 page as it was.
  if (state.entities) mountPickers();
  $("reading-period")?.addEventListener("change", (event) => {
    selectReadingPeriod((event.target as HTMLSelectElement).value);
    void renderReading();
  });
  void renderReading();
  wireStepper();
  subscribe((periodId) => void render(periodId));
  $("unit-range")!.addEventListener("change", renderUnitEconomics);
  $("unit-metric")?.addEventListener("change", renderUnitEconomics);
  mountMarketControls();
  window.addEventListener("resize", renderUnitEconomics);
  renderUnitEconomics();
  const periodId = currentPeriodId();
  if (periodId) await render(periodId);
  // Financial controls and charts are ready before either reading request.
  // A slow catalog or analysis must not hold up other views or their startup.
  void loadReadingPeriods(state.dataRoot).then(async () => {
    readingCatalogState = "ready";
    await renderReading();
  }).catch(() => {
    readingCatalogState = "unavailable";
    void renderReading();
  });
}
