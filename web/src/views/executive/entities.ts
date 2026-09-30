// Per-entity access to executive.json (Dashboard v2): the `entities` block
// built by src/dashboard/executive_summary.py::build_entity_payloads() —
// Industria (ASK-weighted, constant three-carrier panel) plus Aeroméxico,
// Volaris and Viva — and market.json (src/dashboard/market.py).
//
// Aeroméxico keeps reading the top-level records/views the page has always
// used, so selecting it renders exactly the v1 page; its entity block is
// only consulted for the "vs. industria" comparisons that v1 did not have.

import type { EntityBlock, EntityRecord, ExecutiveRecord, ExecutiveView, MarketDocument } from "../../types/domain";
import { ENTITY_LABELS, type EntityKey } from "../shell/carriers";
import { state } from "./state";

export const entityState: { market: MarketDocument | null } = { market: null };

function block(key: EntityKey): EntityBlock | undefined {
  return state.entities?.[key];
}

export function entityRecords(key: EntityKey): ExecutiveRecord[] {
  if (key === "AEROMEXICO") return state.records;
  // Entity records name the ratio `load_factor` (it may be RPM/ASM when the
  // carrier does not report one); the v1 chart code reads
  // `load_factor_reported`, so expose the same value under both names.
  return (block(key)?.records ?? []).map((record: EntityRecord) => ({
    ...record,
    load_factor_reported: record.load_factor,
  }));
}

export function entityRecord(key: EntityKey, periodId: string): EntityRecord | undefined {
  return block(key)?.records.find((record) => record.period_id === periodId);
}

export function entityView(key: EntityKey, periodId: string): ExecutiveView | undefined {
  if (key === "AEROMEXICO") return state.views[periodId];
  return block(key)?.views[periodId];
}

// The Aeroméxico entity view carries vs_industry; the v1 top-level view does not.
export function industryComparisonView(key: EntityKey, periodId: string): ExecutiveView | undefined {
  if (key === "INDUSTRY") return undefined;
  return block(key)?.views[periodId];
}

export function entityLabel(key: EntityKey): string {
  return state.entityList?.find((item) => item.key === key)?.label ?? ENTITY_LABELS[key];
}

export function entityNote(key: EntityKey): string {
  return block(key)?.note ?? "";
}

export async function loadMarket(dataRoot: string): Promise<MarketDocument | null> {
  const response = await fetch(`${dataRoot}/market.json`);
  entityState.market = response.ok ? ((await response.json()) as MarketDocument) : null;
  return entityState.market;
}
