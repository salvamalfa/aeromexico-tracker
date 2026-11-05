import { afterEach, expect, it, vi } from "vitest";
import type { MarketDocument } from "../../types/domain";
import { initPeriods } from "../../state/period";
import { entityState } from "./entities";
import Plotly from "../../lib/plotly";
import { mountMarketControls, renderMarket } from "./market";
vi.mock("../../lib/plotly", () => ({ default: { react: vi.fn() } }));
function period(period_id: string, total: number) {
  const segment = { mexican_carriers_passengers: total, carriers: {
    AEROMEXICO: { passengers: total / 2, share: 0.5 },
    VOLARIS: { passengers: total / 4, share: 0.25 },
    VIVA_AEROBUS: { passengers: total / 4, share: 0.25 },
  }, industry: { passengers: total, share: 1 } };
  return { period_id, period_label: period_id, segments: { total: segment, domestic: segment, international: segment } };
}
afterEach(() => { entityState.market = null; vi.clearAllMocks(); });
it("keeps the entire monthly history after quarter and segment changes",()=>{
 document.body.innerHTML='<article id="market-card"><div id="market-chart"></div></article><select id="market-segment"><option>total</option><option>international</option></select>';
 entityState.market={schema_version:"market_payload_v1",carriers:["AEROMEXICO","VOLARIS","VIVA_AEROBUS"],metadata:{default_quarter:"2026Q2",first_period:"2026M03",last_period:"2026M06",industry_note:"",industry_share_latest:1,method_note:""},quarters:[],months:[period("2026M03",40),period("2026M04",50),period("2026M06",50)]} as MarketDocument;
 initPeriods(["2026Q1","2026Q2"],"2026Q1");mountMarketControls();renderMarket(undefined);
 let call=vi.mocked(Plotly.react).mock.calls.at(-1)!;
 expect(call[1][0]).toMatchObject({x:["2026-03-01","2026-04-01","2026-06-01"],hoverinfo:"none"});
 expect(call[2]?.xaxis?.range).toEqual(["2026-03-01","2026-06-01"]);
 expect(call[2]?.shapes?.[0]?.x0).toBe("2026-01-01");
 const select=document.getElementById("market-segment") as HTMLSelectElement;select.value="international";select.dispatchEvent(new Event("change"));
 initPeriods(["2026Q1","2026Q2"],"2026Q2");renderMarket(undefined);
 call=vi.mocked(Plotly.react).mock.calls.at(-1)!;
 expect(call[1][0]).toMatchObject({x:["2026-03-01","2026-04-01","2026-06-01"]});
 expect(call[2]?.shapes?.[0]?.x1).toBe("2026-07-01");
});
it("preserves reported observations continuously without an artificial July break",()=>{
 document.body.innerHTML='<div id="market-chart"></div><button id="market-source"></button><p id="market-source-note"></p>';
 entityState.market={schema_version:"market_payload_v1",carriers:["AEROMEXICO","VOLARIS","VIVA_AEROBUS"],metadata:{default_quarter:"2026Q2",first_period:"2026M06",last_period:"2026M08",industry_note:"",industry_share_latest:1,method_note:"",method_breaks:["2026M07"]},quarters:[],months:[period("2026M06",50),period("2026M07",60),period("2026M08",70)]} as MarketDocument;
 renderMarket("2026Q3");const call=vi.mocked(Plotly.react).mock.calls.at(-1)!;
 expect(call[1][0]).toMatchObject({x:["2026-06-01","2026-07-01","2026-08-01"],y:[50,50,50],connectgaps:false});
 expect(call[2]?.shapes).not.toContainEqual(expect.objectContaining({type:"line"}));
 expect(document.getElementById("market-source-note")?.textContent).toContain("agosto de 2026");
});
it("does not replace an earlier selected quarter with the last available month",()=>{
 document.body.innerHTML='<article id="market-card"><div id="market-chart"></div></article>';
 entityState.market={schema_version:"market_payload_v1",carriers:["AEROMEXICO","VOLARIS","VIVA_AEROBUS"],metadata:{default_quarter:"2026Q2",first_period:"2026M06",last_period:"2026M06",industry_note:"",industry_share_latest:1,method_note:""},quarters:[],months:[period("2026M06",50)]} as MarketDocument;
 renderMarket("2026Q1");const call=vi.mocked(Plotly.react).mock.calls.at(-1)!;
 expect(call[1][0]).toMatchObject({x:["2026-06-01"]});expect(call[2]?.shapes?.[0]?.x0).toBe("2026-01-01");
 expect(document.getElementById("market-card")?.dataset.comparisonPeriod).toBe("2026Q1");
});
