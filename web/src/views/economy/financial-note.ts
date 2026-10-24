import { entityView } from "../executive/entities";
import type { EntityKey } from "../shell/carriers";

export function renderFinancialNote(entity: EntityKey, period: string): void {
  const host = document.getElementById("financial-comparison-note");
  if (!host) return;
  host.replaceChildren();
  host.hidden = period !== "2026Q3";
  if (host.hidden) return;
  if (entity !== "AEROMEXICO") {
    host.textContent = "Los indicadores 3T26 están disponibles para Aeroméxico. Esta aerolínea o Industria conserva su propio corte; los faltantes se muestran como No disponible.";
    return;
  }
  const notes = entityView(entity, period)?.narrative?.paragraphs ?? [];
  if (!notes.length) { host.hidden = true; return; }
  const details = document.createElement("details");
  const summary = document.createElement("summary");
  summary.textContent = "Fuente y bases de comparación · Aeroméxico 3T26";
  details.append(summary);
  for (const text of notes) {
    const p = document.createElement("p"); p.textContent = text; details.append(p);
  }
  const source = document.createElement("a");
  source.href = "https://ir.aeromexico.com/financial-information/quarterly-results";
  source.textContent = "Resultados trimestrales del emisor";
  source.target = "_blank"; source.rel = "noopener noreferrer";
  details.append(source); host.append(details);
}
