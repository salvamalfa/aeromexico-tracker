// Mutable state shared by the reading and economy tabs: both render off
// the same web/public/data/v1/executive.json payload (records + views by
// period_id), the split of build_executive_payload() — see
// src/web_export/executive.py — exactly like the published page's single
// executive_summary.js drives both panels from one `views` object.

import { initPeriods } from "../../state/period";
import type { ExecutiveDocument, ExecutiveMetadata, ExecutiveRecord, ExecutiveView } from "../../types/domain";

// periodIndex mirrors the shared quarter store (../../state/period.ts) —
// views/executive/bootstrap.ts keeps it in sync on every period change;
// see that store for why the index itself is no longer this module's own.
export interface ExecutiveState {
  dataRoot: string;
  metadata: ExecutiveMetadata | null;
  records: ExecutiveRecord[];
  views: Record<string, ExecutiveView>;
  periodIndex: number;
}

export const state: ExecutiveState = {
  dataRoot: "data/v1",
  metadata: null,
  records: [],
  views: {},
  periodIndex: 0,
};

async function fetchJson<T>(path: string): Promise<T> {
  const response = await fetch(path);
  if (!response.ok) throw new Error(`No se pudo cargar ${path} (HTTP ${response.status})`);
  return response.json() as Promise<T>;
}

export async function loadExecutive(dataRoot?: string): Promise<ExecutiveDocument> {
  if (dataRoot) state.dataRoot = dataRoot;
  const payload = await fetchJson<ExecutiveDocument>(`${state.dataRoot}/executive.json`);
  state.metadata = payload.metadata;
  state.records = payload.records;
  state.views = payload.views;
  state.periodIndex = Math.max(
    0,
    state.records.findIndex((record) => record.period_id === state.metadata?.default_period)
  );
  initPeriods(state.records.map((record) => record.period_id), state.metadata?.default_period);
  return payload;
}

export function currentPeriodId(): string | undefined {
  return state.records[state.periodIndex]?.period_id;
}

export function currentView(): ExecutiveView | undefined {
  const periodId = currentPeriodId();
  return periodId ? state.views[periodId] : undefined;
}
