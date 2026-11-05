import {expect,it} from "vitest";
import {routeEvidenceView,routeDataMonths} from "./evidence-view";
import {readFileSync} from "node:fs";
import {routeRegion} from "./regions";
import type {Route} from "../../types/domain";
const base={market_key:"LAX<>MEX",origin:{iata:"MEX",lat:19.4,lon:-99.1},destination:{iata:"LAX",lat:33.9,lon:-118.4},departures:30,operation_status:"estimated_frequencies"} as Route;
it("trims mixed North American components before totals/directions and never mutates the source",()=>{
 const route={...base,flight_components:[{kind:"observed",departures:20,origin_iata:"MEX",destination_iata:"LAX",period_id:"2026M07",source_label:"BTS T-100"},{kind:"estimated",departures:10,origin_iata:"LAX",destination_iata:"MEX",period_id:"2026M07",source_label:"AeroDataBox"}]} as Route;
 const original=structuredClone(route);const view=routeEvidenceView([route],"international","norteamerica");
 expect(view.evidenceView).toBe("north_america_observed");expect(view.routes[0]!.departures).toBe(20);expect(view.routes[0]!.directions).toEqual([{origin_iata:"MEX",destination_iata:"LAX",departures:20}]);
 expect(view.routes[0]!.flight_components).toHaveLength(1);expect(view.routes[0]!.previous).toBeUndefined();expect(view.excluded.estimated).toBe(10);expect(view.observedMonths).toEqual(["2026M07"]);expect(route).toEqual(original);
});
it("preserves estimates when no observations exist and keeps domestic and other regions unchanged",()=>{
 for(const [mode,region] of [["international","norteamerica"],["domestic",null],["international","europa"]] as const){
  const view=routeEvidenceView([base],mode,region);expect(view.evidenceView).toBe("all");expect(view.routes).toEqual([base]);
 }
});

it("keeps September Brazil in South America and prevents its dates from making July-only regions look complete",()=>{
 const network=JSON.parse(readFileSync("../site/data/v1/flights/entities/INDUSTRY/international/2026Q3.json","utf8"));
 const refreshed=JSON.parse(readFileSync("src/views/flights/fixtures/anac-september-routes.json","utf8")).routes as Route[];
 const changed=new Set(refreshed.map(route=>route.market_key));
 const routes=[...(network.routes as Route[]).filter(route=>!changed.has(route.market_key)),...refreshed];
 network.coverage_by_source["Brasil · ANAC"]=["2026M07","2026M08","2026M09"];
 const vcp=routes.find(route=>[route.origin.iata,route.destination.iata].includes("VCP"));expect(vcp).toBeDefined();expect(routeRegion(vcp!)).toBe("sudamerica");
 for(const [region,months] of [["norteamerica",["2026M07"]],["europa",["2026M07"]],["asia",["2026M07"]],["sudamerica",["2026M07","2026M08","2026M09"]]] as const){
  const view=routeEvidenceView(routes,"international",region);const regional=view.routes.filter(route=>routeRegion(route)===region);
  expect(routeDataMonths(regional,network.coverage_by_source)).toEqual(months);
  if(region==="sudamerica")expect(regional.flatMap(route=>route.flight_components??[]).filter(component=>component.source_label.includes("ANAC")).reduce((sum,component)=>sum+component.departures,0)).toBe(184);
  if(region==="norteamerica")expect(regional.reduce((sum,route)=>sum+(route.departures??0),0)).toBe(6251);
 }
});
