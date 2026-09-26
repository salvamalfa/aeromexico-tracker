// Entry point for the full page: shared header + period stepper, the
// reader-tabs shell (Lectura ejecutiva / Economía unitaria / Vuelos), and
// the three views. Fetches web/public/data/v1/ (produced by
// `uv run python -m src.web_export --out web/public/data/v1`). See
// web/README.md and REPO_MAP.md.
//
// Mount order matches the published page's script order (see
// src/analysis_agent/reader_ui.py::refine and stage18.py::consumer_html):
// the tab shell first, then the executive/economy view (its listeners on
// #period-prev/#period-next are attached first), then Vuelos (attached
// second, on the same buttons) — see views/executive/bootstrap.ts and
// views/flights/bootstrap.ts for why that order is part of parity. Vuelos
// (the Plotly scattergeo/choropleth map, ~180 KB of the JS bundle before
// gzip — see web/README.md "Tamaño del bundle") is loaded through a
// dynamic import so it lands in its own chunk instead of the initial one;
// it is still mounted right after the executive view on every page load
// (never deferred to the tab click), so the attachment order above and
// every rendered value stay exactly as before — only which <script> chunk
// the code streams from changes.
import { mountTabs } from "./views/shell/tabs";
import { mountExecutive } from "./views/executive/bootstrap";
import { $ } from "./views/flights/dom";

export async function mount(dataRoot = "data/v1"): Promise<void> {
  mountTabs();
  await mountExecutive(dataRoot);
  const { mountFlights } = await import("./views/flights/bootstrap");
  await mountFlights(dataRoot);
}

if (typeof window !== "undefined" && !window.__pageNoAutoMount) {
  mount().catch((error: unknown) => {
    console.error(error);
    const status = $("live-status");
    if (status) status.textContent = `No se pudo cargar el panel: ${error instanceof Error ? error.message : String(error)}`;
  });
}
