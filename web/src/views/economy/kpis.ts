// Updates the 4 KPI cards on panel-economy (RASK, CASK, ASK, Margen
// unitario) for the active period and the entity chosen in the cards'
// airline selector (Dashboard v2). Port of updateKpis() in
// src/dashboard/assets/executive_summary.js; load_factor_reported and
// passengers are part of the payload's per-KPI list too, but reader_ui.py
// removes those two cards from the published page, so this view never
// renders them either — see web/index.html's panel-economy markup.
//
// Aeroméxico reads the same top-level view as v1; any single carrier also
// fills the "vs. industria" chip (hidden for Industria itself).

import { $ } from "../flights/dom";
import { entityRecord, entityRecords, entityView, industryComparisonView } from "../executive/entities";
import type { EntityKey } from "../shell/carriers";
import type { Comparison } from "../../types/domain";

const READER_KPI_KEYS = ["rask_cents_per_km", "cask_cents_per_km", "ask_km"] as const;
const ALL_KEYS = [...READER_KPI_KEYS, "unit_margin_cents_per_km"] as const;
const UNAVAILABLE: Comparison = { available: false, display: "No disponible", direction: "na" };

function setText(id: string, value: string): void {
  const node = document.getElementById(id);
  if (node) node.textContent = value;
}

function comparisonText(comparison: Comparison): string {
  return comparison.available ? comparison.display : "No disponible";
}

function signedTwoDecimals(value: number): string {
  return `${value >= 0 ? "+" : ""}${Number(value).toFixed(2)}`;
}

function setComparison(key: string, suffix: string, comparison: Comparison): void {
  setText(`kpi-${key}-${suffix}`, comparisonText(comparison));
  const node = $(`kpi-${key}-${suffix}`);
  if (node) node.className = `delta-${comparison.direction}`;
}

function setIndustryChip(key: string, comparison: Comparison | undefined): void {
  const chip = document.getElementById(`kpi-${key}-vsi`)?.closest<HTMLElement>(".vs-industry");
  if (!chip) return;
  chip.hidden = !comparison;
  if (!comparison) return;
  // A share of the industry (ASK) is context, not a better/worse signal.
  setComparison(key, "vsi", key === "ask_km" ? { ...comparison, direction: "flat" } : comparison);
}

function marginRecordValue(entity: EntityKey, periodId: string): number | undefined {
  if (entity === "AEROMEXICO") {
    return entityRecords("AEROMEXICO").find((record) => record.period_id === periodId)?.unit_margin_cents_per_km;
  }
  return entityRecord(entity, periodId)?.unit_margin_cents_per_km;
}

export function updateKpis(entity: EntityKey, periodId: string): void {
  const view = entityView(entity, periodId);
  if (!view) {
    for (const key of ALL_KEYS) {
      setText(`kpi-${key}-value`, "No disponible");
      setComparison(key, "qoq", UNAVAILABLE);
      setComparison(key, "yoy", UNAVAILABLE);
      setIndustryChip(key, undefined);
    }
    return;
  }
  const comparisons = industryComparisonView(entity, periodId);
  const industryByKey = new Map((comparisons?.kpis ?? []).map((kpi) => [kpi.key, kpi.vs_industry]));
  const kpisByKey = new Map(view.kpis.map((kpi) => [kpi.key, kpi]));
  for (const key of READER_KPI_KEYS) {
    const kpi = kpisByKey.get(key);
    if (!kpi) continue;
    setText(`kpi-${key}-value`, kpi.display_value);
    setComparison(key, "qoq", kpi.qoq);
    setComparison(key, "yoy", kpi.yoy);
    setIndustryChip(key, industryByKey.get(key) ?? undefined);
    const card = document.querySelector(`[data-kpi='${key}']`);
    if (card) card.setAttribute("aria-label", `${kpi.label}: ${kpi.display_value}`);
  }
  const margin = marginRecordValue(entity, periodId);
  if (margin === undefined) return;
  const value = `${signedTwoDecimals(margin)} ¢ USD`;
  setText("kpi-unit_margin_cents_per_km-value", value);
  setComparison("unit_margin_cents_per_km", "qoq", view.margin_qoq);
  setComparison("unit_margin_cents_per_km", "yoy", view.margin_yoy);
  setIndustryChip("unit_margin_cents_per_km", comparisons?.margin_vs_industry);
  const card = document.querySelector("[data-kpi='unit_margin_cents_per_km']");
  if (card) card.setAttribute("aria-label", `Margen unitario: ${value}`);
}
