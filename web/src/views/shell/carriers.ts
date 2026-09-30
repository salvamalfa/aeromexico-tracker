// Airline selection shared by every card that can switch airline
// (Dashboard v2): the entity list (Industria + Aeroméxico, Volaris, Viva),
// one fixed color per entity, and a compact picker styled exactly like the
// existing "Periodo" <select> (.chart-range-control). Each card keeps its
// own selection; all of them are mirrored into the URL (?sel_<card>=A,B)
// so a view can be shared.
//
// Single-choice cards (KPI cards, the executive reading) render a native
// <select>. Multi-choice cards (charts) render a <details> dropdown with
// one checkbox per entity; at least one entity always stays selected.

export const ENTITY_KEYS = ["INDUSTRY", "AEROMEXICO", "VOLARIS", "VIVA_AEROBUS"] as const;
export type EntityKey = (typeof ENTITY_KEYS)[number];

export const ENTITY_LABELS: Record<EntityKey, string> = {
  INDUSTRY: "Industria",
  AEROMEXICO: "Aeroméxico",
  VOLARIS: "Volaris",
  VIVA_AEROBUS: "Viva",
};

// Aeroméxico keeps the page's brand blue; Volaris/Viva were validated with
// the dataviz palette checker against it (all pairs ≥ 3:1 on white, CVD
// separation ≥ 8). Industria is neutral gray and always drawn dashed.
export const ENTITY_COLORS: Record<EntityKey, string> = {
  INDUSTRY: "#6b7280",
  AEROMEXICO: "#003087",
  VOLARIS: "#d05aa8",
  VIVA_AEROBUS: "#1a9a5c",
};

export const CARRIER_KEYS: EntityKey[] = ["AEROMEXICO", "VOLARIS", "VIVA_AEROBUS"];

type Listener = (selection: EntityKey[]) => void;

interface PickerSpec {
  card: string;
  multi: boolean;
  defaults: EntityKey[];
  label?: string;
}

const selections = new Map<string, EntityKey[]>();

export function isEntityKey(value: string): value is EntityKey {
  return (ENTITY_KEYS as readonly string[]).includes(value);
}

export function parseSelection(raw: string | null, multi: boolean, defaults: EntityKey[]): EntityKey[] {
  if (!raw) return [...defaults];
  const keys = ENTITY_KEYS.filter((key) => raw.split(",").includes(key));
  if (!keys.length) return [...defaults];
  return multi ? keys : [keys[0]!];
}

export function serializeSelection(keys: EntityKey[]): string {
  return ENTITY_KEYS.filter((key) => keys.includes(key)).join(",");
}

function syncUrl(): void {
  if (typeof window === "undefined" || !window.history?.replaceState) return;
  const params = new URLSearchParams(window.location.search);
  for (const [card, keys] of selections) params.set(`sel_${card}`, serializeSelection(keys));
  const query = params.toString();
  window.history.replaceState(null, "", `${window.location.pathname}${query ? `?${query}` : ""}${window.location.hash}`);
}

export function selection(card: string): EntityKey[] {
  return selections.get(card) ?? [];
}

function summaryText(keys: EntityKey[]): string {
  if (keys.length === 1) return ENTITY_LABELS[keys[0]!];
  if (keys.length === ENTITY_KEYS.length) return "Todas";
  return `${keys.length} seleccionadas`;
}

// Mounts the picker inside `host` and returns the initial selection.
// `onChange` fires on every user change (never on mount).
export function mountPicker(host: HTMLElement, spec: PickerSpec, onChange: Listener): EntityKey[] {
  const params = new URLSearchParams(window.location.search);
  const initial = parseSelection(params.get(`sel_${spec.card}`), spec.multi, spec.defaults);
  selections.set(spec.card, initial);
  const labelText = spec.label ?? "Aerolínea";
  const id = `carrier-${spec.card}`;
  host.classList.add("chart-range-control", "carrier-control");
  if (!spec.multi) {
    host.innerHTML =
      `<label for="${id}">${labelText}</label>` +
      `<select id="${id}">` +
      ENTITY_KEYS.map((key) => `<option value="${key}">${ENTITY_LABELS[key]}</option>`).join("") +
      "</select>";
    const select = host.querySelector("select")!;
    select.value = initial[0]!;
    select.addEventListener("change", () => {
      const next = [select.value as EntityKey];
      selections.set(spec.card, next);
      syncUrl();
      onChange(next);
    });
    return initial;
  }
  host.innerHTML =
    `<span id="${id}-label">${labelText}</span>` +
    `<details class="carrier-picker" id="${id}">` +
    `<summary aria-describedby="${id}-label"></summary>` +
    '<div class="carrier-menu" role="group">' +
    ENTITY_KEYS.map(
      (key) =>
        `<label><input type="checkbox" value="${key}"><span class="carrier-dot" style="--dot:${ENTITY_COLORS[key]}"></span>${ENTITY_LABELS[key]}</label>`
    ).join("") +
    "</div></details>";
  const details = host.querySelector("details")!;
  const summary = details.querySelector("summary")!;
  const boxes = [...details.querySelectorAll<HTMLInputElement>("input[type=checkbox]")];
  const paint = (keys: EntityKey[]) => {
    summary.textContent = summaryText(keys);
    for (const box of boxes) {
      box.checked = keys.includes(box.value as EntityKey);
      // Keep one entity selected: the last checked box cannot be cleared.
      box.disabled = box.checked && keys.length === 1;
    }
  };
  paint(initial);
  for (const box of boxes) {
    box.addEventListener("change", () => {
      const next = boxes.filter((item) => item.checked).map((item) => item.value as EntityKey);
      if (!next.length) return;
      selections.set(spec.card, next);
      paint(next);
      syncUrl();
      onChange(next);
    });
  }
  document.addEventListener("click", (event) => {
    if (details.open && !details.contains(event.target as Node)) details.open = false;
  });
  return initial;
}
