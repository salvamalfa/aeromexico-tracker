import { readFileSync } from "node:fs";
import { beforeEach, expect, it, vi } from "vitest";
import { initPeriods } from "../../state/period";
import type { ExecutiveDocument, MarketDocument, QuartersDocument } from "../../types/domain";
import { state as financial } from "../executive/state";
import { entityState } from "../executive/entities";
import { initState, setMapEntity, state } from "./state";
import { selectedFlightQuarter } from "./selected-period";
import { flightTotals } from "./flight-measure";
import { routeRegion } from "./regions";
import { currentMapPeriod } from "./map-periods";
import { renderQuarter } from "./quarter";
import { renderNetworkPeriod } from "./network";
import Plotly from "../../lib/plotly";

const controls = vi.hoisted(() => ({ entity: "AEROMEXICO" }));
vi.mock("../../lib/plotly", () => ({default: { react: vi.fn(async () => {}) }}));
vi.mock("./map", () => ({renderFlowMap: vi.fn()}));
vi.mock("./table", () => ({renderRouteOverview: vi.fn()}));
vi.mock("../shell/carriers", async original => ({...await original<typeof import("../shell/carriers")>(), selection: () => [controls.entity]}));
const data = <T>(name: string): T => JSON.parse(readFileSync(`../site/data/v1/${name}.json`,"utf8"));
const executive = data<ExecutiveDocument>("executive"), quarters = data<QuartersDocument>("flights/quarters");
beforeEach(() => {
  document.body.innerHTML = readFileSync("index.html","utf8");
  financial.records = executive.records; financial.views = executive.views; financial.entities = executive.entities!;
  entityState.market = data<MarketDocument>("market");
  state.mapEntity = "AEROMEXICO"; state.baseAvailablePeriods = null; initState(structuredClone(quarters));
  state.domesticNetworks.clear(); state.domesticMonthlyNetworks.clear(); state.internationalNetworks.clear();
  vi.stubGlobal("fetch", vi.fn(async (name: string) => ({ok:true,json:async () => JSON.parse(readFileSync(`../site/${name}`,"utf8"))})));
  window.matchMedia = vi.fn().mockReturnValue({ matches: false });
});
for (const entity of ["AEROMEXICO","VIVA_AEROBUS","VOLARIS","INDUSTRY"]) {
  it(`${entity}: direct Q3 and Q2→Q3 use real financial values, AFAC cuts and July-only maps`, async () => {
    controls.entity = entity; setMapEntity(entity);
    for (const id of ["2026Q3","2026Q2","2026Q3","2026Q2"]) {
      initPeriods(executive.records.map(row => row.period_id),id);
      state.periodIndex = state.quarters.findIndex(row => row.period_id === id); state.mapPeriodId = null;
      state.networkMode = "domestic";
      await renderQuarter();
      expect(selectedFlightQuarter().period_id).toBe(id); expect(currentMapPeriod()).toBe(id);
      const published = executive.entities![entity]!.records.find(row => row.period_id === id);
      expect(document.getElementById("flight-kpi-passengers")?.textContent).toBe(published ? `${(published.passengers / 1e6).toFixed(1)} M` : "No disponible");
      const mix = vi.mocked(Plotly.react).mock.calls.filter(call => call[0] === "mix-chart").at(-1)!;
      expect(mix[2]?.shapes?.[0]?.x0).toBe(id === "2026Q3" ? "2026-07-01" : "2026-04-01");
      if (id === "2026Q3") {
        expect(state.network!.observed_months).toEqual(["2026M07"]);
        expect(state.network!.expected_months).toEqual(["2026M07","2026M08","2026M09"]);
        const prefix = entity === "AEROMEXICO" ? "flights" : `flights/entities/${entity}`;
        const july = data<{routes: {departures?: number|null}[]}>(`${prefix}/domestic/2026M07`);
        const total = (routes: {departures?: number|null}[]) => routes.reduce((sum,row) => sum+(row.departures ?? 0),0);
        expect(total(state.routes)).toBe(total(july.routes));
        expect(document.getElementById("flight-map-coverage-info")?.textContent).toContain("parcial: 1 de 3 meses");
        expect(document.getElementById("mix-coverage")?.textContent).toContain("No se calcula un trimestre");
        state.networkMode = "international"; await renderNetworkPeriod(id);
        const international = data<{routes: {departures?: number|null}[]}>(`${prefix}/international/2026Q3`);
        expect(total(state.routes)).toBe(total(international.routes) - ({AEROMEXICO:840,VIVA_AEROBUS:162,VOLARIS:150,INDUSTRY:1152}[entity] ?? 0));
        expect(state.evidenceView).toBe("north_america_observed");
        expect(state.network!.observed_months).toEqual(["2026M07"]);
        expect(document.getElementById("flight-map-coverage-info")?.textContent).toContain("parcial: 1 de 3 meses");
        expect(state.routes.some(route => (route.flight_components ?? []).some(row => row.period_id === "2026M09"))).toBe(false);
      }
    }
    vi.unstubAllGlobals();
  });
}

it("an unavailable real domestic quarter clears the previous July network instead of substituting it", async () => {
  controls.entity = "AEROMEXICO";
  initPeriods(executive.records.map(r => r.period_id),"2026Q3");
  state.networkMode = "domestic"; state.mapPeriodId = null;
  await renderNetworkPeriod("2026Q3"); expect(state.routes.length).toBeGreaterThan(0);
  initPeriods(executive.records.map(r => r.period_id),"2021Q1");
  await renderNetworkPeriod("2021Q1");
  expect(state.routes).toEqual([]); expect(currentMapPeriod()).toBe("2021Q1");
  expect(document.getElementById("flight-map-coverage-info")?.textContent).toContain("1T21 · sin datos: 0 de 3 meses");
});

it("keeps real regional evidence and July-only dates coherent across Q2/Q3, scopes and rankings", async () => {
  setMapEntity("INDUSTRY"); state.mapEntity = "INDUSTRY";
  const totals = () => state.routes.reduce((sum,route) => {const values=flightTotals(route);for(const [kind,value] of Object.entries(values))sum[kind]=(sum[kind]??0)+value;return sum;},{} as Record<string,number>);
  for(const period of ["2026Q2","2026Q3","2026Q2","2026Q3"]){
    initPeriods(executive.records.map(row=>row.period_id),period); state.networkMode="international";
    for(const region of ["norteamerica","sudamerica","europa","asia",null]){
      state.selectedRegion=region; await renderNetworkPeriod(period);
      if(region==="norteamerica"){
        expect(state.routes).toHaveLength(period==="2026Q2"?152:112);
        expect(totals()).toEqual({observed:period==="2026Q2"?21630:6251});
        expect(document.getElementById("network-estimated-info")).toBeNull();
        expect(state.routes.every(route=>routeRegion(route)==="norteamerica")).toBe(true);
        expect(state.routes.every(route=>(route.flight_components??[]).every(component=>component.kind==="observed"))).toBe(true);
        expect(state.network!.observed_months).toEqual(period==="2026Q2"?["2026M04","2026M05","2026M06"]:["2026M07"]);
        expect(document.getElementById("flight-map-coverage")!.textContent).toBe("No disponible");
        expect(document.getElementById("network-observed-source")!.textContent).toContain("México–EE.UU.");
      }else if(region==="sudamerica"){
        expect(state.evidenceView).toBe("all");
        expect(totals()).toEqual(period==="2026Q2"?{observed:182,estimated:669,scheduled:1975}:{estimated:891});
      }else if(region==="europa")expect(totals()).toEqual(period==="2026Q2"?{estimated:1722,scheduled:1424}:{estimated:635});
      else if(region==="asia")expect(totals()).toEqual(period==="2026Q2"?{estimated:523,scheduled:182}:{estimated:175});
      else {
        expect(state.evidenceView).toBe("north_america_observed");
        expect(totals().estimated).toBe(period==="2026Q2"?2914:1701);
        expect(state.routes.filter(route=>routeRegion(route)==="norteamerica").every(route=>flightTotals(route).estimated===undefined)).toBe(true);
      }
    }
    state.networkMode="domestic"; await renderNetworkPeriod(period);
    expect(state.evidenceView).toBe("all"); expect(state.selectedRegion).toBeNull();
    expect(totals().estimated).toBeGreaterThan(0); expect(totals().observed).toBeUndefined();
  }
});
