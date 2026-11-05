import { readFileSync } from "node:fs";
import { beforeEach, expect, it, vi } from "vitest";
import type { ExecutiveDocument } from "../../types/domain";
import { state } from "../executive/state";
import { initPeriods } from "../../state/period";
import { financialPeriods } from "../../state/financial-period";
import { renderUnitEconomics, renderVolumeMonetization, renderLoadMonetization, setUnitEntities, setVolumeEntities, setLoadEntities } from "./charts";
import { selectedHover } from "./chart-common";
import { updateKpis } from "./kpis";
import { renderFinancialNote } from "./financial-note";
import Plotly from "../../lib/plotly";

vi.mock("../../lib/plotly", () => ({default: {react:vi.fn(async (id:string) => {
  (document.getElementById(id) as unknown as {on:unknown}).on=vi.fn();
}),Fx:{hover:vi.fn(),unhover:vi.fn()}}}));
const review = JSON.parse(readFileSync("../docs/referencias/periodos-20261031/industry-review-executive.json","utf8")) as ExecutiveDocument;
beforeEach(() => {
  document.body.innerHTML=readFileSync("index.html","utf8");
  state.records=review.records;state.views=review.views;state.entities=review.entities!;
  setUnitEntities(["INDUSTRY"]);setVolumeEntities(["INDUSTRY"]);setLoadEntities(["INDUSTRY"]);
  vi.clearAllMocks();
});
it("the real constructed Industry review fills every KPI and all three charts through Q3", async () => {
  for (const period of ["2026Q3","2026Q2","2026Q3"]) {
    initPeriods(financialPeriods(review),period);
    updateKpis("INDUSTRY",period);renderFinancialNote("INDUSTRY",period);
    renderUnitEconomics();renderVolumeMonetization();renderLoadMonetization(period);await Promise.resolve();
    expect(document.querySelector(".reader-economy-kpis")?.textContent).not.toContain("No disponible");
    const record=review.entities!.INDUSTRY!.records.find(row=>row.period_id===period)!;
    const calls=vi.mocked(Plotly.react).mock.calls;
    const unit=calls.filter(call=>call[0]==="unit-chart").at(-1)!;
    const load=calls.filter(call=>call[0]==="load-chart").at(-1)!;
    if(period==="2026Q3") {
      expect(document.getElementById("kpi-rask_cents_per_km-value")?.textContent).toBe("8.2 ¢ USD");
      expect(document.getElementById("kpi-cask_cents_per_km-value")?.textContent).toBe("7.6 ¢ USD");
      expect(document.getElementById("kpi-unit_margin_cents_per_km-value")?.textContent).toBe("+0.6 ¢ USD");
      expect((unit[1][1] as {y:number[]}).y.at(-1)).toBe(record.rask_cents_per_km);
      expect(load[1].at(-1)).toMatchObject({x:[record.load_factor*100],y:[record.rask_cents_per_km]});
      expect(document.getElementById("financial-comparison-note")).toBeNull();
    }
  }
});
it("selection clears automatic tooltips instead of stacking a duplicate box per trace", () => {
  const host=document.getElementById("unit-chart") as unknown as {data:unknown[]};host.data=[];
  selectedHover("unit-chart");
  expect(Plotly.Fx.unhover).toHaveBeenCalled();expect(Plotly.Fx.hover).not.toHaveBeenCalled();
});

it("recalculates all four comparison metrics from real records on entry Q3 and Q2/Q3 returns", async () => {
  const entities = ["INDUSTRY","AEROMEXICO"] as const;
  setUnitEntities([...entities]);
  for (const period of ["2026Q3","2026Q2","2026Q3"]) {
  initPeriods(financialPeriods(review),period);
  const paths = new Set<string>();
  for (const metric of ["rask_cents_per_km","cask_cents_per_km","cask_ex_fuel_cents_per_km","unit_margin_cents_per_km"]) {
    (document.getElementById("unit-metric") as HTMLSelectElement).value=metric;
    renderUnitEconomics(); await Promise.resolve();
    const call=vi.mocked(Plotly.react).mock.calls.filter(call=>call[0]==="unit-chart").at(-1)!;
    expect(call[2]?.datarevision).toBeUndefined(); // Plotly must compare the new arrays, not a fixed quarter revision.
    const traces=call[1] as Array<{x:string[];y:Array<number|null>}>;
    traces.forEach((trace,index)=>{
      const rows=review.entities![entities[index]!]!.records;
      const expected=trace.x.map(label=>{
        const row=rows.find(row=>row.period_label===label) as unknown as Record<string,unknown> | undefined;
        return typeof row?.[metric]==="number" ? row[metric] : null;
      });
      expect(trace.y).toEqual(expected);
    });
    paths.add(JSON.stringify(traces.map(trace=>trace.y)));
  }
  expect(paths.size).toBe(4);
  }
});
