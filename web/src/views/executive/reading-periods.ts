// Reading availability comes from the publication's approved identities, never
// from financial observations. Selecting a reading does not touch their store.
import { state } from "./state";
import { isEntityKey } from "../shell/carriers";

let periods = new Map<string, string[]>();
const selected = new Map<string, string>();
let currentEntity = "AEROMEXICO";

export async function loadReadingPeriods(dataRoot: string): Promise<void> {
  periods = new Map(); selected.clear();
  const url = new URL("../../publication_manifest.json", new URL(`${dataRoot.replace(/\/$/, "")}/`, document.baseURI));
  const response = await fetch(url);
  if (!response.ok) throw new Error("No se pudo verificar el catálogo de lecturas publicadas.");
  const manifest: unknown = await response.json();
  if (!manifest || typeof manifest !== "object" || !("analysis_manifest" in manifest) || !Array.isArray(manifest.analysis_manifest)) {
    throw new Error("Catálogo de lecturas inválido.");
  }
  for (const entry of manifest.analysis_manifest) {
    const entity = entry.entity_key ?? "AEROMEXICO";
    if (!isEntityKey(entity) || typeof entry.period_id !== "string" || !/^\d{4}Q[1-4]$/.test(entry.period_id) || typeof entry.approval_event !== "string" || !entry.approval_event) {
      throw new Error("Identidad de lectura inválida.");
    }
    const values = periods.get(entity) ?? [];
    if (values.includes(entry.period_id)) throw new Error("Lectura duplicada.");
    periods.set(entity, [...values, entry.period_id].sort());
  }
}

export function selectReadingPeriod(period: string): void {
  if (!periods.get(currentEntity)?.includes(period)) return;
  selected.set(currentEntity, period);
  const params = new URLSearchParams(window.location.search);
  params.set("readingPeriod", period);
  window.history.replaceState(null, "", `${window.location.pathname}?${params}${window.location.hash}`);
}

export function selectedReading(entity: string): { period_id: string; period_label: string } | undefined {
  currentEntity = entity;
  const values = periods.get(entity) ?? [];
  const requested = new URLSearchParams(window.location.search).get("readingPeriod");
  const period = selected.get(entity) ?? (requested && values.includes(requested) ? requested : values.at(-1));
  const select = document.getElementById("reading-period") as HTMLSelectElement | null;
  const label = (id: string) => `${id.slice(-1)}T${id.slice(2, 4)}`;
  if (select) {
    select.replaceChildren(...values.map((id) => new Option(label(id), id)));
    select.disabled = !period;
    if (period) select.value = period;
  }
  // Existing entities with no approved reading retain their ordinary pending
  // message for the financial period; no other issuer's reading is substituted.
  const fallback = state.records[state.periodIndex]?.period_id;
  const id = period ?? fallback;
  return id ? { period_id: id, period_label: label(id) } : undefined;
}
