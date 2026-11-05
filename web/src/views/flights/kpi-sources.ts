import { financialKpiSources, type FinancialSource } from "../../lib/financial-sources";
import type { QuarterRecord } from "../../types/domain";
import { entityRecord } from "../executive/entities";
import type { EntityKey } from "../shell/carriers";
import { bindSourceInfo } from "../market/source-info";

export const INFO_ICON = '<svg viewBox="0 0 16 16" aria-hidden="true" focusable="false"><circle cx="8" cy="8" r="6.5" fill="none" stroke="currentColor"/><circle cx="8" cy="4.8" r=".8" fill="currentColor"/><path d="M8 7v4" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round"/></svg>';

export function setSourceDetail(panel: HTMLElement, sources: FinancialSource[], detail: string): void {
  const heading = document.createElement("b"); heading.textContent = "Fuente: ";
  panel.replaceChildren(heading);
  sources.forEach((source, index) => {
    if (index) panel.append(document.createTextNode(" · "));
    const link = document.createElement("a"); link.href = source.href; link.textContent = source.label;
    link.target = "_blank"; link.rel = "noopener noreferrer"; panel.append(link);
  });
  if (!sources.length) panel.append(document.createTextNode("sin referencia detallada para esta selección"));
  panel.append(document.createTextNode(`. ${detail}`));
}

const labels = {passengers:"Pasajeros",asm_miles:"ASM",rpm_miles:"RPM",load_factor:"Ocupación"};

export function renderFlightKpiSources(entity: EntityKey, period: string, legacy?: QuarterRecord): void {
  const record = entityRecord(entity, period);
  for (const key of ["passengers", "asm_miles", "rpm_miles", "load_factor"] as const) {
    const card = document.getElementById(`flight-kpi-${key}`)?.closest<HTMLElement>(".flight-kpi");
    const label = card?.querySelector<HTMLElement>(".kpi-label");
    if (!card || !label) continue;
    const old = card.querySelector<HTMLElement>(".info");
    const button = old instanceof HTMLButtonElement ? old : document.createElement("button");
    if (old && old !== button) old.replaceWith(button);
    button.type = "button"; button.className = "info"; button.removeAttribute("title");
    button.setAttribute("aria-label", `Fuente y definición de ${labels[key]}`);
    if (!button.querySelector("svg")) button.innerHTML = INFO_ICON;
    if (button.parentElement !== label) label.append(button);
    card.querySelectorAll(".info").forEach(other => { if (other !== button) other.remove(); });
    const id = `flight-kpi-${key}-source`;
    let panel = card.querySelector<HTMLElement>(`#${id}`);
    if (!panel) { panel = document.createElement("div"); panel.id = id; card.append(panel); }
    const available = legacy ? legacy.metrics[key]?.value != null
      : !!record && (key !== "rpm_miles" || record.rpk_km != null);
    const definition = key === "passengers" ? `Pasajeros transportados en el trimestre.${entity === "INDUSTRY" ? " Industria suma las tres aerolíneas." : ""}`
      : key === "asm_miles" ? `Asientos disponibles por milla. ASK ÷ 1.609344.${entity === "INDUSTRY" ? " Industria suma la capacidad." : ""}`
      : key === "rpm_miles" ? "Pasajeros por milla. RPK ÷ 1.609344; N/D si el emisor no publica RPK."
      : entity === "INDUSTRY" ? "Ocupación de las tres aerolíneas, ponderada por capacidad (ASK)."
      : record?.load_factor_basis === "reported" || legacy ? "Porcentaje de capacidad utilizada publicado por el emisor."
      : "Porcentaje de capacidad utilizada: RPK ÷ ASK × 100.";
    setSourceDetail(panel, financialKpiSources(entity, period), `${period.slice(-1)}T${period.slice(2,4)}. ${available ? "" : "No disponible para este trimestre. "}${definition}`);
    bindSourceInfo(button, panel);
  }
}
