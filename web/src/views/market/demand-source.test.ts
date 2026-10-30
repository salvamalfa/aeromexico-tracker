import { beforeEach, expect, it, vi } from "vitest";

beforeEach(() => {
  vi.resetModules();
  document.body.innerHTML='<select id="airport-period"></select><table><tbody id="airport-demand"></tbody></table><table><tbody id="airport-groups"></tbody></table><p id="airport-note"></p><p id="airport-quality"></p>';
});

const source = (variant:boolean) => ({months:["2026M08","2026M09"],airports:[{key:"MEX",group:"GOVERNMENT",period_id:"2026M09",passengers:101,yoy_pct:2,previous_period:"2025M09",previous_passengers:99}],groups:[],quality_notes:["Keep bases separate"],...(variant?{afac_airports:[{key:"MEX",group:"AICM",period_id:"2026M09",passengers:100,yoy_pct:null,previous_period:"2025M09",previous_passengers:null}]}:{})});

it("keeps direct reports by default and offers AFAC in the same table",async()=>{
  vi.stubGlobal("fetch",vi.fn().mockResolvedValue({ok:true,json:async()=>source(true)}));
  const { mountDemand }=await import("./demand");
  await mountDemand("/data/v1");
  expect(document.querySelector("#airport-demand")?.textContent).toContain("101");
  const picker=document.querySelector("#airport-source") as HTMLSelectElement;
  expect(picker.getAttribute("aria-label")).toBe("Base de cifras aeroportuarias");
  picker.value="afac";picker.dispatchEvent(new Event("change"));
  expect(document.querySelector("#airport-demand")?.textContent).toContain("100");
  expect(document.querySelector("#airport-demand")?.textContent).not.toContain("101");
  expect(document.querySelector("#airport-note")?.textContent).toContain("Los grupos conservan sus reportes directos");
  const period=document.querySelector("#airport-period") as HTMLSelectElement;
  period.value="2026M08";period.dispatchEvent(new Event("change"));
  expect(document.querySelector("#airport-demand")?.textContent).toContain("Sin observaciones");
});

it("preserves the existing display when no AFAC variant is published",async()=>{
  vi.stubGlobal("fetch",vi.fn().mockResolvedValue({ok:true,json:async()=>source(false)}));
  const { mountDemand }=await import("./demand");
  await mountDemand("/data/v1");
  expect(document.querySelector("#airport-source")).toBeNull();
  expect(document.querySelector("#airport-demand")?.textContent).toContain("101");
});
