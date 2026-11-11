// The global quarter controls reading dates; the approved catalog controls availability.
import { currentPeriodId } from "../../state/period";
import { isEntityKey } from "../shell/carriers";
import { fetchPublicationManifest } from "../../lib/publication-manifest";

let periods = new Map<string, string[]>();
let paths = new Map<string, string>();

export async function loadReadingPeriods(dataRoot: string): Promise<void> {
  periods = new Map();
  paths = new Map();
  const url = new URL("../../publication_manifest.json", new URL(`${dataRoot.replace(/\/$/, "")}/`, document.baseURI));
  const manifest = await fetchPublicationManifest(url);
  if (!manifest || typeof manifest !== "object" || !("analysis_manifest" in manifest) || !Array.isArray(manifest.analysis_manifest)) {
    throw new Error("Catálogo de lecturas inválido.");
  }
  for (const entry of manifest.analysis_manifest) {
    const entity = entry.entity_key === undefined ? "AEROMEXICO" : entry.entity_key;
    if (!isEntityKey(entity) || typeof entry.period_id !== "string" || !/^\d{4}Q[1-4]$/.test(entry.period_id) || typeof entry.approval_event !== "string" || !entry.approval_event) {
      throw new Error("Identidad de lectura inválida.");
    }
    const values = periods.get(entity) ?? [];
    if (values.includes(entry.period_id)) throw new Error("Lectura duplicada.");
    periods.set(entity, [...values, entry.period_id].sort());
    // Explicit entity records use their namespace, including Aeroméxico.
    // Historical entries without entity_key retain the original public path.
    paths.set(`${entity}/${entry.period_id}`, entry.entity_key === undefined
      ? entry.period_id : `${entity}/${entry.period_id}`);
  }
}

export function publishedAnalysisPath(entity: string, period: string): string | undefined {
  return paths.get(`${entity}/${period}`);
}

// Availability is checked for the global quarter only. Never silently substitute
// the latest approved reading, or honor a legacy readingPeriod URL override.
export function selectedReading(entity: string): { period_id: string; period_label: string } | undefined {
  const id = currentPeriodId();
  return id && periods.get(entity)?.includes(id)
    ? { period_id: id, period_label: `${id.slice(-1)}T${id.slice(2, 4)}` }
    : undefined;
}
