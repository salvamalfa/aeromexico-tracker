import { financialKpiSources } from "../../lib/financial-sources";
import { entityLabel, entityView } from "../executive/entities";
import { bindSourceInfo } from "../market/source-info";
import type { EntityKey } from "../shell/carriers";

const DEFINITIONS: Record<string,{label:string;definition:string;industry:string}> = {
  rask_cents_per_km:{label:"RASK",definition:"Ingreso total por asiento-kilómetro. RASK = ingreso total / ASK × 100 (¢ USD).",industry:"Industria pondera por capacidad (ASK)."},
  cask_cents_per_km:{label:"CASK",definition:"Costo por asiento-kilómetro; CASK = CASM ÷ 1.609344 cuando el reporte usa millas.",industry:"Industria pondera por capacidad (ASK)."},
  ask_km:{label:"ASK",definition:"Capacidad: asientos × kilómetros. ASK = ASM × 1.609344; tarjeta en miles de millones.",industry:"Industria suma las tres aerolíneas."},
  unit_margin_cents_per_km:{label:"Margen unitario",definition:"Ingreso menos costo por asiento-kilómetro. Margen = RASK − CASK (¢ USD).",industry:"Industria usa RASK y CASK ponderados por capacidad."},
};
const INFO_SVG = '<svg viewBox="0 0 16 16" aria-hidden="true" focusable="false"><circle cx="8" cy="8" r="6.5" fill="none" stroke="currentColor"/><circle cx="8" cy="4.8" r=".8" fill="currentColor"/><path d="M8 7v4" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round"/></svg>';

export function renderEconomyKpiSources(entity: EntityKey, period: string): void {
  for (const [key,definition] of Object.entries(DEFINITIONS)) {
    const card = document.querySelector<HTMLElement>(`[data-kpi="${key}"]`);
    const title = card?.querySelector<HTMLElement>(".kpi-label");
    if (!card || !title) continue;
    let button = card.querySelector<HTMLButtonElement>("button.kpi-info");
    let panel = card.querySelector<HTMLElement>(".economy-kpi-source");
    if (!button || !panel) {
      card.querySelector(".kpi-info")?.remove();
      button = document.createElement("button"); button.type = "button"; button.className = "kpi-info";
      button.innerHTML = INFO_SVG; title.append(button);
      panel = document.createElement("div"); panel.id = `economy-source-${key}`; panel.className = "economy-kpi-source";
      card.append(panel); bindSourceInfo(button,panel);
    }
    button.removeAttribute("title"); button.setAttribute("aria-label",`Definición y fuente de ${definition.label}`);
    const source = document.createElement("b");
    source.textContent = `Fuente: ${entity === "INDUSTRY" ? "reportes financieros" : entityLabel(entity)} · ${period.slice(-1)}T${period.slice(2,4)}. `;
    const unavailable = entityView(entity,period) ? "" : " No disponible para este trimestre.";
    panel.replaceChildren(source, document.createTextNode(`${definition.definition} ${entity === "INDUSTRY" ? definition.industry : ""}${unavailable} `));
    financialKpiSources(entity,period).forEach((link,index) => {
      if (index) panel!.append(document.createTextNode(" · "));
      const anchor = document.createElement("a"); anchor.href = link.href; anchor.textContent = link.label;
      anchor.target = "_blank"; anchor.rel = "noopener noreferrer"; panel!.append(anchor);
    });
  }
}
