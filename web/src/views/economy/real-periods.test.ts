// Regression against the actual constructed, versioned payload, not fabricated KPIs.
import { readFileSync } from "node:fs";
import { beforeEach, expect, it, vi } from "vitest";
import type { ExecutiveDocument, MarketDocument } from "../../types/domain";
import { state, loadExecutive } from "../executive/state";
import { entityRecords, entityState } from "../executive/entities";
import { initPeriods } from "../../state/period";
import { financialPeriods } from "../../state/financial-period";
import { renderUnitEconomics, renderVolumeMonetization, renderLoadMonetization, setUnitEntities, setVolumeEntities, setLoadEntities } from "./charts";
import { updateKpis } from "./kpis";
import { renderFinancialNote } from "./financial-note";
import { renderMarket } from "../executive/market";
import Plotly from "../../lib/plotly";
import type { EntityKey } from "../shell/carriers";

vi.mock("../../lib/plotly", () => ({ default: { react: vi.fn(async (id: string) => {
  const host = document.getElementById(id); if (host) (host as unknown as {on: unknown}).on = vi.fn();
}), Fx: { unhover: vi.fn(), hover: vi.fn() } } }));
const payload = JSON.parse(readFileSync("../site/data/v1/executive.json", "utf8")) as ExecutiveDocument;
const market = JSON.parse(readFileSync("../site/data/v1/market.json", "utf8")) as MarketDocument;
beforeEach(() => {
  document.body.innerHTML = readFileSync("index.html", "utf8");
  state.records = payload.records; state.views = payload.views;
  state.entities = payload.entities!; state.entityList = payload.entity_list!;
  entityState.market = market; vi.mocked(Plotly.react).mockClear();
});

it("opens the latest verifiable financial quarter and respects every historical deep link", async () => {
  vi.stubGlobal("fetch", vi.fn(async () => ({ ok: true, json: async () => payload })));
  const periods = financialPeriods(payload);
  window.history.replaceState(null, "", "/");
  await loadExecutive(); expect(state.records[state.periodIndex]!.period_id).toBe(periods.at(-1));
  for (const period of periods) {
    window.history.replaceState(null,"",`/?period=${period}`); await loadExecutive();
    expect(state.records[state.periodIndex]!.period_id).toBe(period);
  }
  vi.unstubAllGlobals(); window.history.replaceState(null,"","/");
});

for (const entity of ["AEROMEXICO", "VIVA_AEROBUS", "VOLARIS", "INDUSTRY"] as EntityKey[]) {
  it(`${entity}: Q2 → Q3 → Q2 checks KPI values, every history trace and selected scatter coordinates`, async () => {
    setUnitEntities([entity]); setVolumeEntities([entity]); setLoadEntities([entity]);
    for (const period of ["2026Q2", "2026Q3", "2026Q2"]) {
      initPeriods(financialPeriods(payload),period);
      state.periodIndex = state.records.findIndex(row => row.period_id === period);
      const records = entityRecords(entity), selected = records.find(row => row.period_id === period);
      updateKpis(entity,period); renderFinancialNote(entity,period);
      renderUnitEconomics(); renderVolumeMonetization(); renderLoadMonetization(period); await Promise.resolve();
      const calls = vi.mocked(Plotly.react).mock.calls;
      const unit = calls.filter(call => call[0] === "unit-chart").at(-1)!;
      const volume = calls.filter(call => call[0] === "volume-chart").at(-1)!;
      const load = calls.filter(call => call[0] === "load-chart").at(-1)!;
      expect(unit[1][1]).toMatchObject({ x: records.map(r => r.period_label), y: records.map(r => r.rask_cents_per_km) });
      expect(unit[2]?.annotations?.[0]?.text).toBe(`${period.slice(-1)}T26`);
      expect(volume[2]?.annotations?.[0]?.text).toBe(`${period.slice(-1)}T26`);
      if (entity !== "INDUSTRY") expect(volume[1][0]).toMatchObject({ x: records.map(r => r.period_label), y: records.map(r => r.passengers / 1e6) });
      else for (const [index, key] of ["AEROMEXICO", "VOLARIS", "VIVA_AEROBUS"].entries()) {
        const members = new Map(entityRecords(key as EntityKey).map(r => [r.period_id,r]));
        expect(volume[1][index]).toMatchObject({ y: records.map(r => members.get(r.period_id)!.passengers / 1e6) });
      }
      const years = [...new Set(records.map(r => r.period_id.slice(0,4)))];
      for (const [index,year] of years.entries()) {
        const rows = records.filter(r => r.period_id.startsWith(year));
        expect(load[1][index]).toMatchObject({x:rows.map(r => r.load_factor_reported*100),y:rows.map(r => r.rask_cents_per_km)});
      }
      const ring = load[1].at(-1) as { x: number[]; y: number[] };
      expect(ring.x).toEqual(selected ? [selected.load_factor_reported*100] : []);
      expect(ring.y).toEqual(selected ? [selected.rask_cents_per_km] : []);
      if (selected) expect(document.getElementById("kpi-rask_cents_per_km-value")?.textContent).toBe(`${selected.rask_cents_per_km.toFixed(1)} ¢ USD`);
      else {
        expect(document.getElementById("kpi-rask_cents_per_km-value")?.textContent).toBe("No disponible");
        expect(document.getElementById("financial-comparison-note")).toBeNull();
      }
      for (const id of ["unit-chart", "volume-chart", "load-chart"]) {
        expect(document.getElementById(`${id}-coverage`)).toBeNull();
        expect(document.getElementById(id)?.getAttribute("aria-description")).toContain(selected ? "disponible" : "sin dato para 3T26");
      }
    }
  });
}

it("real AFAC keeps every reported share unchanged, joins June to July and stops in August", () => {
  renderMarket("2026Q3");
  expect(market.months.at(-1)?.period_id).toBe("2026M08");
  expect(market.quarters.some(row => row.period_id === "2026Q3")).toBe(false);
  const call = vi.mocked(Plotly.react).mock.calls.at(-1)!;
  const trace = call[1][0] as {x: string[]; y: Array<number|null>};
  const july = trace.x.indexOf("2026-07-01");
  expect(trace.x[july - 1]).toBe("2026-06-01");
  expect(trace.y[july - 1]).toBeTypeOf("number");
  expect(trace.y[july]).toBeTypeOf("number");
  expect(trace.x.at(-1)).toBe("2026-08-01");
  expect(new Set(trace.x).size).toBe(trace.x.length);
  for (const [i, key] of ["AEROMEXICO", "VOLARIS", "VIVA_AEROBUS"].entries()) {
    const actual = call[1][i] as { y: Array<number|null> };
    const months = market.months.filter(row => row.period_id >= "2021M01");
    expect(actual.y).toEqual(months.map(row => {
      const share = row.segments.total.carriers[key]?.share;
      return share == null ? null : share * 100;
    }));
  }
  expect(document.getElementById("market-method-note")).toBeNull();
  expect(document.getElementById("market-source-note")?.textContent).toContain("agosto de 2026");
});

it("a later complete issuer quarter controls the default even before AM or Industry has it", () => {
  const later = structuredClone(payload);
  const issuer = later.entities!.VIVA_AEROBUS!;
  issuer.records.push({...issuer.records.at(-1)!,period_id:"2030Q1",period_label:"1T30"});
  issuer.views["2030Q1"] = {...issuer.views["2026Q3"]!,period_id:"2030Q1",period_label:"1T30"};
  expect(financialPeriods(later).at(-1)).toBe("2030Q1");
  delete issuer.views["2030Q1"];
  expect(financialPeriods(later).at(-1)).toBe("2026Q3");
});

it("comparison modes retain Q3 gaps for Industry and select the actual issuer points", async () => {
  const entities: EntityKey[] = ["INDUSTRY","AEROMEXICO","VIVA_AEROBUS","VOLARIS"];
  initPeriods(financialPeriods(payload),"2026Q3");
  setUnitEntities(entities); setVolumeEntities(entities); setLoadEntities(entities);
  renderUnitEconomics(); renderVolumeMonetization(); renderLoadMonetization("2026Q3"); await Promise.resolve();
  const calls = vi.mocked(Plotly.react).mock.calls;
  const unit = calls.find(call => call[0] === "unit-chart")!;
  expect((unit[1][0] as {y: unknown[]}).y.at(-1)).toBeNull();
  for (let index=1;index<entities.length;index++) {
    const row = entityRecords(entities[index]!).find(r => r.period_id === "2026Q3")!;
    expect((unit[1][index] as {y: unknown[]}).y.at(-1)).toBe(row.rask_cents_per_km);
  }
  expect(calls.find(call => call[0] === "load-chart")![1].filter(trace => (trace as {showlegend?: boolean}).showlegend === false)).toHaveLength(3);
});
