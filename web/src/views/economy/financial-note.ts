import { entityLabel, entityView } from "../executive/entities";
import type { EntityKey } from "../shell/carriers";

export function renderFinancialNote(entity: EntityKey, period: string): void {
  const host = document.getElementById("financial-comparison-note");
  if (!host) return;
  host.replaceChildren();
  host.hidden = period !== "2026Q3";
  if (host.hidden) return;
  const view = entityView(entity, period);
  if (!view) {
    host.textContent = `Los indicadores 3T26 de ${entityLabel(entity)} conservan su propio corte; los faltantes se muestran como No disponible.`;
    return;
  }
  const notes = view.narrative?.paragraphs ?? [];
  if (!notes.length) { host.hidden = true; return; }
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
