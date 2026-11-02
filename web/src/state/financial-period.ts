import type { ExecutiveDocument } from "../types/domain";

// The published financial record and its view must both exist. An analysis
// thesis, route map or common airline cut does not determine this default.
export function financialPeriods(payload: ExecutiveDocument): string[] {
  const blocks = [{ records: payload.records, views: payload.views }, ...Object.values(payload.entities ?? {}).map(block => ({
    records: block.records.map(row => ({ ...row, load_factor_reported: row.load_factor })), views: block.views,
  }))];
  return [...new Set(blocks.flatMap(block => block.records.filter(record => /^\d{4}Q[1-4]$/.test(record.period_id)
    && block.views[record.period_id]
    && [record.passengers, record.ask_km, record.load_factor_reported,
      record.rask_cents_per_km, record.cask_cents_per_km, record.unit_margin_cents_per_km].every(Number.isFinite))
    .map(record => record.period_id)))].sort();
}
