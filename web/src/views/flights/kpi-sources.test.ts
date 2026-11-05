import { readFileSync } from "node:fs";
import { beforeEach, expect, it } from "vitest";
import type { ExecutiveDocument, QuartersDocument, Route } from "../../types/domain";
import { state as financial } from "../executive/state";
import { financialKpiSources } from "../../lib/financial-sources";
import { renderEntityKpis } from "./carriers";
import { renderFlightKpiSources } from "./kpi-sources";
import { renderNetworkVolume } from "./volume";
import { state } from "./state";

const data = <T>(name:string):T => JSON.parse(readFileSync(`../site/data/v1/${name}.json`,"utf8"));
const executive = data<ExecutiveDocument>("executive");
beforeEach(() => {
  document.body.innerHTML = readFileSync("index.html","utf8");
  financial.records = executive.records; financial.views = executive.views; financial.entities = executive.entities ?? null;
  state.presenceOnlyRouteCount = 0;
});

for (const entity of ["AEROMEXICO", "VOLARIS", "VIVA_AEROBUS", "INDUSTRY"] as const) {
  it(`${entity}: keeps one linked source trigger per financial KPI across real Q2/Q3 renders`, () => {
    for (const period of ["2026Q2", "2026Q3", "2026Q2", "2026Q3"]) {
      renderEntityKpis(entity,period);
      for (const key of ["passengers", "asm_miles", "rpm_miles", "load_factor"]) {
        const card = document.getElementById(`flight-kpi-${key}`)!.closest(".flight-kpi")!;
        expect(card.querySelectorAll(".info")).toHaveLength(1);
        expect(card.querySelectorAll(".info svg")).toHaveLength(1);
        expect(card.querySelectorAll(".info svg circle[r='6.5']")).toHaveLength(1);
        const button = card.querySelector<HTMLButtonElement>("button.info")!;
        expect(button.parentElement!.className).toBe("kpi-label"); expect(button.hasAttribute("title")).toBe(false);
        const panel = document.getElementById(button.getAttribute("aria-controls")!)!;
        expect(card.querySelectorAll(`#${panel.id}`)).toHaveLength(1);
        expect([...panel.querySelectorAll<HTMLAnchorElement>("a")].map(link => link.href))
          .toEqual(financialKpiSources(entity,period).map(source => source.href));
        button.click(); expect(panel.dataset.open).toBe("true");
        button.click(); expect(panel.dataset.open).toBeUndefined();
      }
    }
    expect(document.getElementById("flight-kpi-asm_miles-source")!.textContent).toContain("ASK ÷ 1.609344");
    expect(document.getElementById("flight-kpi-rpm_miles-source")!.textContent).toContain("RPK ÷ 1.609344");
    if (entity === "INDUSTRY") expect(document.getElementById("flight-kpi-load_factor-source")!.textContent).toContain("ponderada por capacidad (ASK)");
  });
}

it("supports the retained financial payload without entity blocks", () => {
  const record = data<QuartersDocument>("flights/quarters").quarters.find(row => row.period_id === "2026Q2")!;
  financial.entities = null;
  renderFlightKpiSources("AEROMEXICO","2026Q2",record);
  expect(document.querySelectorAll(".flight-kpi button.info")).toHaveLength(4);
  expect(document.getElementById("flight-kpi-load_factor-source")!.textContent).toContain("publicado por el emisor");
});

it("attributes real estimated flight counts to AeroDataBox, keeps one trigger, and removes a stale open popup on rerender", () => {
  // Retained historical renderer, no longer mounted by the official map.
  document.body.insertAdjacentHTML("beforeend", '<div id="network-volume"></div>');
  state.routes = data<{routes:Route[]}>("flights/entities/INDUSTRY/domestic/2026M07").routes;
  renderNetworkVolume();
  const button = document.getElementById("network-estimated-info")!;
  const panel = document.getElementById("network-estimated-source")!;
  expect(panel.querySelector<HTMLAnchorElement>("a")!.textContent).toBe("AeroDataBox");
  expect([...panel.querySelectorAll<HTMLAnchorElement>("a")].some(link => link.href.includes("gob.mx/afac"))).toBe(false);
  expect(panel.textContent).toContain("no acredita vuelos realizados");
  button.click(); expect(panel.dataset.open).toBe("true");
  renderNetworkVolume(); expect(panel.dataset.open).toBeUndefined(); expect(button.isConnected).toBe(false);
  expect(document.querySelectorAll("#network-estimated-info")).toHaveLength(1);
  expect(document.querySelectorAll("#network-estimated-info svg")).toHaveLength(1);
  expect(document.querySelectorAll("#flight-map-coverage-button")).toHaveLength(1);
});
