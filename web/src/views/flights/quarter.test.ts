import { beforeEach, describe, expect, it, vi } from "vitest";
import { initPeriods } from "../../state/period";
import { renderQuarter } from "./quarter";
import { state } from "./state";
vi.mock("./mix", () => ({renderMix:vi.fn()}));
vi.mock("./network", () => ({renderNetworkPeriod:vi.fn(async()=>true)}));
vi.mock("./carriers", () => ({renderEntityKpis:vi.fn()}));
vi.mock("../shell/carriers", () => ({selection:()=>["AEROMEXICO"]}));

describe("financial period and retained flight cut", () => {
  beforeEach(() => {
    document.body.innerHTML='<span id="period-display">3T26</span><button id="period-prev"></button><button id="period-next"></button><p id="flight-data-period"></p><p id="live-status"></p>';
    for(const key of ["passengers","asm_miles","rpm_miles","load_factor"]){
      for(const suffix of ["","-qoq","-yoy"]){const el=document.createElement("span");el.id=`flight-kpi-${key}${suffix}`;document.body.append(el);}
    }
    state.quarters=[{period_id:"2026Q1",period_label:"1T26",metrics:{passengers:{value:1,period_start:"2026-01-01",period_end:"2026-03-31"},asm_miles:{value:2},rpm_miles:{value:1},load_factor:{value:.5}}}];
    state.periodIndex=0;state.byPeriod=new Map(state.quarters.map(r=>[r.period_id,r]));
    state.domesticMonthsQuarterId="2026Q1";
    initPeriods(["2026Q1","2026Q2","2026Q3"],"2026Q3");
  });
  it("does not overwrite the financial header with a retained Q1 flight cut", async()=>{
    await renderQuarter();
    expect(document.getElementById("period-display")?.textContent).toBe("3T26");
    expect(document.getElementById("flight-data-period")?.textContent).toContain("Corte de vuelos: 1T26");
    expect(document.getElementById("flight-data-period")?.textContent).toContain("No hay datos de vuelos para 2026Q3");
    expect(document.getElementById("live-status")?.textContent).toContain("conservan 2026Q3");
  });
  it("keeps the ordinary shared-quarter behavior when that flight quarter exists",async()=>{
    initPeriods(["2026Q1","2026Q2","2026Q3"],"2026Q1");
    await renderQuarter();
    expect(document.getElementById("period-display")?.textContent).toBe("1T26");
    expect(document.getElementById("flight-data-period")?.textContent).not.toContain("No hay datos");
  });
});
