// Entry point for the full page: shared header + period stepper, the
// reader-tabs shell (Lectura ejecutiva / Economía unitaria / Vuelos), and
// the three views. Fetches web/public/data/v1/ (produced by
// `uv run python -m src.web_export --out web/public/data/v1`). See
// web/README.md and REPO_MAP.md.
//
// The executive/economy view always mounts eagerly: it wires the shared
// #period-prev/#period-next listeners (state/period.ts) and fetches
// executive.json. Vuelos (the Plotly scattergeo/choropleth map plus its
// own data — quarters.json, world geometry, network files, see
// web/README.md "Carga inicial de Vuelos") mounts lazily instead, the
// first time panel-flights becomes visible — via the same
// 'reader-tab-visible' CustomEvent shell/tabs.ts dispatches on every tab
// switch (also used by views/flights/bootstrap.ts itself to resize its
// Plotly graphs) — rather than unconditionally on every page load. It is
// still loaded through a dynamic import so it lands in its own chunk.
// Because both views subscribe to the same period store instead of each
// keeping their own listeners on #period-prev/#period-next, switching
// quarters before Vuelos is ever opened and then opening it shows the
// already-selected quarter, exactly like the published page (which
// mounts both eagerly) — see state/period.ts and
// tests/test_web_page_parity.py.
import { mountTabs } from "./views/shell/tabs";
import { mountExecutive } from "./views/executive/bootstrap";
import { $ } from "./views/flights/dom";

let flightsMount: Promise<void> | null = null;
function ensureDemandMounted(dataRoot: string): Promise<void> {
  return import("./views/market/demand").then(({ mountDemand }) => mountDemand(dataRoot));
}

function ensureNewsMounted(dataRoot: string): Promise<void> {
  // mountNews guards concurrent mounts and permits retry after a fetch error.
  return import("./views/news/bootstrap").then(({ mountNews }) => mountNews(dataRoot));
}

function ensureFlightsMounted(dataRoot: string): Promise<void> {
  if (!flightsMount) {
    flightsMount = import("./views/flights/bootstrap").then(({ mountFlights }) => mountFlights(dataRoot));
  }
  return flightsMount;
}

export async function mount(dataRoot = "data/v1"): Promise<void> {
  mountTabs();
  await mountExecutive(dataRoot);
  if (import.meta.env.VITE_CHAT_ENABLED === "true") {
    const { mountChat } = await import("./views/chat/bootstrap");
    mountChat();
  }
  window.addEventListener("reader-tab-visible", (event) => {
    const panelId = (event as CustomEvent<{ panelId: string }>).detail?.panelId;
    if (panelId === "panel-market") void ensureDemandMounted(dataRoot);
    if (panelId === "panel-news") void ensureNewsMounted(dataRoot);
    if (panelId === "panel-flights") void ensureFlightsMounted(dataRoot);
  });
  // Defensive only: today's markup always starts on the reading tab (see
  // index.html), so panel-flights starts hidden and this never fires on
  // load — but if that default ever changed, Vuelos must still mount.
  const newsPanel = $("panel-news");
  if (newsPanel && !newsPanel.hidden) await ensureNewsMounted(dataRoot);
  const marketPanel = $("panel-market");
  if (marketPanel && !marketPanel.hidden) await ensureDemandMounted(dataRoot);
  const panel = $("panel-flights");
  if (panel && !panel.hidden) await ensureFlightsMounted(dataRoot);
}

if (typeof window !== "undefined" && !window.__pageNoAutoMount) {
  mount().catch((error: unknown) => {
    console.error(error);
    const status = $("live-status");
    if (status) status.textContent = `No se pudo cargar el panel: ${error instanceof Error ? error.message : String(error)}`;
  });
}
