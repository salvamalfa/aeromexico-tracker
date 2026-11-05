import {beforeEach,expect,it} from "vitest";
import {renderMapChartSource,renderMixChartSource} from "./chart-sources";
import type {Route} from "../../types/domain";
beforeEach(()=>{document.body.innerHTML='<div><h2 id="network-title">Rutas nacionales</h2></div><article class="chart-panel"><p class="panel-title">Pasajeros y contribución por segmento</p><div id="mix-chart"></div></article>';});
it("keeps provider attribution distinct from AFAC and one trigger after repeated map renders",()=>{
 const routes=[{source_label:"AeroDataBox · AFAC pasajeros · frecuencias históricas estimadas", departures:123, operation_status:"estimated_frequencies"}] as Route[];
 renderMapChartSource(routes);renderMapChartSource(routes);
 expect(document.querySelectorAll("#network-title button")).toHaveLength(1);
 expect(document.querySelector("#map-chart-source")?.textContent).toContain("Fuente: AeroDataBox");
 expect(document.querySelector("#map-chart-source a")?.getAttribute("href")).toBe("https://aerodatabox.com/");
 expect(document.querySelector("#map-chart-source")?.textContent).not.toContain("Fuente: AFAC");
 document.getElementById("network-title")!.textContent="Rutas internacionales";
 renderMapChartSource([{source_label:"BTS T-100"}] as Route[]);
 expect(document.querySelectorAll("#network-title button")).toHaveLength(1);
 expect(document.querySelectorAll("#map-chart-source")).toHaveLength(1);
 expect(document.querySelector("#map-chart-source a")?.getAttribute("href")).toBe("https://www.transtats.bts.gov/");
});
it("updates mix provenance with the actual basis and keeps links accessible",()=>{
 renderMixChartSource();renderMixChartSource();
 const button=document.querySelector<HTMLButtonElement>(".panel-title button")!;
 expect(document.querySelectorAll(".panel-title button")).toHaveLength(1);
 expect(document.querySelector("#mix-chart-source")?.textContent).toContain("regular y fletamento");
 button.focus();expect(button.getAttribute("aria-expanded")).toBe("true");
 renderMixChartSource({entity:"VOLARIS",source_url:"https://ir.volaris.com/original"});
 expect(document.querySelector("#mix-chart-source a")?.getAttribute("href")).toBe("https://ir.volaris.com/original");
 expect(document.querySelector("#mix-chart-source")?.textContent).toContain("no equivalen al universo AFAC");
 document.dispatchEvent(new KeyboardEvent("keydown",{key:"Escape"}));expect(button.getAttribute("aria-expanded")).toBe("false");
});
