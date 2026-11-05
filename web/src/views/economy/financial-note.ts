import { entityLabel, entityView, entityRecords } from "../executive/entities";
import type { EntityKey } from "../shell/carriers";

export function renderFinancialNote(entity: EntityKey, period: string): void {
  const host = document.getElementById("financial-comparison-note");
  if (!host) return;
  host.replaceChildren();
  const view = entityView(entity, period);
  host.hidden = !!view && period !== "2026Q3";
  if (host.hidden) return;
  if (!view) {
    const latest = entityRecords(entity).map(row => row.period_id).sort().at(-1);
    const label = (id: string) => `${id.slice(-1)}T${id.slice(2,4)}`;
    host.textContent = `${entityLabel(entity)}: No disponible para ${label(period)}.${latest ? ` Último trimestre financiero publicado: ${label(latest)}.` : ""}`
      + (entity === "INDUSTRY" ? " El agregado de Industria está pendiente de actualización y validación con las tres aerolíneas; disponer de sus reportes individuales no actualiza automáticamente el agregado." : "");
    return;
  }
  const notes = view.narrative?.paragraphs ?? [];
  if (!notes.length) { host.hidden = true; return; }
  if (view.narrative?.headline === "Industria calculada · vista previa para revisión") {
    const label = document.createElement("p");
    label.textContent = "Industria calculada con los tres reportes financieros · vista previa para revisión.";
    host.append(label);
  }
  const details = document.createElement("details");
  const summary = document.createElement("summary");
  summary.textContent = `Fuente y bases de comparación · ${entityLabel(entity)} 3T26`;
  details.append(summary);
  for (const text of notes) {
    const p = document.createElement("p"); p.textContent = text; details.append(p);
  }
  const url = entity === "AEROMEXICO" ? "https://ir.aeromexico.com/financial-information/quarterly-results"
    : entity === "VIVA_AEROBUS" ? "https://cdn.investorcloud.net/VivaAerobus/InformacionFinanciera/ReportesTrimestrales/2026-3T26-en.pdf"
    : entity === "VOLARIS" ? "https://www.sec.gov/Archives/edgar/data/1520504/000129281426005010/ex99-1.htm" : null;
  if (url) {
    const source = document.createElement("a");
    source.href = url;
    source.textContent = entity === "VOLARIS" ? "Reporte de referencia SEC" : "Resultados trimestrales del emisor";
    source.target = "_blank"; source.rel = "noopener noreferrer";
    details.append(source);
  }
  host.append(details);
}
