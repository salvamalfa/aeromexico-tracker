// Updates the 4 KPI cards on panel-economy (RASK, CASK, ASK, Margen
// unitario) for the active period. Port of updateKpis() in
// src/dashboard/assets/executive_summary.js; load_factor_reported and
// passengers are part of the payload's per-KPI list too, but reader_ui.py
// removes those two cards from the published page, so this view never
// renders them either — see web/index.html's panel-economy markup.

import { $ } from "../flights/dom.js";
import { state } from "../executive/state.js";

const READER_KPI_KEYS = ["rask_cents_per_km", "cask_cents_per_km", "ask_km"];

function setText(id, value) {
  const node = document.getElementById(id);
  if (node) node.textContent = value;
}

function comparisonText(comparison) {
  return comparison.available ? comparison.display : "No disponible";
}

function signedTwoDecimals(value) {
  return `${value >= 0 ? "+" : ""}${Number(value).toFixed(2)}`;
}

function setComparison(key, suffix, comparison) {
  setText(`kpi-${key}-${suffix}`, comparisonText(comparison));
  const node = $(`kpi-${key}-${suffix}`);
  if (node) node.className = `delta-${comparison.direction}`;
}

export function updateKpis(view) {
  const kpisByKey = new Map(view.kpis.map((kpi) => [kpi.key, kpi]));
  for (const key of READER_KPI_KEYS) {
    const kpi = kpisByKey.get(key);
    if (!kpi) continue;
    setText(`kpi-${key}-value`, kpi.display_value);
    setComparison(key, "qoq", kpi.qoq);
    setComparison(key, "yoy", kpi.yoy);
    const card = document.querySelector(`[data-kpi='${key}']`);
    if (card) card.setAttribute("aria-label", `${kpi.label}: ${kpi.display_value}`);
  }
  const record = state.records[state.periodIndex];
  if (!record) return;
  const value = `${signedTwoDecimals(record.unit_margin_cents_per_km)} ¢ USD`;
  setText("kpi-unit_margin_cents_per_km-value", value);
  setComparison("unit_margin_cents_per_km", "qoq", view.margin_qoq);
  setComparison("unit_margin_cents_per_km", "yoy", view.margin_yoy);
  const card = document.querySelector("[data-kpi='unit_margin_cents_per_km']");
  if (card) card.setAttribute("aria-label", `Margen unitario: ${value}`);
}
