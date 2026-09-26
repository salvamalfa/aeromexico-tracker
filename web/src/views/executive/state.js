// Mutable state shared by the reading and economy tabs: both render off
// the same web/public/data/v1/executive.json payload (records + views by
// period_id), the split of build_executive_payload() — see
// src/web_export/executive.py — exactly like the published page's single
// executive_summary.js drives both panels from one `views` object.

export const state = {
  dataRoot: "public/data/v1",
  metadata: null,
  records: [],
  views: {},
  periodIndex: 0,
};

async function fetchJson(path) {
  const response = await fetch(path);
  if (!response.ok) throw new Error(`No se pudo cargar ${path} (HTTP ${response.status})`);
  return response.json();
}

export async function loadExecutive(dataRoot) {
  if (dataRoot) state.dataRoot = dataRoot;
  const payload = await fetchJson(`${state.dataRoot}/executive.json`);
  state.metadata = payload.metadata;
  state.records = payload.records;
  state.views = payload.views;
  state.periodIndex = Math.max(
    0,
    state.records.findIndex((record) => record.period_id === state.metadata.default_period)
  );
  return payload;
}

export function currentPeriodId() {
  return state.records[state.periodIndex]?.period_id;
}

export function currentView() {
  return state.views[currentPeriodId()];
}
