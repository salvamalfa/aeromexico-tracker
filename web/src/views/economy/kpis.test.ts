import { readFileSync } from "node:fs";
import { afterEach, expect, it } from "vitest";
import type { ExecutiveDocument } from "../../types/domain";
import { state } from "../executive/state";
import { updateKpis } from "./kpis";
import { renderQuarterTable } from "./table";

afterEach(() => { state.entities = null; state.records = []; state.views = {}; });

it("rounds only card presentation, including comparisons and accessible labels, preserving raw data and the detailed table", () => {
  const payload = JSON.parse(readFileSync("../site/data/v1/executive.json", "utf8")) as ExecutiveDocument;
  const period = payload.records.at(-1)!.period_id;
  state.records = payload.records; state.views = payload.views; state.entities = payload.entities!;
  const record = state.records.at(-1)!;
  const view = state.views[period]!;
  const rask = view.kpis.find(kpi => kpi.key === "rask_cents_per_km")!;
  // A double-rounding boundary: 8.149 must become 8.1, not 8.2 from 8.15.
  record.rask_cents_per_km = 8.149; rask.value = 8.149; rask.display_value = "8.15 ¢ USD";
  record.unit_margin_cents_per_km = -0.149;
  view.margin_qoq = {available:true,raw:0.149,display:"+0.15 ¢ USD",direction:"up"};
  const industry = state.entities!.AEROMEXICO!.views[period]!;
  industry.margin_vs_industry = {available:true,raw:-0.149,display:"-0.15 ¢ USD",direction:"down"};
  document.body.innerHTML = readFileSync("index.html", "utf8");
  const before = JSON.stringify({record, view, industry});
  updateKpis("AEROMEXICO", period); renderQuarterTable("AEROMEXICO");
  expect(document.getElementById("kpi-rask_cents_per_km-value")?.textContent).toBe("8.1 ¢ USD");
  expect(document.querySelector('[data-kpi="rask_cents_per_km"]')?.getAttribute("aria-label")).toContain("8.1 ¢ USD");
  expect(document.getElementById("kpi-unit_margin_cents_per_km-value")?.textContent).toBe("-0.1 ¢ USD");
  expect(document.getElementById("kpi-unit_margin_cents_per_km-qoq")?.textContent).toBe("+0.1 ¢ USD");
  expect(document.getElementById("kpi-unit_margin_cents_per_km-vsi")?.textContent).toBe("-0.1 ¢ USD");
  expect(document.querySelector(".disclosure-body tbody")?.textContent).toContain("8.15");
  expect(JSON.stringify({record, view, industry})).toBe(before);
});
