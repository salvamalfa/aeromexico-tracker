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
// second, on the same buttons) — see views/executive/bootstrap.js and
// views/flights/bootstrap.js for why that order is part of parity.

import { mountTabs } from "./views/shell/tabs.js";
import { mountExecutive } from "./views/executive/bootstrap.js";
import { mountFlights } from "./views/flights/bootstrap.js";
import { $ } from "./views/flights/dom.js";

export async function mount(dataRoot = "public/data/v1") {
  mountTabs();
  await mountExecutive(dataRoot);
  await mountFlights(dataRoot);
}

if (typeof window !== "undefined" && !window.__pageNoAutoMount) {
  mount().catch((error) => {
    console.error(error);
    const status = $("live-status");
    if (status) status.textContent = `No se pudo cargar el panel: ${error.message}`;
  });
}
