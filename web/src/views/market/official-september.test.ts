import { readFileSync } from "node:fs";
import { expect,it,vi } from "vitest";
import type { MarketDocument, MarketSegmentKey } from "../../types/domain";
import { marketSnapshot,selectedMarketPeriods } from "./calculations";
import { entityState } from "../executive/entities";
import { renderMarket } from "../executive/market";
import Plotly from "../../lib/plotly";
import { initPeriods } from "../../state/period";
import { buildChatContext } from "../chat/context";

vi.mock("../../lib/plotly",()=>({default:{react:vi.fn()}}));
const official=JSON.parse(readFileSync("../docs/referencias/periodos-20261031/afac-official-market-september.json","utf8")) as MarketDocument;
it("preserves every real share on Q2/Q3 axes: 15% for Total/National, 8% for International",()=>{
  document.body.innerHTML=readFileSync("index.html","utf8"); entityState.market=official;
  for(const quarter of ["2026Q2","2026Q3"]) for(const segment of ["total","domestic","international"] as MarketSegmentKey[]) {
    (document.getElementById("market-segment") as HTMLSelectElement).value=segment;
    renderMarket(quarter);
    const call=vi.mocked(Plotly.react).mock.calls.at(-1)!;
    const range=call[2]?.yaxis?.range as number[];
    expect(range[0]).toBe(segment==="international" ? 8 : 15);
    const ys=call[1].flatMap(trace=>(trace as {y:Array<number|null>}).y).filter((value):value is number=>value!==null);
    expect(Math.min(...ys)).toBeGreaterThanOrEqual(range[0]!);
    expect(Math.max(...ys)).toBeLessThanOrEqual(range[1]!);
  }
  entityState.market=null;
});

it("traces Q2/Q3 totals and all derived table measures to the same AFAC months in 2025 and 2026",()=>{
  for(const quarter of ["2026Q2","2026Q3"]) for(const segment of ["total","domestic","international"] as MarketSegmentKey[]) {
    const selected=selectedMarketPeriods(official,quarter,segment), snapshot=marketSnapshot(selected.periods,quarter,segment);
    const start=(Number(quarter.slice(-1))-1)*3+1;
    const months=(year:string)=>official.months.filter(row=>row.period_id.slice(0,4)===year && Number(row.period_id.slice(-2))>=start && Number(row.period_id.slice(-2))<start+3);
    const total=(year:string)=>months(year).reduce((sum,row)=>sum+row.segments[segment].mexican_carriers_passengers!,0);
    const current=total("2026"),prior=total("2025");
    expect(snapshot.total).toBe(current); expect(snapshot.delta).toBe(current-prior);
    expect(snapshot.growth).toBeCloseTo((current/prior-1)*100,10);
    for(const [index,key] of ["AEROMEXICO","VOLARIS","VIVA_AEROBUS"].entries()) {
      const passengers=(year:string)=>months(year).reduce((sum,row)=>sum+row.segments[segment].carriers[key]!.passengers!,0);
      const value=passengers("2026"),base=passengers("2025"),row=snapshot.rows[index]!;
      expect(row.passengers).toBe(value); expect(row.growth).toBeCloseTo((value/base-1)*100,10);
      expect(row.share).toBeCloseTo(value/current*100,10);
      expect(row.shareChange).toBeCloseTo((value/current-base/prior)*100,10);
      expect(row.contribution).toBeCloseTo((value-base)/prior*100,10);
    }
  }
});

it("keeps the source as one clickable AFAC link for participation",()=>{
  document.body.innerHTML=readFileSync("index.html","utf8"); entityState.market=official; renderMarket("2026Q3");
  const buttons=[document.getElementById("market-source")!];
  expect(buttons).toHaveLength(1);
  for(const button of buttons) {
    const panel=document.getElementById(button.getAttribute("aria-controls")!)!;
    expect(panel.textContent).toContain("Fuente: AFAC.");
    expect(panel.querySelector("a")?.href).toBe("https://www.gob.mx/afac/acciones-y-programas/estadisticas-280404");
    expect(button.contains(panel)).toBe(false);
  }
  entityState.market=null;
});
it("uses the real AFAC Q3 operator totals, including charter and unmapped Mexican operators",()=>{
  const data=selectedMarketPeriods(official,"2026Q3","total");
  expect(data.partial).toBe(false); expect(data.months).toEqual(["2026M07","2026M08","2026M09"]);
  const result=marketSnapshot(data.periods,"2026Q3","total");
  expect(result.total).toBe(21890201);
  expect(result.rows.map(row=>row.passengers)).toEqual([6056686,8362452,7232729,238334]);
  for (const segment of ["total","domestic","international"] as MarketSegmentKey[]) {
    for (const quarter of ["2026Q2","2026Q3","2026Q2"]) {
      const selected=selectedMarketPeriods(official,quarter,segment);
      const snapshot=marketSnapshot(selected.periods,quarter,segment);
      const source=official.quarters.find(row=>row.period_id===quarter)!.segments[segment];
      expect(snapshot.total).toBe(source.mexican_carriers_passengers);
      expect(snapshot.rows.slice(0,3).reduce((sum,row)=>sum+row.passengers!,0)+snapshot.rows[3]!.passengers!).toBe(snapshot.total);
    }
  }
});
it("compares only matching months when the newest month has not yet arrived",()=>{
  const partial=structuredClone(official);
  partial.months=partial.months.filter(row=>row.period_id!=="2026M09");
  partial.quarters=partial.quarters.filter(row=>row.period_id!=="2026Q3");
  const data=selectedMarketPeriods(partial,"2026Q3","total");
  const snapshot=marketSnapshot(data.periods,"2026Q3","total");
  const sum=(year:string)=>partial.months.filter(row=>[`${year}M07`,`${year}M08`].includes(row.period_id)).reduce((total,row)=>total+row.segments.total.mexican_carriers_passengers!,0);
  expect(data.partial).toBe(true);expect(snapshot.total).toBe(sum("2026"));
  expect(snapshot.delta).toBe(sum("2026")-sum("2025"));
});
it("keeps the complete real history and both axes fixed while the quarter band and chat follow Q2/Q3 or a historical link",()=>{
  document.body.innerHTML=readFileSync("index.html","utf8");entityState.market=official;
  document.querySelectorAll('.reader-tabs [role="tab"]').forEach(tab=>tab.setAttribute("aria-selected",String(tab.id==="tab-flights")));
  for(const segment of ["total","domestic","international"] as MarketSegmentKey[]) {
    (document.getElementById("market-segment") as HTMLSelectElement).value=segment;
    let baseline: unknown;
    for(const period of ["2026Q3","2026Q2","2026Q3","2024Q1","2026Q2"]) {
      window.history.replaceState(null,"",`/?period=${period}`);
      initPeriods(official.quarters.map(row=>row.period_id),new URLSearchParams(location.search).get("period")!);
      renderMarket(undefined);
      const call=vi.mocked(Plotly.react).mock.calls.at(-1)!;
      const trace=call[1][0] as {x:string[]};
      expect(trace.x.at(-1)).toBe("2026-09-01");
      expect(call[2]?.xaxis?.range).toEqual([trace.x[0],"2026-09-01"]);
      const history={traces:call[1],x:call[2]?.xaxis?.range,y:call[2]?.yaxis?.range};
      if(baseline) expect(history).toEqual(baseline); else baseline=structuredClone(history);
      const start=(Number(period.slice(-1))-1)*3+1;
      expect(call[2]?.shapes?.[0]?.x0).toBe(`${period.slice(0,4)}-${String(start).padStart(2,"0")}-01`);
      expect(document.getElementById("market-card")?.dataset.comparisonPeriod).toBe(period);
      expect(buildChatContext(document.getElementById("market-card"))).toMatchObject({tab:"market",period,filters:{segment}});
      expect(buildChatContext(document.getElementById("market-chart"))).toMatchObject({tab:"market",period});
      expect(document.getElementById("market-source-note")?.textContent).toContain("septiembre de 2026");
    }
  }
  window.history.replaceState(null,"","/");
  entityState.market=null;
});

