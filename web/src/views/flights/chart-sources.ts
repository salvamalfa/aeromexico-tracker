import { bindSourceInfo, AFAC_CATALOG_URL, setAfacSource } from "../market/source-info";
import { flightKind } from "./flight-measure";
import { state } from "./state";
import type { Route } from "../../types/domain";

const INFO = '<svg viewBox="0 0 16 16" aria-hidden="true" focusable="false"><circle cx="8" cy="8" r="6.5" fill="none" stroke="currentColor"/><circle cx="8" cy="4.8" r=".8" fill="currentColor"/><path d="M8 7v4" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round"/></svg>';
function panelFor(title: HTMLElement, id: string, label: string): HTMLElement {
 let button=title.querySelector<HTMLButtonElement>(`#${id}-button`);
 let panel=document.getElementById(id);
 if(!button){button=document.createElement("button");button.type="button";button.id=`${id}-button`;button.className="kpi-info";button.innerHTML=INFO;button.setAttribute("aria-label",label);title.append(button);}
 if(!panel){panel=document.createElement("div");panel.id=id;title.after(panel);}
 bindSourceInfo(button,panel);return panel;
}
function content(panel:HTMLElement, source:string, detail:string, links:Array<[string,string]>):void {
 const lead=document.createElement("b");lead.textContent="Fuente: ";panel.replaceChildren(lead);
 if(!links.length)panel.append(document.createTextNode(source));
 for(const [index,[label,url]] of links.entries()){
  if(index)panel.append(document.createTextNode(" · "));
  const link=document.createElement("a");link.href=url;link.textContent=label;link.target="_blank";link.rel="noopener noreferrer";panel.append(link);
 }
 panel.append(document.createTextNode(". "+detail));
}
export function renderMapChartSource(routes:Route[]):void {
 const title=document.getElementById("network-title");if(!title)return;
 const labels=routes.flatMap(r=>[r.source_label??"",...(r.flight_components??[]).map(c=>c.source_label??"")]).join(" ");
 const links:Array<[string,string]>=[];
 if(/aerodatabox/i.test(labels))links.push(["AeroDataBox","https://aerodatabox.com/"]);
 if(/T-100|BTS/i.test(labels))links.push(["BTS","https://www.transtats.bts.gov/"]);
 if(routes.some(r=>flightKind(r)!=="estimated" && /AFAC/i.test(r.source_label??"")))links.push(["AFAC",AFAC_CATALOG_URL]);
 if(/ANAC/i.test(labels))links.push(["ANAC","https://www.anac.gov.br/acesso-a-informacao/dados-abertos"]);
 const source=links.map(([label])=>label).join(" y ")||"fuente indicada en cada ruta";
 const detail=state.evidenceView === "north_america_observed"
  ? "Norteamérica: sólo operaciones observadas México–EE.UU.; Canadá y otras rutas estimadas quedan fuera. Las demás regiones conservan sus tipos reales."
  : state.networkMode === "international" && state.selectedRegion === "norteamerica" && !state.hasNorthAmericaObservations
  ? "Sin observados disponibles. Se conservan los tipos de cifra publicados; cobertura parcial."
  : "Vuelos por ruta y periodo; observados, estimados y programación se mantienen separados.";
 content(panelFor(title,"map-chart-source","Fuente y cálculo del mapa"),source,detail,links);
}
export function renderMixChartSource(corporate?:{source_url:string;entity:string}):void {
 const title=document.querySelector<HTMLElement>("#mix-chart")?.closest(".chart-panel")?.querySelector<HTMLElement>(".panel-title");if(!title)return;
 const panel=panelFor(title,"mix-chart-source","Fuente y cálculo de pasajeros por segmento");
 if(corporate)content(panel,corporate.entity,"Mostramos los meses y definiciones del reporte corporativo; no equivalen al universo AFAC.",[["Reporte original",corporate.source_url]]);
 else setAfacSource(panel,"Sumamos pasajeros nacionales e internacionales por aerolínea, regular y fletamento; cada trimestre usa sus meses disponibles.");
}
