import {readFileSync} from "node:fs";
import {beforeEach,expect,it,vi} from "vitest";
import type {MarketDocument,QuarterRecord,QuartersDocument} from "../../types/domain";
import {entityState} from "../executive/entities";
import {renderMix} from "./mix";
import {state} from "./state";
const controls=vi.hoisted(()=>({entity:"AEROMEXICO"}));
vi.mock("../../lib/plotly",()=>({default:{react:vi.fn()}}));
vi.mock("../shell/carriers",async original=>({...await original<typeof import("../shell/carriers")>(),selection:()=>[controls.entity]}));
import Plotly from "../../lib/plotly";
const current=JSON.parse(readFileSync("../docs/referencias/periodos-20261031/afac-official-market-september.json","utf8")) as MarketDocument;
beforeEach(()=>{
 document.body.innerHTML=readFileSync("index.html","utf8"); window.matchMedia=vi.fn().mockReturnValue({matches:false});
 entityState.market=current;state.passengerBasis="afac";state.passengerPeriod="quarter";state.corporateMonthlyPassengers=null;state.corporatePeerMonthlyPassengers={};
 state.monthlyPassengers=(JSON.parse(readFileSync("../site/data/v1/flights/quarters.json","utf8")) as QuartersDocument).monthly_passengers;
 vi.mocked(Plotly.react).mockClear();
});
for(const entity of ["AEROMEXICO","VOLARIS","VIVA_AEROBUS","INDUSTRY"] as const){
 it(`${entity}: plots complete September AFAC quarter and monthly values directly and after Q2/Q3 transitions`,()=>{
  controls.entity=entity;
  for(const period of ["2026Q3","2026Q2","2026Q3"]){
   const month=period==="2026Q3"?"07":"04";
   const record={period_id:period,period_label:period,metrics:{passengers:{period_start:`2026-${month}-01`,period_end:period==="2026Q3"?"2026-09-30":"2026-06-30"}}} as QuarterRecord;
   state.passengerPeriod="quarter";renderMix(record);
   const call=vi.mocked(Plotly.react).mock.calls.at(-1)!;const traces=call[1] as {x:string[];y:number[]}[];
   const point=traces[0]!.x.indexOf(`2026-${month}-01`);expect(point).toBeGreaterThanOrEqual(0);
   const quarter=current.quarters.find(row=>row.period_id===period)!;
   const value=(segment:"domestic"|"international")=>{const block=quarter.segments[segment];return entity==="INDUSTRY"?block.industry!.passengers:block.carriers[entity]!.passengers;};
   expect(traces[0]!.y[point]).toBe(value("domestic"));expect(traces[1]!.y[point]).toBe(value("international"));
   expect(traces[0]!.y[point]!+traces[1]!.y[point]!).toBe(Number(value("domestic"))+Number(value("international")));
   state.passengerPeriod="month";renderMix(record);
   const monthly=vi.mocked(Plotly.react).mock.calls.at(-1)![1] as {x:string[];y:number[]}[];
   expect(monthly[0]!.x.at(-1)).toBe("2026-09-01");
   const september=current.months.find(row=>row.period_id==="2026M09")!;
   const expected=entity==="INDUSTRY"?september.segments.domestic.industry!.passengers:september.segments.domestic.carriers[entity]!.passengers;
   expect(monthly[0]!.y.at(-1)).toBe(expected);
   expect(document.getElementById("mix-coverage")!.textContent).toContain("3 de 3 meses");
  }
  if(entity==="AEROMEXICO")expect(current.metadata.method_note).toContain("Aeroméxico Connect");
 });
}
