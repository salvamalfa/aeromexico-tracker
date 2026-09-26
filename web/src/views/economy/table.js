// Builds the "Ver datos por trimestre" disclosure table. Port of
// _data_rows() in src/dashboard/executive_summary_html.py (rendered once
// per full page load there; here it can be called once after
// web/public/data/v1/executive.json loads, since every quarter's row is
// shown at once regardless of the active period).

import { state } from "../executive/state.js";

function metricCell(value, comparison) {
  const delta = comparison.available ? comparison.display : "—";
  return (
    '<span class="table-metric">' +
    `<span>${value}</span>` +
    `<small class="delta-${comparison.direction}" title="vs. trimestre anterior">${delta}</small>` +
    "</span>"
  );
}

export function renderQuarterTable() {
  const body = document.querySelector(".disclosure-body tbody");
  if (!body) return;
  const rows = [...state.records].reverse().map((record) => {
    const view = state.views[record.period_id];
    const kpis = new Map(view.kpis.map((item) => [item.key, item]));
    const rowClass = String(record.period_id).endsWith("Q4") ? ' class="year-separator"' : "";
    return (
      `<tr${rowClass}>` +
      `<td>${record.period_label}</td>` +
      `<td>${metricCell(record.rask_cents_per_km.toFixed(2), kpis.get("rask_cents_per_km").qoq)}</td>` +
      `<td>${metricCell(record.cask_cents_per_km.toFixed(2), kpis.get("cask_cents_per_km").qoq)}</td>` +
      `<td>${metricCell(signedTwoDecimals(record.unit_margin_cents_per_km), view.margin_qoq)}</td>` +
      `<td>${metricCell((record.ask_km / 1_000_000_000).toFixed(2), kpis.get("ask_km").qoq)}</td>` +
      `<td>${metricCell(`${(record.load_factor_reported * 100).toFixed(1)}%`, kpis.get("load_factor_reported").qoq)}</td>` +
      `<td>${metricCell((record.passengers / 1_000_000).toFixed(3), kpis.get("passengers").qoq)}</td>` +
      "</tr>"
    );
  });
  body.innerHTML = rows.join("");
}

function signedTwoDecimals(value) {
  return `${value >= 0 ? "+" : ""}${Number(value).toFixed(2)}`;
}
