import {readFileSync} from "node:fs";
import {expect,it,vi} from "vitest";
import type {MarketDocument} from "../../types/domain";
import {afacMixTooltip,seriesMixTooltip,mixGrowth,scheduleMixTooltip} from "./mix-tooltip";
import {TOOLTIP_UP,TOOLTIP_DOWN} from "../../lib/unified-tooltip";
const market=JSON.parse(readFileSync("../docs/referencias/periodos-20261031/afac-official-market-september.json","utf8")) as MarketDocument;
for(const entity of ["AEROMEXICO","VOLARIS","VIVA_AEROBUS","INDUSTRY"] as const){
 it(`${entity}: Q2/Q3 uses the same three months a year earlier for both segments`,()=>{
  for(const id of ["2026Q2","2026Q3"]){
   const model=afacMixTooltip(market,[entity],id);expect(model.heading).toBe(id==="2026Q2"?"2T26":"3T26");expect(model.comparisonLabel).toBe(id==="2026Q2"?"vs. 2T25":"vs. 3T25");
   const first=id==="2026Q2"?4:7;
   for(const [index,segment] of (["domestic","international"] as const).entries()){
    const sum=(year:number)=>[0,1,2].reduce((total,offset)=>{const block=market.months.find(row=>row.period_id===`${year}M${String(first+offset).padStart(2,"0")}`)!.segments[segment];return total+Number(entity==="INDUSTRY"?block.industry.passengers:block.carriers[entity]!.passengers);},0);
    const current=sum(2026),base=sum(2025),growth=(current/base-1)*100,row=model.rows[index]!;
    expect(row.value).toBe(`${(current/1e6).toFixed(1)} M`);expect(row.change).toBe(`${growth>0?"+":""}${growth.toFixed(1)}%`);
    expect(row.color).toBe(growth>0?TOOLTIP_UP:growth<0?TOOLTIP_DOWN:"#657188");
   }
  }
 });
}
it("labels the hovered month rather than the selected global quarter, with entity names only for a multi-selection",()=>{
 const model=afacMixTooltip(market,["AEROMEXICO","VOLARIS"],"2026M09");
 expect(model.heading).toBe("septiembre de 2026");expect(model.comparisonLabel).toBe("vs. septiembre de 2025");expect(model.rows).toHaveLength(4);expect(model.rows[0]!.label).toBe("Aeroméxico · Nacional");expect(model.rows[2]!.label).toBe("Volaris · Nacional");
});
it("compares only the current partial months and never fills a missing prior segment with zero",()=>{
 const data=structuredClone(market);
 data.months=data.months.filter(row=>row.period_id!=="2026M09");
 const quarter=data.quarters.find(row=>row.period_id==="2026Q3")!;
 for(const segment of ["domestic","international"] as const)quarter.segments[segment].carriers.AEROMEXICO!.passengers=data.months.filter(row=>["2026M07","2026M08"].includes(row.period_id)).reduce((sum,row)=>sum+row.segments[segment].carriers.AEROMEXICO!.passengers!,0);
 const model=afacMixTooltip(data,["AEROMEXICO"],"2026Q3");expect(model.comparisonLabel).toBe("vs. julio–agosto de 2025");expect(model.rows.every(row=>row.change!=="N/D")).toBe(true);
 data.months.find(row=>row.period_id==="2025M08")!.segments.international.carriers.AEROMEXICO!.passengers=null;
 expect(afacMixTooltip(data,["AEROMEXICO"],"2026Q3").rows[1]!.change).toBe("N/D");
 expect(mixGrowth(10,0)).toBeNull();expect(mixGrowth(null,5)).toBeNull();expect(mixGrowth(0,5)).toBe(-100);
});
it("corporate monthly comparators stay in their own report and label reserved segments",()=>{
 const points=[{date:"2025-09-01",domestic:100,international:200},{date:"2026-09-01",domestic:110,international:180}];
 const model=seriesMixTooltip(points,"2026M09","month",true);
 expect(model.heading).toBe("septiembre de 2026 · tramos reservados");expect(model.comparisonLabel).toBe("vs. septiembre de 2025");expect(model.rows.map(row=>row.change)).toEqual(["+10.0%","-10.0%"]);
 expect(seriesMixTooltip(points.slice(1),"2026M09","month").rows.every(row=>row.change==="N/D")).toBe(true);
});
it("a delayed earlier render cannot restore an old quarter's tooltip",async()=>{
 document.body.innerHTML='<div><p id="mix-coverage">Cobertura</p><div id="mix-chart" aria-describedby="mix-coverage"></div></div>';let resolve!:()=>void;
 const old=new Promise<void>(done=>{resolve=done;});
 scheduleMixTooltip(old,["old"],()=>({heading:"old",comparisonLabel:"old",rows:[]}));
 scheduleMixTooltip(Promise.resolve(),["new"],()=>({heading:"new",comparisonLabel:"new",rows:[]}));
 await Promise.resolve();resolve();await Promise.resolve();
 document.getElementById("mix-chart")!.dispatchEvent(new FocusEvent("focus"));expect(document.getElementById("mix-chart-detail")!.textContent).toContain("new");expect(document.getElementById("mix-chart-detail")!.textContent).not.toContain("old");
 expect(document.getElementById("mix-chart")!.getAttribute("aria-describedby")!.split(" ")).toEqual(["mix-coverage","mix-chart-detail"]);
});
