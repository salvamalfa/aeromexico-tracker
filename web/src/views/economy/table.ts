// Builds the "Ver datos por trimestre" disclosure table. Port of
// _data_rows() in src/dashboard/executive_summary_html.py (rendered once
// per full page load there; here it can be called once after
// web/public/data/v1/executive.json loads, since every quarter's row is
// shown at once regardless of the active period).

import { entityRecords, entityView } from "../executive/entities";
import type { EntityKey } from "../shell/carriers";
import type { Comparison } from "../../types/domain";

function metricCell(value: string, comparison: Comparison): string {
  const delta = comparison.available ? comparison.display : "—";
  return (
    '<span class="table-metric">' +
    `<span>${value}</span>` +
    `<small class="delta-${comparison.direction}" title="vs. trimestre anterior">${delta}</small>` +
    "</span>"
  );
}

function signedTwoDecimals(value: number): string {
  return `${value >= 0 ? "+" : ""}${Number(value).toFixed(2)}`;
}

// Rows follow the entity chosen for the KPI cards (Dashboard v2); entity
// views name the occupancy KPI `load_factor`, v1 views `load_factor_reported`.
export function renderQuarterTable(entity: EntityKey = "AEROMEXICO"): void {
  const body = document.querySelector(".disclosure-body tbody");
  if (!body) return;
  const records = entityRecords(entity).filter((record) => entityView(entity, record.period_id));
  const rows = [...records].reverse().map((record) => {
    const view = entityView(entity, record.period_id)!;
    const kpis = new Map(view.kpis.map((item) => [item.key === "load_factor" ? "load_factor_reported" : item.key, item]));
    const rowClass = String(record.period_id).endsWith("Q4") ? ' class="year-separator"' : "";
    return (
      `<tr${rowClass}>` +
      `<td>${record.period_label}</td>` +
      `<td>${metricCell(record.rask_cents_per_km.toFixed(2), kpis.get("rask_cents_per_km")!.qoq)}</td>` +
      `<td>${metricCell(record.cask_cents_per_km.toFixed(2), kpis.get("cask_cents_per_km")!.qoq)}</td>` +
      `<td>${metricCell(signedTwoDecimals(record.unit_margin_cents_per_km), view.margin_qoq)}</td>` +
      `<td>${metricCell((record.ask_km / 1_000_000_000).toFixed(2), kpis.get("ask_km")!.qoq)}</td>` +
      `<td>${metricCell(`${(record.load_factor_reported * 100).toFixed(1)}%`, kpis.get("load_factor_reported")!.qoq)}</td>` +
      `<td>${metricCell((record.passengers / 1_000_000).toFixed(3), kpis.get("passengers")!.qoq)}</td>` +
      "</tr>"
    );
  });
  body.innerHTML = rows.join("");
}
