import { readFileSync } from "node:fs";
import { afterEach, expect, it } from "vitest";
import type { ExecutiveDocument } from "../../types/domain";
import { financialKpiSources } from "../../lib/financial-sources";
import { state } from "../executive/state";
import { chatCardLabel, mountChatCardActions } from "../chat/card-actions";
import { updateKpis } from "./kpis";
import { renderEconomyChartSource } from "./chart-sources";
import { setSubtitle } from "./chart-common";
import { vi } from "vitest";

vi.mock("../../lib/plotly",()=>({default:{react:vi.fn()},Fx:{}}));
afterEach(()=>{state.records=[];state.views={};state.entities=null;});
it("links the retained Viva Q2/Q3 reports and Volaris Q3 reference, and all three issuers for Industry",()=>{
  expect(financialKpiSources("VIVA_AEROBUS","2026Q2")[0]!.href).toBe("https://cdn.investorcloud.net/VivaAerobus/InformacionFinanciera/ReportesTrimestrales/2026-2T26-en.pdf");
  expect(financialKpiSources("VIVA_AEROBUS","2026Q3")[0]!.href).toBe("https://cdn.investorcloud.net/VivaAerobus/InformacionFinanciera/ReportesTrimestrales/2026-3T26-en.pdf");
  expect(financialKpiSources("VOLARIS","2026Q3")[0]!.href).toBe("https://www.sec.gov/Archives/edgar/data/1520504/000129281426005010/ex99-1.htm");
  expect(financialKpiSources("INDUSTRY","2026Q3").map(link=>link.label)).toEqual([
    "Aeroméxico","Volaris","Viva",
  ]);
});
it("updates all four source panels by issuer and quarter, with exactly one icon despite chat and rerenders", async()=>{
  const data=JSON.parse(readFileSync("../docs/referencias/periodos-20261031/industry-review-executive.json","utf8")) as ExecutiveDocument;
  state.records=data.records;state.views=data.views;state.entities=data.entities!;
  document.body.innerHTML=readFileSync("index.html","utf8");
  const dispose=mountChatCardActions(()=>{});
  for(const period of ["2026Q2","2026Q3","2026Q2"]) for(const entity of ["AEROMEXICO","VIVA_AEROBUS","VOLARIS","INDUSTRY"] as const) {
    updateKpis(entity,period); await Promise.resolve();
    for(const card of document.querySelectorAll(".reader-economy-kpis .kpi-card")) {
      expect(card.querySelectorAll(".kpi-info")).toHaveLength(1);
      expect(card.querySelectorAll(".kpi-info svg")).toHaveLength(1);
      expect(card.querySelectorAll(".economy-kpi-source")).toHaveLength(1);
      const panel=card.querySelector(".economy-kpi-source")!;
      expect(panel.textContent!.split(/\s+/).length).toBeLessThan(65);
      expect(panel.textContent).toContain(`${period.slice(-1)}T26`);
      expect([...panel.querySelectorAll("a")].map(link=>link.href)).toEqual(financialKpiSources(entity,period).map(link=>link.href));
      expect(chatCardLabel(card)).not.toContain("Fuente:");
      expect(chatCardLabel(card)).not.toContain("ⓘ");
      if(entity==="INDUSTRY") expect(panel.querySelectorAll("a")).toHaveLength(3);
    }
  }
  dispose();
});

it("keeps graph sources concise, changes selected issuers and preserves one trigger when titles are repainted",()=>{
  document.body.innerHTML=readFileSync("index.html","utf8");
  for(const entities of [["INDUSTRY"],["AEROMEXICO"],["VOLARIS","VIVA_AEROBUS"],["INDUSTRY"]] as const) {
    setSubtitle("unit-title","Ingreso, costo y margen");
    for(const chart of ["unit","volume","load"] as const) {
      renderEconomyChartSource(chart,[...entities]);
      const card=document.getElementById(`${chart}-chart`)!.closest(".chart-card")!;
      expect(card.querySelectorAll(".chart-title .market-source-info")).toHaveLength(1);
      expect(card.querySelectorAll(".economy-chart-source")).toHaveLength(1);
      const panel=card.querySelector(".economy-chart-source")!;
      expect(panel.textContent).toContain("Fuente: reportes financieros");
      expect(panel.textContent).not.toContain("AFAC");
      expect(panel.textContent!.split(/\s+/).length).toBeLessThan(75);
      expect(panel.querySelectorAll("a")).toHaveLength(entities.some(entity=>entity==="INDUSTRY")?3:entities.length);
      expect(chatCardLabel(card)).not.toContain("Fuente:");
      expect(chatCardLabel(card)).not.toContain("ⓘ");
    }
  }
});
